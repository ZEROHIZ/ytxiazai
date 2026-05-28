# -*- coding: utf-8 -*-
"""
clip_parser.py

核心职责：
该文件负责对下载任务的各种输入参数（特别是时间区间和持续时间字符串）进行解析、格式转换及有效性验证。

主要功能：
- 将 HH:MM:SS, MM:SS, SS.FFF 或纯秒数等不同格式的时间字符串转换为浮点秒数。
- 对开始时间和结束时间进行合理性校验（例如：开始时间不能为负、不能大于结束时间）。
- 提供时间范围越界校验：当开始时间超出视频总时长时抛出异常；当结束时间超出视频总时长或未指定时，自动安全截断/补充为视频的实际总长度。
"""

import re
from typing import Optional, Tuple

def parse_duration(duration_str: Optional[str]) -> Optional[float]:
    """
    将人类可读的时间字符串解析为浮点数秒数。
    
    支持的格式包括：
    - 纯秒数 (例如 "120", "12.5")
    - 分:秒 (例如 "10:00", "05:30")
    - 时:分:秒 (例如 "01:10:00", "1:30:15.5")
    
    参数:
        duration_str: 时间格式字符串，允许为 None
        
    返回:
        float: 解析得到的秒数；如果输入为空或 None，则返回 None。
        
    异常:
        ValueError: 当字符串格式无法解析时抛出。
    """
    if duration_str is None:
        return None
        
    stripped = duration_str.strip()
    if not stripped:
        return None
        
    # 首先尝试作为纯浮点秒数解析
    try:
        return float(stripped)
    except ValueError:
        pass
        
    # 使用正则匹配 HH:MM:SS 或 MM:SS 格式
    # 格式 1: (小时:)?(分钟):(秒)
    parts = stripped.split(':')
    if len(parts) == 2:
        # MM:SS
        try:
            minutes = int(parts[0])
            seconds = float(parts[1])
            if minutes < 0 or seconds < 0:
                raise ValueError()
            return minutes * 60.0 + seconds
        except ValueError:
            raise ValueError(f"无效的分钟:秒格式：'{stripped}'。分钟和秒数均须为非负数。")
            
    elif len(parts) == 3:
        # HH:MM:SS
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            if hours < 0 or minutes < 0 or seconds < 0:
                raise ValueError()
            if minutes >= 60:
                raise ValueError("分钟不能大于等于60")
            return hours * 3600.0 + minutes * 60.0 + seconds
        except ValueError as e:
            msg = str(e) if str(e) else f"无效的小时:分钟:秒格式：'{stripped}'。"
            raise ValueError(msg)
            
    raise ValueError(f"不支持的时间格式：'{stripped}'。支持格式包括：'秒数' (如 120), '分:秒' (如 10:00), '时:分:秒' (如 01:20:00)。")


def validate_and_clamp_times(
    start_time: float, 
    end_time: Optional[float], 
    total_duration: Optional[float]
) -> Tuple[float, float]:
    """
    校验开始与结束时间，并根据视频的实际总长度进行必要的容错限制。
    
    规则：
    1. 开始时间必须为非负数。
    2. 如果指定了结束时间，结束时间必须大于开始时间。
    3. 如果提供了视频实际总长度 (total_duration)：
       - 如果开始时间大于等于总长度，抛出异常退出。
       - 如果结束时间未指定，或者结束时间大于总长度，自动将其截断为总长度。
       
    参数:
        start_time: 开始时间（秒数）
        end_time: 结束时间（秒数，允许为 None）
        total_duration: 视频总长度（秒数，允许为 None）
        
    返回:
        Tuple[float, float]: 返回校验/截断后的 (开始时间, 结束时间) 浮点秒数对。
        
    异常:
        ValueError: 当参数不合法时抛出。
    """
    if start_time < 0:
        raise ValueError(f"开始时间不能为负数 (当前输入为: {start_time}s)。")
        
    # 如果指定了视频总时长，进行越界校验与自动截断
    if total_duration is not None:
        if start_time >= total_duration:
            raise ValueError(
                f"开始时间 ({start_time}s) 已经超出或等于视频的实际总时长 ({total_duration}s)，无法进行下载。"
            )
            
        if end_time is None or end_time > total_duration:
            # 自动截断至视频结束点
            end_time = total_duration
    else:
        # 如果未获得视频总时长（如网络提取元数据失败），且未指定结束时间，默认给一个最大值或提醒
        if end_time is None:
            # 若未指定结束，默认为一个极大值（依靠底层 ffmpeg 截断）
            end_time = float('inf')
            
    if end_time <= start_time:
        raise ValueError(f"结束时间 ({end_time}s) 必须大于开始时间 ({start_time}s)。")
        
    return start_time, end_time
