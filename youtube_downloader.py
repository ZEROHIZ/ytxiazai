# -*- coding: utf-8 -*-
"""
youtube_downloader.py

核心职责：
该文件负责与 `yt-dlp` 第三方库的底层交互，核心功能包括：
1. 校验本地代理的网络连通性，防止因为代理不可用导致下载阻塞；
2. 获取 YouTube 视频的元数据（主要是标题和总时长）；
3. 根据分辨率偏好（最高2K，其次1080p/720p）构建视频格式过滤器；
4. 利用 yt-dlp 的 `download_ranges`（HTTP Range 分段请求）机制，实现仅下载视频指定区间并利用 ffmpeg 进行无损/微损精确切割，节约流量。

主要函数：
- `test_proxy(proxy_url: str) -> bool`: 检测指定的代理是否正常开放且可连接。
- `get_video_info(url: str, proxy: Optional[str], cookies_path: Optional[str]) -> dict`: 获取视频的基本信息（元数据）。
- `download_clip(...) -> str`: 核心下载函数，执行精确片段下载并保存。
"""

import os
import sys
import socket
import urllib.parse
from typing import Optional, Dict, Any

import yt_dlp
from yt_dlp.utils import download_range_func


def test_proxy(proxy_url: Optional[str]) -> bool:
    """
    测试代理的可达性。如果是本地代理（例如 127.0.0.1:7890），测试对应的 TCP 端口是否开放。
    
    参数:
        proxy_url: 代理 URL，例如 "http://127.0.0.1:7890" 或 "127.0.0.1:7890"
        
    返回:
        bool: 代理可用或未配置代理返回 True，如果配置了代理但连接超时/失败则返回 False。
    """
    if not proxy_url:
        # 没有配置代理，视为连通性“正常”（不测试）
        return True
        
    url = proxy_url.strip()
    # 补充协议头以便于 urllib 解析
    if not url.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
        url = 'http://' + url
        
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return False
            
        # 尝试通过 socket 连接该端口，超时时间设为 3 秒
        with socket.create_connection((host, port), timeout=3.0):
            return True
    except Exception:
        return False


def get_video_info(
    url: str, 
    proxy: Optional[str] = None, 
    cookies_path: Optional[str] = None,
    cookies_from_browser: Optional[str] = None
) -> Dict[str, Any]:
    """
    只提取视频的元数据（例如总时长、标题），不进行实质下载，网络开销极小。
    
    参数:
        url: YouTube 视频地址
        proxy: 代理地址
        cookies_path: Cookie 文件的绝对路径
        cookies_from_browser: 直接从浏览器中提取的浏览器名称 (如 "chrome")
        
    返回:
        Dict[str, Any]: 视频信息字典。
    """
    ydl_opts = {
        'extract_flat': False,
        'skip_download': True,
        'proxy': proxy,
        'quiet': True,
        'noprogress': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'retries': 10,
        'socket_timeout': 30,
    }
    
    if cookies_from_browser:
        ydl_opts['cookiesfrombrowser'] = (cookies_from_browser, None, None, None)
    elif cookies_path:
        ydl_opts['cookiefile'] = cookies_path
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info


def download_clip(
    url: str,
    start_time: float,
    end_time: float,
    resolution: str = "2k",
    proxy: Optional[str] = None,
    cookies_path: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
    output_dir: str = "downloads"
) -> str:
    """
    通过 HTTP Range requests 只下载指定的时间段，并调用 ffmpeg 组合输出为最终剪裁文件。
    
    参数:
        url: 视频 URL
        start_time: 开始秒数（浮点数）
        end_time: 结束秒数（浮点数）
        resolution: 最高分辨率上限 ("2k", "1080p", "720p")
        proxy: 代理服务 URL
        cookies_path: Cookie 文件的绝对路径
        cookies_from_browser: 直接从浏览器中提取的浏览器名称 (如 "chrome")
        output_dir: 存放视频的目标文件夹目录
        
    返回:
        str: 最终保存的文件路径。
    """
    # 1. 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 2. 解析分辨率映射，构造 yt-dlp 的 format 字符串
    # 目标规则: 最高 2K (1440), 其次 1080p, 再其次 720p。
    # 用 bestvideo[height<=Limit]+bestaudio/best[height<=Limit] 实现
    res_map = {
        "2k": 1440,
        "1440p": 1440,
        "1080p": 1080,
        "720p": 720
    }
    max_height = res_map.get(resolution.lower(), 1440)
    format_str = f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]"
    
    # 3. 构造输出文件名模板，直接静态嵌入开始和结束时间
    # 格式： downloads/[Video_Title]_[start]s-[end]s.[ext]
    out_template = os.path.join(
        output_dir, 
        f"%(title)s_{int(start_time)}s-{int(end_time)}s.%(ext)s"
    )
    
    # 4. 配置 yt-dlp 下载参数
    ydl_opts = {
        'format': format_str,
        'proxy': proxy,
        # 核心：使用 download_ranges 限制分段下载，force_keyframes_at_cuts 强制关键帧切分以确保时间绝对精确
        'download_ranges': download_range_func(None, [(start_time, end_time)]),
        'force_keyframes_at_cuts': True,
        'outtmpl': out_template,
        'ignoreerrors': False,
        'merge_output_format': 'mp4',  # 优先合并输出为通用 mp4 容器
        'nocheckcertificate': True,
        'retries': 10,
        'fragment_retries': 10,
        'socket_timeout': 30,
    }
    
    if cookies_from_browser:
        ydl_opts['cookiesfrombrowser'] = (cookies_from_browser, None, None, None)
    elif cookies_path:
        ydl_opts['cookiefile'] = cookies_path
    
    print(f"[*] 准备启动分段下载 (时间区间: {start_time}s - {end_time}s)...")
    print(f"[*] 格式规则: {format_str}")
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # 获取最终合并后的目标路径
        # 为了能够在运行后知道保存的真实文件名，我们可以通过 prepare_filename 提前预算出最终文件名
        # 因为 info_dict 在 download 时会展开，这里我们可以先提取部分信息
        info_dict = ydl.extract_info(url, download=False)
        filename = ydl.prepare_filename(info_dict)
        # 替换后缀为合并后的 mp4，这符合 merge_output_format
        base, _ = os.path.splitext(filename)
        final_filepath = base + ".mp4"
        
        # 执行下载
        print(f"[*] 正在下载视频段数据，请稍候...")
        ydl.download([url])
        
        return final_filepath
