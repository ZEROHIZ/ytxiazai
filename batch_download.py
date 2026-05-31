# -*- coding: utf-8 -*-
"""
batch_download.py
venv\Scripts\python batch_download.py

核心职责：
根据指定的 JSON 配置文件，自动提取视频链接、分段片段以及对应的标签（Tags），
进行批量片段下载。下载后根据“方案 B”将视频自动进行两级目录归类管理：
    - 目标文件夹：sucai/{第一级分类(主体)}/
    - 目标文件名：{完整Tag}-{片段ID}-{YouTube视频ID}.mp4
同时实现断点续传（如果本地目标文件已存在，则自动跳过下载），极大节约带宽与时间。
集成自动镜头转场对齐引擎，实现高精度亚秒级自动物理微调裁剪与 JSON 起止时间双向自动同步。

特别支持：
- 允许在 JSON 配置文件中省略 'url' 字段，自动根据 JSON 文件名提取 YouTube 视频 ID 并拼接完整的 'url' 键位，
  持久化写回 JSON 文件；
- 完美向后兼容已包含 'url' 的 JSON 文件，以及各种不同结构（如列表或字典）的 clips 声明。

运行方式：
venv\\Scripts\\python batch_download.py [JSON文件路径] [其他参数]
例如：
venv\\Scripts\\python batch_download.py data/1.json
"""

import os
import sys
import re
import json
import shutil
import argparse
import urllib.parse as urlparse
from typing import List, Tuple, Optional

# 导入同级目录下的模块
import clip_parser
import youtube_downloader
import download_clip

# 重定向本地 print 至安全控制台输出，实现无缝防乱码防护
print = download_clip.safe_print


def extract_video_id(url: str) -> str:
    """
    从 YouTube URL 中智能提取 11 位唯一的 Video ID。
    
    支持的标准格式：
    - https://www.youtube.com/watch?v=4auehJl9sRA
    - https://youtu.be/4auehJl9sRA
    - https://www.youtube.com/embed/4auehJl9sRA
    """
    if not url:
        return "unknown"
    try:
        parsed = urlparse.urlparse(url)
        if parsed.hostname in ('youtu.be', 'www.youtu.be'):
            return parsed.path.lstrip('/')
        if parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if parsed.path == '/watch':
                p = urlparse.parse_qs(parsed.query)
                return p.get('v', [''])[0]
            if parsed.path.startswith(('/embed/', '/v/')):
                return parsed.path.split('/')[2]
        # 备用正则匹配
        match = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', url)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "unknown"


def parse_time_range(time_range_str: str) -> Tuple[float, float]:
    """
    解析 JSON 中的时间区间字符串（如 "[00:00,00:03]"），转换为 (开始秒数, 结束秒数)。
    """
    match = re.match(r'\[\s*([^,]+)\s*,\s*([^\]]+)\s*\]', time_range_str)
    if not match:
        raise ValueError(f"无法解析的时间区间格式: '{time_range_str}'。格式须为: '[开始时间,结束时间]'")
    
    start_str = match.group(1).strip()
    end_str = match.group(2).strip()
    
    start_sec = clip_parser.parse_duration(start_str)
    end_sec = clip_parser.parse_duration(end_str)
    
    if start_sec is None:
        start_sec = 0.0
    if end_sec is None:
        raise ValueError(f"结束时间解析失败，不能为 None: '{end_str}'")
        
    return start_sec, end_sec


def sanitize_filename(name: str) -> str:
    """
    过滤掉 Windows 文件名中的非法字符。
    """
    return re.sub(r'[\/:*?"<>|]', '_', name)


def get_category_and_filename(tag: str, video_id: str, clip_id: str) -> Tuple[str, str]:
    """
    根据“方案 B”计算分类目录（主体）以及唯一的自包含文件名。
    """
    cleaned_tag = tag.strip() if tag else ""
    if not cleaned_tag:
        return "未分类", sanitize_filename(f"未分类-{clip_id}-{video_id}.mp4")
    
    # 拆分 Tag
    segments = [s.strip() for s in cleaned_tag.split('_') if s.strip()]
    if not segments:
        return "未分类", sanitize_filename(f"未分类-{clip_id}-{video_id}.mp4")
        
    # 第一段作为主体目录
    subject = segments[0]
    
    # 方案 B 核心：{完整Tag}-{clip_id}-{video_id}.mp4
    filename = f"{cleaned_tag}-{clip_id}-{video_id}.mp4"
    return subject, sanitize_filename(filename)


def archive_json_file(json_path: str):
    """
    将处理完毕的 JSON 文件移动至该目录下的 'processed' 子文件夹中。
    """
    try:
        dir_name = os.path.dirname(json_path) or "."
        base_name = os.path.basename(json_path)
        processed_dir = os.path.join(dir_name, "processed")
        os.makedirs(processed_dir, exist_ok=True)
        dest_path = os.path.join(processed_dir, base_name)
        
        # 如果目标已存在同名文件，先删除以防移动失败
        if os.path.exists(dest_path):
            os.remove(dest_path)
            
        shutil.move(json_path, dest_path)
        print(f"[*] [OK] 已将配置文件移至归档目录: {dest_path}")
    except Exception as e:
        print(f"[*] [WARNING] 归档配置文件 {json_path} 失败: {e}")


def main(argv: List[str]):
    print("======================================================")
    print("        YouTube Clips Batch Downloader & Classifier   ")
    print("======================================================")
    
    # 1. 定义命令行参数
    parser = argparse.ArgumentParser(
        description="根据 JSON 配置文件批量下载 YouTube 视频片段，并自动执行 Scheme B 目录归档分类。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "json_path", 
        default="data",
        nargs="?",
        help="JSON 配置文件路径或包含配置文件的目录路径 (默认: 'data')"
    )
    parser.add_argument(
        "-p", "--proxy", 
        default="127.0.0.1:7890",
        help="代理服务器地址 (默认: 127.0.0.1:7890，无代理传入空字符串 '')"
    )
    parser.add_argument(
        "-c", "--cookies", 
        default="0d24036b-958b-437b-a104-e9b0338dafc6.txt",
        help="Cookie 文件路径 (默认: '0d24036b-958b-437b-a104-e9b0338dafc6.txt')"
    )
    parser.add_argument(
        "--cookies-from-browser", 
        default=None,
        help="直接从浏览器提取 Cookie (如: chrome)。配置后将忽略 -c 选项。"
    )
    parser.add_argument(
        "-r", "--resolution", 
        choices=["2k", "1440p", "1080p", "720p"], 
        default="2k",
        help="视频最高分辨率上限限制 (默认: 2k)"
    )
    parser.add_argument(
        "-o", "--output-base", 
        default="sucai",
        help="归档分类的主目录根路径 (默认: 'sucai')"
    )
    parser.add_argument(
        "-t", "--temp-dir", 
        default="temp_downloads",
        help="临时下载存储文件夹路径 (默认: 'temp_downloads')"
    )
    
    args = parser.parse_args(argv)
    
    # 2. 检验并配置代理连通性
    proxy_str = args.proxy.strip() if args.proxy else None
    if proxy_str:
        if not proxy_str.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            proxy_str = 'http://' + proxy_str
            
        print(f"[*] 正在检测代理服务 [{proxy_str}] 的连通性...")
        if not youtube_downloader.test_proxy(proxy_str):
            print("\n[ERROR] 无法连接到代理服务器！请确保代理服务已开启或使用 -p \"\" 运行直连。")
            sys.exit(1)
        print("[OK] 代理服务器连通性检测通过。")
    else:
        print("[*] 未配置代理服务，将使用直连模式。")
        
    # 3. 扫描并加载所有待处理的 JSON 文件
    json_path = args.json_path
    json_files = []
    
    if os.path.isdir(json_path):
        # 扫描该目录下所有的 .json 文件 (排除 processed 目录以防死循环)
        for item in os.listdir(json_path):
            item_path = os.path.join(json_path, item)
            if os.path.isfile(item_path) and item.lower().endswith('.json'):
                json_files.append(item_path)
        # 对文件列表排序，确保按数字/字母顺序递增处理
        json_files.sort()
        if not json_files:
            print(f"\n[*] 在目录 [{json_path}] 中未检测到任何待处理的 .json 配置文件。")
            sys.exit(0)
    else:
        # 如果是具体文件
        if os.path.exists(json_path):
            json_files.append(json_path)
        else:
            print(f"\n[ERROR] 找不到指定的 JSON 配置文件或目录: {json_path}")
            sys.exit(1)
            
    total_json_count = len(json_files)
    print(f"\n[*] 共检测到 {total_json_count} 个 JSON 配置文件，开始循环处理...")
    
    # 确定 Cookie 路径
    cookies_from_browser = args.cookies_from_browser.strip() if args.cookies_from_browser else None
    cookies_path = None
    if not cookies_from_browser:
        cookies_path = args.cookies if os.path.exists(args.cookies) else None
        
    global_success = 0
    global_skip = 0
    global_fail = 0
    
    # 4. 循环处理每一个 JSON 文件
    for idx, json_filepath in enumerate(json_files, 1):
        print(f"\n\n######################################################")
        print(f"[*] 正在处理 JSON [{idx}/{total_json_count}]: {os.path.basename(json_filepath)}")
        print(f"######################################################")
        
        try:
            with open(json_filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"\n[ERROR] 读取或解析 JSON 失败: {json_filepath}, 错误: {e}")
            global_fail += 1
            continue
            
        video_url = config.get("url")
        clips = config.get("clips", {})
        
        # 加上 URL 键位：若 JSON 文件中无 url，则根据文件名自动拼接并回写
        config_modified = False
        if not video_url:
            base_name = os.path.basename(json_filepath)
            video_id_from_file, _ = os.path.splitext(base_name)
            # 自动拼接 YouTube 视频 URL
            video_url = f"https://www.youtube.com/watch?v={video_id_from_file}"
            config["url"] = video_url
            config_modified = True
            print(f"[*] [AUTO-FILL] JSON 文件中缺少 'url' 字段，已自动根据文件名拼接: {video_url}")
            
        # 兼容性处理：若 clips 为列表格式，自动转换为字典格式
        if isinstance(clips, list):
            clips_dict = {}
            for i, clip in enumerate(clips, 1):
                clips_dict[str(i)] = clip
            clips = clips_dict
            config["clips"] = clips
            config_modified = True
            print(f"[*] [AUTO-FILL] 检测到 clips 为列表格式，已自动转换为字典格式")
            
        # 如果有任何修改，把最新的 JSON 配置写回磁盘，实现双向自动同步
        if config_modified:
            try:
                with open(json_filepath, 'w', encoding='utf-8') as wf:
                    json.dump(config, wf, indent=4, ensure_ascii=False)
                print(f"[*] [OK] 已将更新后的配置（包含 'url' 键位）写回原 JSON 文件: {json_filepath}")
            except Exception as e:
                print(f"[*] [WARNING] 写入更新配置回 JSON 文件失败: {e}")
                
        if not video_url:
            print(f"\n[WARNING] JSON 文件中缺少 'url' 字段且无法通过文件名获取，跳过该文件。")
            global_fail += 1
            continue
        if not clips:
            print(f"\n[WARNING] JSON 文件中没有检测到任何 'clips' 片段，将直接移动该文件。")
            archive_json_file(json_filepath)
            continue
            
        # 提取视频 ID
        video_id = extract_video_id(video_url)
        print(f"[OK] 解析视频元数据成功:")
        print(f"    - 视频 URL: {video_url}")
        print(f"    - Video ID: {video_id}")
        print(f"    - 片段数量: {len(clips)}")
        
        # 5. 循环处理每个片段 (最多进行 5 轮修补尝试以抵御网络偶发故障)
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                print(f"\n[!] 正在针对 [{os.path.basename(json_filepath)}] 启动第 {attempt}/{max_attempts} 轮重试，自动尝试修补缺失片段...")
                
            success_count = 0
            skip_count = 0
            fail_count = 0
            
            for clip_id, clip_info in clips.items():
                time_range = clip_info.get("time")
                tag = clip_info.get("tag", "").strip()
                
                if not time_range:
                    print(f"\n[WARNING] 片段 [{clip_id}] 缺少时间范围，跳过该片段。")
                    fail_count += 1
                    continue
                    
                try:
                    start_sec, end_sec = parse_time_range(time_range)
                except Exception as ex:
                    print(f"\n[WARNING] 解析时间区间出错: {ex}，跳过该片段。")
                    fail_count += 1
                    continue
                    
                # 根据方案 B 规则，确定分类目标路径
                subject, target_filename = get_category_and_filename(tag, video_id, clip_id)
                target_dir = os.path.join(args.output_base, subject)
                target_filepath = os.path.join(target_dir, target_filename)
                
                # 查重：判断目标文件是否已存在，且必须包含合法的视频流（防止跳过仅存音频的损坏文件）
                file_exists = False
                if os.path.exists(target_filepath):
                    import subprocess
                    probe_cmd = [
                        "ffprobe", "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=codec_type",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        target_filepath
                    ]
                    try:
                        probe_result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                        if b"video" in probe_result.stdout:
                            file_exists = True
                        else:
                            # 存在但没有视频流（只有音频），将其删除以便重新下载
                            print(f"    [*] 检测到本地存在该片段的损坏文件（无视频流，仅存音频），正在自动清理并准备重新下载...")
                            os.remove(target_filepath)
                    except Exception:
                        file_exists = True  # 发生异常默认保留
                
                if file_exists:
                    # 在重试轮次中，已经下载的片段直接跳过，且仅在首轮打印提示以防止刷屏
                    if attempt == 1:
                        print(f"    - 片段 [{clip_id}] -> {target_filename} [已存在，跳过]")
                    skip_count += 1
                    continue
                    
                print(f"\n    [*] 片段 [{clip_id}/{len(clips)}] 开始下载 ({time_range} -> {target_filename})...")
                try:
                    # 下载至临时文件夹
                    os.makedirs(args.temp_dir, exist_ok=True)
                    downloaded_temp_path = youtube_downloader.download_clip(
                        url=video_url,
                        start_time=start_sec,
                        end_time=end_sec,
                        resolution=args.resolution,
                        proxy=proxy_str,
                        cookies_path=cookies_path,
                        cookies_from_browser=cookies_from_browser,
                        output_dir=args.temp_dir
                    )
                    
                    # 验证下载后的临时文件是否包含合法的视频流（防止因网络风控或 HTTP 429/5XX 导致只下了音频）
                    has_video = False
                    if os.path.exists(downloaded_temp_path):
                        import subprocess
                        probe_cmd = [
                            "ffprobe", "-v", "error",
                            "-select_streams", "v:0",
                            "-show_entries", "stream=codec_type",
                            "-of", "default=noprint_wrappers=1:nokey=1",
                            downloaded_temp_path
                        ]
                        try:
                            probe_result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                            if b"video" in probe_result.stdout:
                                has_video = True
                        except Exception:
                            pass
                            
                    if os.path.exists(downloaded_temp_path) and has_video:
                        # 创建目标主体目录并移动文件到目标路径
                        os.makedirs(target_dir, exist_ok=True)
                        shutil.move(downloaded_temp_path, target_filepath)
                        print(f"    [SUCCESS] 片段 [{clip_id}] 归类完成 -> {target_filepath}")
                        
                        # 自动转场镜头对齐与物理裁剪微调
                        try:
                            import auto_aligner
                            aligned = auto_aligner.auto_align_clip(target_filepath, json_filepath, clip_id)
                            if aligned:
                                print(f"    [AUTO-ALIGN] 自动检测到镜头转场，已成功微调对齐切片 [{clip_id}]！")
                        except Exception as align_err:
                            print(f"    [WARNING] 自动镜头对齐失败: {align_err}")
                            
                        success_count += 1
                    else:
                        if os.path.exists(downloaded_temp_path):
                            try:
                                os.remove(downloaded_temp_path)
                            except Exception:
                                pass
                            print(f"    [ERROR] 下载文件检测失败：文件下载成功但只包含音频流（无视频流），这通常由于 YouTube 风控限制（如 HTTP 429/5XX）导致视频请求失败。该临时文件已被清理并设为失败。")
                        else:
                            print(f"    [ERROR] 下载成功但临时下载文件未找到")
                        fail_count += 1
                except Exception as ex:
                    print(f"    [ERROR] 片段 [{clip_id}] 下载或切割时失败: {ex}")
                    fail_count += 1
                    
                # 每次真正执行下载尝试后（无论成功或失败），引入 2~5 秒随机休眠以规避防爬虫风控
                import time
                import random
                sleep_time = random.uniform(2.0, 5.0)
                print(f"    [*] 正在随机休眠 {sleep_time:.2f} 秒以保护连接、降低风控风险...")
                time.sleep(sleep_time)
                
            # 5.6 统计单文件处理情况并进行所有片段的存在性校验
            print(f"\n[*] JSON [{os.path.basename(json_filepath)}] 阶段循环结束。开始二次校验是否所有片段均已保存在本地...")
            
            all_clips_exist = True
            missing_clips = []
            
            for check_clip_id, check_clip_info in clips.items():
                check_time_range = check_clip_info.get("time")
                check_tag = check_clip_info.get("tag", "").strip()
                
                if not check_time_range:
                    continue
                    
                check_subject, check_target_filename = get_category_and_filename(check_tag, video_id, check_clip_id)
                check_filepath = os.path.join(args.output_base, check_subject, check_target_filename)
                
                if not os.path.exists(check_filepath):
                    all_clips_exist = False
                    missing_clips.append(check_clip_id)
                    
            if all_clips_exist:
                print(f"[*] [SUCCESS] 经校验，该配置下的所有 {len(clips)} 个片段均已成功保存在本地！")
                archive_json_file(json_filepath)
                global_success += success_count
                global_skip += skip_count
                global_fail += fail_count
                break  # 完美成功，退出重试循环！
            else:
                if attempt < max_attempts:
                    import time
                    import random
                    retry_wait = random.uniform(10.0, 15.0)
                    print(f"[*] [WARNING] 该配置中仍有部分片段缺失或未下载成功。")
                    print(f"    - 缺失片段 ID: {', '.join(missing_clips)}")
                    print(f"    - 正在冷却等待 {retry_wait:.2f} 秒，随后将自动发起第 {attempt+1} 次修补尝试...")
                    time.sleep(retry_wait)
                else:
                    # 最后一轮重试仍然失败，说明这个配置文件最终有缺失
                    print(f"[*] [WARNING] 已经达到最大重试次数 ({max_attempts})，该配置中仍有片段缺失。")
                    print(f"    - 缺失片段 ID: {', '.join(missing_clips)}")
                    print(f"    - 该配置文件 [{os.path.basename(json_filepath)}] 将保留在原目录以备下次手动重试。")
                    global_success += success_count
                    global_skip += skip_count
                    global_fail += fail_count
        
    # 6. 清理临时下载目录
    if os.path.exists(args.temp_dir):
        try:
            if not os.listdir(args.temp_dir):
                os.rmdir(args.temp_dir)
        except Exception:
            pass
            
    print(f"\n======================================================")
    print(f"【批量处理完毕汇总报告】")
    print(f" - 处理 JSON 文件数: {total_json_count} 个")
    print(f" - 成功归类片段: {global_success} 个")
    print(f" - 重复跳过片段: {global_skip} 个")
    print(f" - 下载失败片段: {global_fail} 个")
    print(f"======================================================")
    
    if global_fail > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
