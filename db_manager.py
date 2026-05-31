# -*- coding: utf-8 -*-
"""
db_manager.py

核心职责：
负责素材库本地 SQLite 数据库（data/sucai.db）的连接、初始化建表以及视频/片段数据的 Upsert 写入。
在写入片段时，负责利用“方案 A”将中文属性的 Key 批量映射翻译为合法的英文数据库列名。

主要功能：
- init_db(): 初始化视频表 (videos) 和片段表 (clips)。
- upsert_video(video_id, title, source_url): 插入或更新视频全局数据。
- upsert_clip(clip_data): 自动映射中文属性后，插入或更新片段特征及物理元数据。
"""

import os
import sqlite3
import json
from typing import Dict, Any

# 数据库存储路径（完美支持 Docker 挂载）
DB_PATH = os.path.join("data", "sucai.db")

# 方案 A 核心映射表：中文属性 Key -> 数据库英文列名
KEY_MAP = {
    "主体": "subject",
    "场景": "scene",
    "动作": "action",
    "镜头": "camera_movement",
    "氛围": "atmosphere",
    "色调": "color_tone",
    "描述": "description",
    "适用场景": "use_case",
    "关键词": "keywords"
}

def get_db_connection():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库并建表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 创建视频表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY,
        title TEXT,
        source_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. 创建片段表 (联合主键确保 video_id + clip_id 唯一)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clips (
        video_id TEXT,
        clip_id TEXT,
        group_dir TEXT,
        start_seconds REAL,
        end_seconds REAL,
        duration REAL,
        tag TEXT,
        subject TEXT,
        scene TEXT,
        action TEXT,
        camera_movement TEXT,
        atmosphere TEXT,
        color_tone TEXT,
        description TEXT,
        use_case TEXT,
        keywords TEXT,
        resolution TEXT,
        fps REAL,
        aspect_ratio TEXT,
        local_path TEXT,
        aligned INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (video_id, clip_id)
    )
    """)
    
    # 动态执行表结构升级升级（若已存在老表，则增加 color_tone 列）
    try:
        cursor.execute("ALTER TABLE clips ADD COLUMN color_tone TEXT")
    except sqlite3.OperationalError:
        pass  # 已经包含该列
    
    conn.commit()
    conn.close()
    print(f"[*] [DB] 数据库已成功在 [{DB_PATH}] 初始化。")


def upsert_video(video_id: str, title: str, source_url: str):
    """
    更新或插入视频全局元数据。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO videos (video_id, title, source_url)
    VALUES (?, ?, ?)
    ON CONFLICT(video_id) DO UPDATE SET
        title = excluded.title,
        source_url = excluded.source_url
    """, (video_id, title, source_url))
    conn.commit()
    conn.close()


def upsert_clip(clip_data: Dict[str, Any]):
    """
    自动利用“方案 A”映射中文属性，并更新或插入片段记录（Upsert）。
    """
    # 1. 提取核心非属性字段
    video_id = clip_data.get("video_id")
    clip_id = str(clip_data.get("clip_id"))
    group_dir = clip_data.get("group_dir")
    start_seconds = clip_data.get("start_seconds")
    end_seconds = clip_data.get("end_seconds")
    duration = clip_data.get("duration")
    tag = clip_data.get("tag")
    local_path = clip_data.get("local_path")
    if local_path:
        local_path = local_path.replace("\\", "/")
        if os.path.isabs(local_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            local_path = os.path.relpath(local_path, base_dir)
            local_path = local_path.replace("\\", "/")
    aligned = 1 if clip_data.get("aligned") else 0
    
    # 物理元数据字段
    resolution = clip_data.get("resolution")
    fps = clip_data.get("fps")
    aspect_ratio = clip_data.get("aspect_ratio")
    
    # 2. 方案 A：映射中文 attributes 字段到英文变量上
    raw_attributes = clip_data.get("attributes", {})
    mapped_attrs = {}
    for zh_key, en_key in KEY_MAP.items():
        val = raw_attributes.get(zh_key, None)
        # 对关键词列表进行扁平化处理，转为逗号分隔的字符串存储，便于检索
        if en_key == "keywords" and isinstance(val, list):
            val = ",".join(val)
        mapped_attrs[en_key] = val
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 3. 执行 Upsert SQL 语句
    cursor.execute("""
    INSERT INTO clips (
        video_id, clip_id, group_dir, start_seconds, end_seconds, duration, tag,
        subject, scene, action, camera_movement, atmosphere, color_tone, description, use_case, keywords,
        resolution, fps, aspect_ratio, local_path, aligned
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?
    )
    ON CONFLICT(video_id, clip_id) DO UPDATE SET
        group_dir = excluded.group_dir,
        start_seconds = excluded.start_seconds,
        end_seconds = excluded.end_seconds,
        duration = excluded.duration,
        tag = excluded.tag,
        subject = excluded.subject,
        scene = excluded.scene,
        action = excluded.action,
        camera_movement = excluded.camera_movement,
        atmosphere = excluded.atmosphere,
        color_tone = excluded.color_tone,
        description = excluded.description,
        use_case = excluded.use_case,
        keywords = excluded.keywords,
        resolution = excluded.resolution,
        fps = excluded.fps,
        aspect_ratio = excluded.aspect_ratio,
        local_path = excluded.local_path,
        aligned = excluded.aligned
    """, (
        video_id, clip_id, group_dir, start_seconds, end_seconds, duration, tag,
        mapped_attrs.get("subject"), mapped_attrs.get("scene"), mapped_attrs.get("action"),
        mapped_attrs.get("camera_movement"), mapped_attrs.get("atmosphere"), mapped_attrs.get("color_tone"), mapped_attrs.get("description"),
        mapped_attrs.get("use_case"), mapped_attrs.get("keywords"),
        resolution, fps, aspect_ratio, local_path, aligned
    ))
    
    conn.commit()
    conn.close()
    print(f"    [DB-OK] 片段 [{clip_id}] 信息已成功录入/更新至本地数据库。")


if __name__ == "__main__":
    # 本地直接运行测试初始化
    init_db()
