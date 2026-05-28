# -*- coding: utf-8 -*-
"""
download_clip.py

核心职责：
该文件是整个命令行程序的统一入口（Main Entrypoint）。它负责：
1. 使用 `argparse` 解析用户输入的命令行参数（如视频地址、起止时间、代理端口、Cookie路径等）。
2. 在核心下载启动前，率先检测代理服务的可用性，并在连接失败时向用户提供高可读性的引导和错误指示。
3. 提取视频元数据以获取总时长，将起止时间进行格式化及合法性验证（包括自动越界截断）。
4. 调度下载模块执行局部片段下载，并于完成后汇报成果。

运行方式：
python download_clip.py "URL" -s "开始时间" -e "结束时间" [其他可选参数]
"""

import os
import sys
import argparse
from typing import List

# 导入自定义模块
import clip_parser
import youtube_downloader


def safe_print(*args, **kwargs):
    """
    安全地在控制台输出文本，自动替换当前终端无法编码的特殊字符（如 Emoji 🗻）。
    """
    encoding = sys.stdout.encoding or 'utf-8'
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    file = kwargs.get('file', sys.stdout)
    
    # 仅对输出到标准输出/错误的情况进行安全编码替换
    if file in (sys.stdout, sys.stderr):
        try:
            text = sep.join(str(arg) for arg in args)
            encoded = text.encode(encoding, errors='replace')
            file.buffer.write(encoded + end.encode(encoding))
            file.flush()
        except Exception:
            text = sep.join(str(arg).encode('ascii', errors='replace').decode('ascii') for arg in args)
            file.write(text + end)
            file.flush()
    else:
        import builtins
        builtins.print(*args, **kwargs)

# 重定向本地 print 至安全控制台输出，实现无缝防乱码防护
print = safe_print


def print_banner():
    """打印漂亮的程序头"""
    banner = """
======================================================
     YouTube Partial Video Clip Downloader (yt-dlp)
======================================================
    """
    print(banner)


def main(argv: List[str]):
    print_banner()
    
    # 1. 定义命令行参数解析器
    parser = argparse.ArgumentParser(
        description="高效下载 YouTube 视频的特定时间片段，节约流量与时间。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "url", 
        help="YouTube 视频链接 (例如: https://www.youtube.com/watch?v=TnG89ChN9LQ)"
    )
    parser.add_argument(
        "-s", "--start", 
        default="0",
        help="片段开始时间，支持格式: 纯秒数(如 120), 分:秒(如 10:00), 时:分:秒(如 01:10:00)。默认从头(0秒)开始。"
    )
    parser.add_argument(
        "-e", "--end", 
        default=None,
        help="片段结束时间，支持格式与开始时间相同。如果不指定，则默认下载至视频实际结束处。"
    )
    parser.add_argument(
        "-p", "--proxy", 
        default="127.0.0.1:7890",
        help="代理服务器地址 (默认: 127.0.0.1:7890，如不使用代理请传入空字符串 '')"
    )
    parser.add_argument(
        "-c", "--cookies", 
        default="0d24036b-958b-437b-a104-e9b0338dafc6.txt",
        help="Netscape 格式 Cookie 文件的路径 (默认: 预置的 0d24036b-958b-437b-a104-e9b0338dafc6.txt)"
    )
    parser.add_argument(
        "--cookies-from-browser", 
        default=None,
        help="直接从浏览器提取 Cookie (如: chrome, firefox, edge, brave)。配置后将忽略 -c 选项。"
    )
    parser.add_argument(
        "-r", "--resolution", 
        choices=["2k", "1440p", "1080p", "720p"], 
        default="2k",
        help="视频最高分辨率上限限制 (默认: 2k。规则：最高2K/1440p，无则1080p，再无则720p)"
    )
    parser.add_argument(
        "-o", "--output-dir", 
        default="downloads",
        help="视频保存目录路径 (默认: 'downloads')"
    )
    
    args = parser.parse_args(argv)
    
    # 2. 规范化并校验代理连通性 (Fail-Fast 策略)
    proxy_str = args.proxy.strip() if args.proxy else None
    if proxy_str:
        # 格式化为标准代理协议前缀
        if not proxy_str.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            proxy_str = 'http://' + proxy_str
            
        print(f"[*] 正在检测代理服务 [{proxy_str}] 的连通性...")
        if not youtube_downloader.test_proxy(proxy_str):
            print("\n[ERROR] 无法连接到代理服务器！")
            print(f"   当前配置代理地址为: {proxy_str}")
            print("   请按以下步骤排查：")
            print("   1. 确保您的代理客户端（如 Clash, Clash Verge 等）已正常开启运行。")
            print("   2. 确认代理的 HTTP/SOCKS 端口是否确为 7890。如果不是，请通过命令行参数 -p 自定义端口。")
            print("   3. 如果不需要代理服务，请使用参数 -p \"\" 运行程序。")
            sys.exit(1)
        print("[OK] 代理服务器连通性检测通过。")
    else:
        print("[*] 未配置代理服务，将使用直连模式。")
        
    # 3. 解析起止时间参数
    try:
        start_sec = clip_parser.parse_duration(args.start)
        if start_sec is None:
            start_sec = 0.0
            
        end_sec = clip_parser.parse_duration(args.end)
    except ValueError as e:
        print(f"\n[ERROR] 时间格式解析失败: {e}")
        sys.exit(1)
        
    # 4. 提取视频元数据以进行时长对齐和越界判定
    print(f"\n[*] 正在通过网络提取视频元数据信息 (不下载视频)...")
    cookies_from_browser = args.cookies_from_browser.strip() if args.cookies_from_browser else None
    cookies_path = None
    
    if cookies_from_browser:
        print(f"[*] 已配置直接从浏览器 [{cookies_from_browser}] 提取 Cookie。")
    else:
        cookies_path = args.cookies if os.path.exists(args.cookies) else None
        if args.cookies and not cookies_path:
            print(f"[WARNING] 指定的 Cookie 文件未找到: {args.cookies}，将尝试不附带 Cookie 进行提取。")
        
    try:
        info_dict = youtube_downloader.get_video_info(
            args.url, 
            proxy_str, 
            cookies_path, 
            cookies_from_browser
        )
        video_title = info_dict.get('title', 'YouTube Video')
        total_duration = info_dict.get('duration')
        
        print(f"[OK] 成功获取视频元数据：")
        print(f"    - 视频标题: {video_title}")
        if total_duration:
            print(f"    - 视频总长: {int(total_duration)} 秒 ({int(total_duration)//60}分{int(total_duration)%60}秒)")
        else:
            print(f"    - 视频总长: 无法从元数据获取")
            
    except Exception as e:
        print(f"\n[ERROR] 获取视频元数据失败。详细信息：{e}")
        print("   这通常是由于网络不畅、Cookie失效或链接有误导致。请检查网络配置或重新导出 Cookie。")
        sys.exit(1)
        
    # 5. 执行时间范围合理性校验和自动截断
    try:
        resolved_start, resolved_end = clip_parser.validate_and_clamp_times(
            start_sec, end_sec, total_duration
        )
    except ValueError as e:
        print(f"\n[ERROR] 时间区间不合法: {e}")
        sys.exit(1)
        
    # 如果结束时间是无限的（在没有获取到视频长度的极罕见场景下），在此说明
    end_display = f"{resolved_end}s" if resolved_end != float('inf') else "视频结尾"
    print(f"\n[*] 解析后的下载区间:")
    print(f"    - 开始点: {resolved_start} 秒")
    print(f"    - 结束点: {end_display}")
    print(f"    - 下载净长: {resolved_end - resolved_start:.2f} 秒")
    
    # 6. 开启片段下载
    try:
        saved_path = youtube_downloader.download_clip(
            url=args.url,
            start_time=resolved_start,
            end_time=resolved_end,
            resolution=args.resolution,
            proxy=proxy_str,
            cookies_path=cookies_path,
            cookies_from_browser=cookies_from_browser,
            output_dir=args.output_dir
        )
        print(f"\n[SUCCESS] 视频片段已高效下载完毕！")
        print(f"    - 保存文件名: {os.path.basename(saved_path)}")
        print(f"    - 存放完整路径: {os.path.abspath(saved_path)}")
        
    except Exception as e:
        print(f"\n[ERROR] 下载或切割合并过程中发生错误：{e}")
        sys.exit(1)


if __name__ == "__main__":
    # 解析来自命令行直接传入的 argv 数组
    main(sys.argv[1:])
