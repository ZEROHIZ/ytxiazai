# -*- coding: utf-8 -*-
"""
download_test.py

核心职责：
用于测试从“YouTube 下载与素材管理系统”后端 API 检索视频片段并下载到本地根目录。
主要功能：
1. 请求后端的 /api/clips 接口获取最新的已下载视频素材片段列表。
2. 提取第一个有效片段的 Web 访问路径（web_path）。
3. 采用流式（Streaming）分块下载，并在控制台实时输出下载进度与日志。
"""

import os
import sys
import requests

# 配置服务器地址
SERVER_HOST = "192.168.110.30:7878"
# 备用本地开发测试地址（如果上述地址连接失败，可作为回退）
BACKUP_HOST = "127.0.0.1:7878"

def test_download():
    # 尝试连接的地址列表
    hosts = [SERVER_HOST, BACKUP_HOST]
    base_url = None
    clips_data = None
    
    print("[*] 正在尝试检索视频片段...")
    
    # 1. 自动寻找可用服务器地址并调用 /api/clips 接口
    for host in hosts:
        url = f"http://{host}/api/clips"
        try:
            print(f" -> 正在连接服务器: {url}")
            response = requests.get(url, params={"limit": 5}, timeout=5, proxies={"http": None, "https": None})
            if response.status_code == 200:
                clips_data = response.json()
                base_url = f"http://{host}"
                print(f"[+] 成功连接到服务器: {host}")
                
                # 打印 clips 完整的原始响应信息
                import json
                print("\n" + "="*20 + " 【API /api/clips 完整响应信息】 " + "="*20)
                print(json.dumps(clips_data, indent=4, ensure_ascii=False))
                print("="*75 + "\n")
                
                break
            else:
                print(f"[!] 服务器返回异常状态码: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[!] 无法连接到 {host}: {e}")
            
    if not clips_data or not clips_data.get("clips"):
        print("[x] 错误：未能在服务器上获取到任何已下载的视频片段列表！请确认后端正在运行且包含已下载素材。")
        sys.exit(1)
        
    # 2. 选取列表中的第一个片段
    clip = clips_data["clips"][0]
    web_path = clip.get("web_path")
    video_title = clip.get("video_title", "未命名视频")
    clip_id = clip.get("clip_id", "未知ID")
    
    if not web_path:
        print("[x] 错误：获取到的片段没有有效的 web_path 播放地址。")
        sys.exit(1)
        
    download_url = f"{base_url}{web_path}"
    # 获取文件名，默认使用 web_path 的最后一段，否则用 clip_id.mp4
    filename = os.path.basename(web_path) if web_path else f"{clip_id}.mp4"
    # 解码 URL 中的中文字符
    from urllib.parse import unquote
    filename = unquote(filename)
    
    target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    
    print("\n" + "="*50)
    print(f"【发现可下载素材】")
    print(f"  - 视频标题: {video_title}")
    print(f"  - 片段编号: {clip_id}")
    print(f"  - 下载地址: {download_url}")
    print(f"  - 保存目标: {target_path}")
    print("="*50 + "\n")
    
    # 3. 开始流式下载并输出进度日志
    try:
        print("[*] 正在发起流式下载请求...")
        with requests.get(download_url, stream=True, timeout=15, proxies={"http": None, "https": None}) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            print(f"[+] 连接建立成功！文件总大小: {total_size / (1024*1024):.2f} MB")
            print("[*] 正在写入文件并打印进度...")
            
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB per chunk
            
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f" -> 已下载: {downloaded / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB ({percent:.1f}%)")
                        else:
                            print(f" -> 已下载: {downloaded / (1024*1024):.2f} MB (未知总大小)")
                            
        print(f"\n[√] 恭喜！素材已成功下载到根目录：{target_path}")
        
    except Exception as e:
        print(f"\n[x] 下载过程中发生异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_download()
