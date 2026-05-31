# -*- coding: utf-8 -*-
"""
metadata_extractor.py

核心职责：
使用本地系统安装的 `ffprobe` 工具，对指定路径下的视频切片进行多维度物理元数据解析。

主要功能：
- extract_metadata(video_path: str) -> dict:
  提取视频的：宽度、高度、分辨率字符串 (如 "1920x1080")、帧率 (如 29.97)、
  画面比例 (如 "16:9")、物理时长 (以 ffprobe 实测为准)。
"""

import subprocess
import json
import math
from typing import Dict, Any, Optional

def extract_metadata(video_path: str) -> Dict[str, Any]:
    """
    使用 ffprobe 工具解析指定视频片段的物理特征，返回元数据字典。
    """
    default_meta = {
        "resolution": "unknown",
        "fps": 0.0,
        "aspect_ratio": "unknown",
        "duration": 0.0
    }
    
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration,display_aspect_ratio",
        "-of", "json",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if result.returncode != 0:
            print(f"    [WARNING] ffprobe 返回非0状态码: {result.stderr}")
            return default_meta
            
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return default_meta
            
        stream = streams[0]
        
        # 1. 抽取宽度和高度，组合成分辨率
        width = stream.get("width")
        height = stream.get("height")
        resolution = f"{width}x{height}" if width and height else "unknown"
        
        # 2. 抽取帧率 (r_frame_rate 通常为 "30000/1001" 或 "30/1")
        fps = 0.0
        r_frame_rate = stream.get("r_frame_rate", "")
        if "/" in r_frame_rate:
            try:
                num, den = map(float, r_frame_rate.split("/"))
                if den > 0:
                    fps = round(num / den, 2)
            except Exception:
                pass
        
        # 3. 抽取宽高比，如果不存在则利用宽和高利用最大公约数自动缩水计算
        aspect_ratio = stream.get("display_aspect_ratio", "unknown")
        if aspect_ratio == "N/A" or aspect_ratio == "0:1" or aspect_ratio == "unknown":
            if width and height:
                try:
                    gcd = math.gcd(width, height)
                    aspect_ratio = f"{width // gcd}:{height // gcd}"
                except Exception:
                    aspect_ratio = "unknown"
                    
        # 4. 抽取真实时长
        duration = 0.0
        duration_str = stream.get("duration")
        if duration_str:
            try:
                duration = round(float(duration_str), 2)
            except ValueError:
                pass
                
        return {
            "resolution": resolution,
            "fps": fps,
            "aspect_ratio": aspect_ratio,
            "duration": duration
        }
        
    except FileNotFoundError:
        print("    [WARNING] 本地环境未检测到 'ffprobe' 可执行文件，跳过物理元数据提取。")
        return default_meta
    except Exception as e:
        print(f"    [WARNING] 解析视频元数据失败 ({video_path}): {e}")
        return default_meta


if __name__ == "__main__":
    # 本地直接运行测试（如果需要的话，传入一个本地视频路径）
    import sys
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        print(f"正在测试解析: {test_path}")
        print(extract_metadata(test_path))
    else:
        print("提示: 可传入视频路径进行直接解析测试。")
