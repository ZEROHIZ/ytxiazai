# -*- coding: utf-8 -*-
"""
auto_aligner.py

核心职责：
该文件负责视频片段的“自动转场/镜头对齐”与“自动物理裁剪”。
当大模型给出的切片时间有细微偏差时，视频开头或结尾会残留相邻场景的短片段。
本程序通过 FFmpeg 帧差分析（Scene Score 突变率）自动检测这些残留并物理剔除。

核心设计：
1. 双向高效探测：
   - 优先检测开头（Front Check）的 1.5 秒区间。若检测到转场，执行微调剪裁，不再检测中后段；
   - 若开头正常，检测结尾（Back Check）的最后 1.5 秒区间。若检测到转场，执行微调剪裁。
   - 检测时间窗口最多为视频时长的一半（D/2），防止过度裁剪。
2. 通用短片段裁剪算法（剪短留长）：
   - 识别出转场时间点 t 后，计算前段长度 (t) 与后段长度 (duration - t)。
   - 若前段 >= 后段（如 3.169s >= 1.869s）：前段为长主体，后段为短残留，自动切除尾部（trim_end = duration - t）。
   - 若前段 < 后段（如 0.700s < 4.300s）：后段为长主体，前段为短残留，自动切除头部（trim_start = t）。
   - 100% 确保只切除短的残留，留下长的主画面。
3. 原地物理微调与 JSON 自动同步：
   - 不需要备份与还原，直接通过 FFmpeg 重编码生成临时文件，成功后覆盖原文件，并自动重写 JSON 配置文件中的 time 字段。
4. 去重对齐标记：
   - 在 JSON 文件的每一个 clip 中，处理完成后自动打上 `"aligned": true` 标记。
   - 运行前先检查该标记，如已对齐，直接跳过，防止重复处理。
"""

import os
import re
import json
import shutil
import subprocess
from typing import Tuple, Optional

# 导入同级目录下的模块以复用解析与命名规则
import clip_parser


def get_video_duration(video_path: str) -> float:
    """
    通过 ffprobe 获取视频的精确总时长（秒）。
    """
    cmd = [
        "ffprobe", "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        video_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        out = result.stdout.decode('utf-8', errors='ignore').strip()
        return float(out)
    except Exception as e:
        print(f"    [WARNING] 获取视频时长失败: {e}，默认返回 0.0s")
        return 0.0


def detect_scene_transition(
    video_path: str, 
    start_seek: Optional[float] = None, 
    duration_limit: Optional[float] = None, 
    threshold: float = 0.22
) -> Optional[float]:
    """
    在指定时间段内运行 FFmpeg 检测画面切换（转场）。
    如果检测到 scene_score 陡增（> threshold），返回其在视频中的绝对时间戳。
    
    参数:
        video_path: 视频文件路径
        start_seek: 如果指定，将使用 -sseof 从视频末尾向前定位进行检测
        duration_limit: 如果指定，限制检测的时长（-t 参数）
        threshold: 镜头切换突变门槛（默认 0.22）
    """
    cmd = ["ffmpeg", "-y"]
    
    # 如果指定了尾部 seek
    if start_seek is not None:
        cmd.extend(["-sseof", f"-{start_seek:.3f}"])
        
    cmd.extend(["-i", video_path])
    
    # 如果指定了时长限制（用于开头检测，只算前 N 秒，避免算完整个视频）
    if duration_limit is not None:
        cmd.extend(["-t", f"{duration_limit:.3f}"])
        
    # 使用 select 过滤器并要求输出 lavfi.scene_score 属性
    cmd.extend([
        "-vf", f"select='gt(scene,{threshold})',metadata=print:key=lavfi.scene_score",
        "-f", "null", "-"
    ])
    
    try:
        # 执行检测，抓取 stderr 输出
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stderr_text = result.stderr.decode('utf-8', errors='ignore')
        
        # 解析日志提取 pts_time，例如:
        # [Parsed_metadata_1 @ ...] frame:0    pts:21010    pts_time:0.700333
        pattern = re.compile(r"pts_time:\s*([\d\.]+)")
        
        for line in stderr_text.splitlines():
            if "pts_time" in line:
                match = pattern.search(line)
                if match:
                    t = float(match.group(1))
                    return t
        return None
    except Exception as e:
        print(f"    [WARNING] 镜头切换检测发生异常: {e}")
        return None


def format_seconds_to_time(seconds: float) -> str:
    """
    将秒数格式化为 HH:MM:SS.FFF 或 MM:SS.FFF 字符串。
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    else:
        return f"{m:02d}:{s:06.3f}"


def auto_align_clip(video_path: str, json_path: str, clip_id: str, threshold: float = 0.22) -> bool:
    """
    自动场景对齐核心函数。
    1. 检查 JSON 是否已处理过；
    2. 获取视频总长；
    3. 计算探测窗口；
    4. 运行开头与结尾转场检测，并执行物理剪裁；
    5. 同步写入 JSON 配置文件并标记已对齐。
    
    返回:
        bool: 是否进行了物理对齐/剪切。
    """
    # 步骤 0: 检查 JSON 是否已对齐过，避免重复处理
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            clips = config.get("clips", {})
            if clip_id in clips and clips[clip_id].get("aligned") is True:
                print(f"    - 片段 [{clip_id}] [已对齐标记，跳过]")
                return False
        except Exception:
            pass

    if not os.path.exists(video_path):
        print(f"    [WARNING] 视频文件不存在，无法进行自动镜头对齐: {video_path}")
        return False
        
    duration = get_video_duration(video_path)
    if duration <= 1.0:
        # 视频太短，不适合再裁剪
        return False
        
    # 定义探测窗口，默认为 1.5 秒，但绝不能超过视频总长度的一半，防止误把长片段切掉
    max_detect_window = min(1.5, duration / 2.0)
    
    trim_start = 0.0
    trim_end = 0.0
    
    print(f"    [*] 开始自动分析视频边界 (总长 {duration:.3f}s, 扫描窗口 {max_detect_window:.3f}s)...")
    
    # 步骤 1: 扫描镜头切换点 (优先开头，其次结尾)
    front_t = detect_scene_transition(
        video_path=video_path, 
        duration_limit=max_detect_window, 
        threshold=threshold
    )
    
    back_t = None
    if front_t is None:
        back_t = detect_scene_transition(
            video_path=video_path, 
            start_seek=max_detect_window, 
            threshold=threshold
        )
        
    # 统一解析得到的绝对转场时间点 t
    t = None
    if front_t is not None:
        t = front_t
    elif back_t is not None:
        # 处理 FFmpeg 在尾部 seek 时绝对时间戳和相对时间戳的兼容性
        if back_t < max_detect_window:
            t = duration - max_detect_window + back_t
        else:
            t = back_t

    # 步骤 2: 应用通用短片段裁剪算法（剪短留长）
    if t is not None and 0.05 < t < duration - 0.05:
        first_segment_len = t
        second_segment_len = duration - t
        
        if first_segment_len >= second_segment_len:
            # 前半段较长，后半段为短残留 -> 自动切除尾部！
            trim_end = second_segment_len
            trim_start = 0.0
            print(f"    [AUTO-ALIGN] 探测到转场点在 {t:.3f}s (前半段较长 {first_segment_len:.3f}s)。将自动切除尾部 {trim_end:.3f}s 并保留前半段。")
        else:
            # 后半段较长，前半段为短残留 -> 自动切除头部！
            trim_start = first_segment_len
            trim_end = 0.0
            print(f"    [AUTO-ALIGN] 探测到转场点在 {t:.3f}s (后半段较长 {second_segment_len:.3f}s)。将自动切除头部 {trim_start:.3f}s 并保留后半段。")

    # 步骤 3: 确定是否需要物理裁剪
    has_cut = (trim_start > 0.0 or trim_end > 0.0)
    
    if has_cut:
        # 执行物理原地重编码剪切
        new_duration = duration - trim_start - trim_end
        if new_duration <= 0.2:
            print("    [WARNING] 裁剪后视频长度小于 0.2s，放弃物理裁剪。")
            has_cut = False
        else:
            temp_path = video_path + ".temp.mp4"
            # 极速高质量重编码剪裁命令，确保 100% 帧精准
            cmd = [
                "ffmpeg", "-y", 
                "-ss", f"{trim_start:.3f}", 
                "-t", f"{new_duration:.3f}", 
                "-i", video_path, 
                "-c:v", "libx264", "-preset", "superfast", "-crf", "20", 
                "-c:a", "aac", 
                temp_path
            ]
            
            try:
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                if os.path.exists(temp_path):
                    # 物理覆盖原视频 file，无需保留备份
                    os.remove(video_path)
                    os.rename(temp_path, video_path)
                    print(f"    [SUCCESS] 视频物理微调剪切成功！新总长: {new_duration:.3f}s")
                else:
                    print("    [ERROR] FFmpeg 执行成功但临时切片文件未生成，放弃。")
                    has_cut = False
            except Exception as e:
                print(f"    [ERROR] FFmpeg 裁剪执行失败: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                has_cut = False
    else:
        print("    [AUTO-ALIGN] 未检测到任何视频边界转场残留，视频极其干净，无需对齐。")
        
    # 步骤 4: 同步重写 JSON 配置文件（更新起止时间并打上 aligned 标记）
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            clips = config.get("clips", {})
            if clip_id in clips:
                # 只有发生了物理裁剪，才更新时间戳
                if has_cut:
                    time_range = clips[clip_id].get("time", "")
                    match = re.match(r'\[\s*([^,]+)\s*,\s*([^\]]+)\s*\]', time_range)
                    if match:
                        start_str = match.group(1).strip()
                        end_str = match.group(2).strip()
                        
                        old_start_sec = clip_parser.parse_duration(start_str) or 0.0
                        old_end_sec = clip_parser.parse_duration(end_str) or 0.0
                        
                        new_start_sec = old_start_sec + trim_start
                        new_end_sec = old_end_sec - trim_end
                        
                        new_time_range = f"[{format_seconds_to_time(new_start_sec)},{format_seconds_to_time(new_end_sec)}]"
                        clips[clip_id]["time"] = new_time_range
                        print(f"    [JSON-SYNC] 已将 JSON 片段 [{clip_id}] 的时间更新为: {new_time_range}")
                
                # 标记该片段已成功对齐/审核完毕
                clips[clip_id]["aligned"] = True
                
                # 写回 JSON 文件
                with open(json_path, 'w', encoding='utf-8') as wf:
                    json.dump(config, wf, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"    [WARNING] 同步重写 JSON 配置文件标记失败: {e}")
            
    return has_cut
