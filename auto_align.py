# -*- coding: utf-8 -*-
"""
auto_align.py

核心职责：
这是一个独立的批量自动场景对齐与物理裁剪脚本。
它允许用户在下载完所有片段后，或者针对以前已有的素材库，一键扫描并对齐所有的 MP4 文件。

运行方式：
venv\\Scripts\\python auto_align.py [JSON文件或目录路径] [其他可选参数]
例如：
venv\\Scripts\\python auto_align.py data/processed/1.json
"""

import os
import sys
import json
import argparse
from typing import List

# 导入同级目录下的核心对齐模块
import auto_aligner
from batch_download import extract_video_id, get_category_and_filename, print


def main(argv: List[str]):
    print("======================================================")
    print("        YouTube Clips Auto-Scene Aligner Tool         ")
    print("======================================================")
    
    # 1. 定义命令行参数
    parser = argparse.ArgumentParser(
        description="一键批量对已下载视频片段执行镜头切换自动对齐及物理裁剪微调。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "json_path", 
        default="data",
        nargs="?",
        help="JSON 配置文件路径，或者包含配置文件的目录路径 (默认: 'data')"
    )
    parser.add_argument(
        "-t", "--threshold", 
        type=float,
        default=0.22,
        help="镜头切换差异突变阀值检测参数 (默认: 0.22。数值越小越灵敏)"
    )
    parser.add_argument(
        "-o", "--output-base", 
        default="sucai",
        help="归档素材库根路径目录 (默认: 'sucai')"
    )
    
    args = parser.parse_args(argv)
    
    # 2. 扫描加载 JSON 文件
    json_path = args.json_path
    json_files = []
    
    if os.path.isdir(json_path):
        # 扫描该目录下所有的 .json 文件 (递归处理子目录或单独处理子目录)
        for root, dirs, files in os.walk(json_path):
            for file in files:
                if file.lower().endswith('.json'):
                    json_files.append(os.path.join(root, file))
        # 排序
        json_files.sort()
        if not json_files:
            print(f"\n[*] 在目录 [{json_path}] 中未检测到任何待处理的 .json 配置文件。")
            sys.exit(0)
    else:
        if os.path.exists(json_path):
            json_files.append(json_path)
        else:
            print(f"\n[ERROR] 找不到指定的 JSON 配置文件或目录: {json_path}")
            sys.exit(1)
            
    total_files = len(json_files)
    print(f"\n[*] 共检测到 {total_files} 个 JSON 配置文件，开始扫描关联素材并自动对齐...")
    
    scanned_clips = 0
    aligned_clips = 0
    skipped_clips = 0
    missing_clips = 0
    
    # 3. 循环扫描并自动对齐
    for idx, json_filepath in enumerate(json_files, 1):
        print(f"\n######################################################")
        print(f"[*] 正在扫描 JSON [{idx}/{total_files}]: {os.path.basename(json_filepath)}")
        print(f"######################################################")
        
        try:
            with open(json_filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取或解析 JSON 失败: {json_filepath}, 错误: {e}")
            continue
            
        video_url = config.get("url")
        clips = config.get("clips", {})
        
        if not video_url or not clips:
            print(f"[WARNING] 缺少 url 或 clips，跳过此文件。")
            continue
            
        video_id = extract_video_id(video_url)
        
        # 处理该 JSON 下的每一个片段
        for clip_id, clip_info in clips.items():
            scanned_clips += 1
            
            # 优先检查是否已经打上对齐标记，避免重复检测
            if clip_info.get("aligned") is True:
                skipped_clips += 1
                continue
                
            tag = clip_info.get("tag", "").strip()
            
            # 获取对应的分类和文件名，定位本地视频实体路径
            subject, target_filename = get_category_and_filename(tag, video_id, clip_id)
            target_filepath = os.path.join(args.output_base, subject, target_filename)
            
            if os.path.exists(target_filepath):
                print(f"\n    -> 片段 [{clip_id}] 关联物理素材成功: {target_filename}")
                # 调用核心对齐引擎
                try:
                    is_aligned = auto_aligner.auto_align_clip(
                        video_path=target_filepath, 
                        json_path=json_filepath, 
                        clip_id=clip_id,
                        threshold=args.threshold
                    )
                    if is_aligned:
                        aligned_clips += 1
                except Exception as ex:
                    print(f"    [ERROR] 自动镜头对齐时发生未捕获异常: {ex}")
            else:
                # 记录不存在的切片
                missing_clips += 1
                
    print(f"\n======================================================")
    print(f"【批量自动场景对齐汇总报告】")
    print(f" - 扫描 JSON 配置文件: {total_files} 个")
    print(f" - 扫描视频片段总数: {scanned_clips} 个")
    print(f" - 自动微调并对齐片段: {aligned_clips} 个")
    print(f" - 已对齐标记跳过片段: {skipped_clips} 个")
    print(f" - 未找到本地物理文件: {missing_clips} 个")
    print(f"======================================================")
    
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
