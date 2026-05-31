# -*- coding: utf-8 -*-
"""
web_app.py

核心职责：
负责提供系统 Web 后端服务。利用 FastAPI 框架实现 RESTful API 接口，并使用多进程/多线程执行器来异步调度视频下载任务。
支持以下核心功能：
1. 全局配置持久化（存储于 data/settings.json，如代理、分辨率）。
2. data/*.json 配置文件的列表、读取、新建、编辑与删除。
3. cookies/ 目录下 Cookie 文件管理（新建、上传、删除），支持并发下载时 Cookie 独占绑定调度。
4. 关联 sqlite 本地数据库（data/sucai.db），支持搜索和分类过滤已下载片段。
5. 异步下载队列调度：并发数等于有效 Cookie 数。每个 worker 独占使用一个 Cookie 并启动 batch_download.py 子进程，实时捕捉其控制台输出并写入日志。
6. 提供本地流式视频预览（映射静态目录 sucai/ 与 static/）。
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
import shutil
import time
import glob
import io
import re
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==================== 目录与路径初始化 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
COOKIES_DIR = os.path.join(BASE_DIR, "cookies")
SUCAI_DIR = os.path.join(BASE_DIR, "sucai")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
LOGS_DIR = os.path.join(DATA_DIR, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(COOKIES_DIR, exist_ok=True)
os.makedirs(SUCAI_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# 默认设置文件
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

# 初始化 SQLite 数据库建表
import db_manager
db_manager.init_db()

def resolve_local_path(path: str) -> str:
    """
    智能跨平台路径解析函数。
    解决在 Windows 上下载并写入 SQLite 的绝对路径，在 Linux Docker 环境中无法被 os.path.exists() 检测到的问题。
    """
    if not path:
        return ""
    # 统一化斜杠
    path = path.replace("\\", "/")
    
    # 如果路径在当前环境下直接存在，直接返回
    if os.path.exists(path):
        return path
        
    # 针对 Docker 容器，若原始绝对路径在 Windows (如 D:/daima/youtube下载/sucai/...)，
    # 则通过定位关键字，将其重组为相对于当前 BASE_DIR 的 Linux 路径
    for folder in ["sucai", "downloads", "temp_downloads"]:
        marker = f"/{folder}/"
        if marker in path:
            relative_part = path.split(marker, 1)[1]
            alt_path = os.path.join(BASE_DIR, folder, relative_part)
            alt_path = alt_path.replace("\\", "/")
            if os.path.exists(alt_path):
                return alt_path
        elif path.startswith(f"{folder}/") or path.startswith(f"./{folder}/"):
            # 兼容已经是相对路径的情况
            sub_path = path.split(f"{folder}/", 1)[1]
            alt_path = os.path.join(BASE_DIR, folder, sub_path)
            alt_path = alt_path.replace("\\", "/")
            if os.path.exists(alt_path):
                return alt_path
                
    return path


# ==================== FastAPI 初始化 ====================
app = FastAPI(title="YouTube 下载器与素材管理系统")

# 跨域设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 配置系统 (Settings) ====================
def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_PATH):
        default = {
            "proxy": "127.0.0.1:7890",
            "resolution": "2k",
            "max_concurrency": 3
        }
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"proxy": "127.0.0.1:7890", "resolution": "2k"}

def save_settings(data: Dict[str, Any]):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

class SettingsModel(BaseModel):
    proxy: str
    resolution: str

@app.get("/api/settings")
def get_settings():
    return load_settings()

@app.post("/api/settings")
def update_settings(settings: SettingsModel):
    current = load_settings()
    current["proxy"] = settings.proxy.strip()
    current["resolution"] = settings.resolution.strip()
    save_settings(current)
    return {"status": "ok", "message": "配置更新成功"}

# ==================== JSON 配置文件管理 ====================
class JsonModel(BaseModel):
    filename: str
    content: Dict[str, Any]

@app.get("/api/jsons")
def list_jsons(
    status: str = "all",
    q: str = "",
    page: int = 1,
    limit: int = 20
):
    """分页获取 data 目录及 processed/ 归档目录下所有的 .json 配置文件及其概要信息"""
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    processed_files = glob.glob(os.path.join(DATA_DIR, "processed", "*.json"))
    
    all_filepaths = []
    for f in files:
        if os.path.basename(f) != "settings.json":
            all_filepaths.append((f, False))
    for f in processed_files:
        all_filepaths.append((f, True))
        
    # 按状态和搜索关键词进行初筛
    filtered_filepaths = []
    for filepath, is_processed in all_filepaths:
        basename = os.path.basename(filepath)
        if status == "pending" and is_processed:
            continue
        if status == "completed" and not is_processed:
            continue
            
        title = basename
        url = ""
        # 快速读取 title/url 供模糊匹配
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                title = data.get("title", basename)
                url = data.get("url", "")
        except Exception:
            pass
            
        if q:
            q_lower = q.lower()
            if q_lower not in basename.lower() and q_lower not in title.lower() and q_lower not in url.lower():
                continue
                
        filtered_filepaths.append((filepath, is_processed))
        
    # 排序
    filtered_filepaths.sort(key=lambda x: os.path.basename(x[0]))
    total = len(filtered_filepaths)
    
    # 切片分页
    offset = (page - 1) * limit
    paginated_filepaths = filtered_filepaths[offset : offset + limit]
    
    result = []
    for filepath, is_processed in paginated_filepaths:
        basename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            clips_count = len(data.get("clips", {})) if isinstance(data.get("clips"), dict) else len(data.get("clips", []))
            # 统计已下载成功的 clips
            db_conn = sqlite3.connect(db_manager.DB_PATH)
            db_conn.row_factory = sqlite3.Row
            cursor = db_conn.cursor()
            # 尝试提取 video_id
            video_url = data.get("url", "")
            video_id = ""
            if video_url:
                import batch_download
                video_id = batch_download.extract_video_id(video_url)
            
            db_completed = 0
            if video_id:
                cursor.execute("SELECT count(*) as cnt FROM clips WHERE video_id = ?", (video_id,))
                row = cursor.fetchone()
                if row:
                    db_completed = row["cnt"]
            db_conn.close()

            result.append({
                "filename": basename,
                "url": video_url,
                "title": data.get("title", basename),
                "clips_count": clips_count,
                "completed_count": db_completed,
                "status": "completed" if db_completed >= clips_count and clips_count > 0 else "pending",
                "is_processed": is_processed
            })
        except Exception as e:
            result.append({
                "filename": basename,
                "url": "",
                "title": f"解析失败 ({basename})",
                "clips_count": 0,
                "completed_count": 0,
                "status": "error",
                "error": str(e),
                "is_processed": is_processed
            })
    return {
        "jsons": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/jsons/{filename}")
def get_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        processed_path = os.path.join(DATA_DIR, "processed", filename)
        if os.path.exists(processed_path):
            path = processed_path
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取失败: {e}")

@app.get("/api/prompts/{filename}")
def get_raw_prompt(filename: str):
    """获取 prompt.md 或 prompt2.md 的原始文本内容供前端一键复制"""
    if filename not in ["prompt.md", "prompt2.md"]:
        raise HTTPException(status_code=400, detail="非法提示词文件名")
    path = os.path.join(BASE_DIR, "prompts", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="提示词文件不存在")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取提示词失败: {e}")

@app.post("/api/jsons")
def save_json(data: JsonModel):
    filename = data.filename.strip()
    if not filename.endswith(".json"):
        filename += ".json"
    path = os.path.join(DATA_DIR, filename)
    processed_path = os.path.join(DATA_DIR, "processed", filename)
    # 如果已存在于已完成归档中，则覆盖归档中的文件以保持一致
    if not os.path.exists(path) and os.path.exists(processed_path):
        path = processed_path
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data.content, f, indent=4, ensure_ascii=False)
        return {"status": "ok", "message": "保存成功", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")

@app.delete("/api/jsons/{filename}")
def delete_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    processed_path = os.path.join(DATA_DIR, "processed", filename)
    target = None
    if os.path.exists(path):
        target = path
    elif os.path.exists(processed_path):
        target = processed_path
        
    if not target:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        os.remove(target)
        return {"status": "ok", "message": "删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")

# ==================== COOKIES 文件管理 ====================
@app.get("/api/cookies")
def list_cookies():
    # 扫描 cookies 目录下所有 .txt 文件
    txt_files = glob.glob(os.path.join(COOKIES_DIR, "*.txt"))
    # 同时兼容根目录的默认文本 Cookie
    root_default = os.path.join(BASE_DIR, "0d24036b-958b-437b-a104-e9b0338dafc6.txt")
    result = []
    
    # 加入默认 root cookie
    if os.path.exists(root_default):
        result.append({
            "filename": os.path.basename(root_default),
            "size": os.path.getsize(root_default),
            "is_default": True,
            "path": root_default
        })
        
    for filepath in txt_files:
        basename = os.path.basename(filepath)
        result.append({
            "filename": basename,
            "size": os.path.getsize(filepath),
            "is_default": False,
            "path": filepath
        })
    return result

@app.post("/api/cookies")
def create_cookie(filename: str, content: str):
    if not filename.endswith(".txt"):
        filename += ".txt"
    path = os.path.join(COOKIES_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content.strip() + "\n")
        return {"status": "ok", "message": "Cookie 保存成功", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")

@app.post("/api/cookies/upload")
async def upload_cookie(file: UploadFile = File(...)):
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="必须上传 .txt 文本文件")
    path = os.path.join(COOKIES_DIR, file.filename)
    try:
        with open(path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"status": "ok", "message": "Cookie 上传成功", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")

@app.post("/api/cookies/rename")
def rename_cookie(filename: str, new_filename: str):
    if not new_filename.endswith(".txt"):
        new_filename += ".txt"
        
    old_path = os.path.join(COOKIES_DIR, filename)
    new_path = os.path.join(COOKIES_DIR, new_filename)
    
    old_root_path = os.path.join(BASE_DIR, filename)
    new_root_path = os.path.join(BASE_DIR, new_filename)
    
    target_old = None
    target_new = None
    
    if os.path.exists(old_path):
        target_old = old_path
        target_new = new_path
    elif os.path.exists(old_root_path):
        target_old = old_root_path
        target_new = new_root_path
        
    if not target_old:
        raise HTTPException(status_code=404, detail="Cookie 文件不存在")
        
    if os.path.exists(target_new) and target_old != target_new:
        raise HTTPException(status_code=400, detail="同名 Cookie 文件已存在")
        
    try:
        os.rename(target_old, target_new)
        return {"status": "ok", "message": "Cookie 重命名成功", "filename": new_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重命名失败: {e}")

@app.delete("/api/cookies/{filename}")
def delete_cookie(filename: str):
    path = os.path.join(COOKIES_DIR, filename)
    root_path = os.path.join(BASE_DIR, filename)
    
    target_path = None
    if os.path.exists(path):
        target_path = path
    elif os.path.exists(root_path):
        target_path = root_path
        
    if not target_path:
        raise HTTPException(status_code=404, detail="Cookie 文件不存在")
    try:
        os.remove(target_path)
        return {"status": "ok", "message": "删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")

# ==================== 素材库检索 API ====================
@app.get("/api/clips")
def list_clips(
    q: Optional[str] = None, 
    subject: Optional[str] = None, 
    tag: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    """
    模糊检索 SQLite 数据库中的片段，并支持分类过滤与分页。
    """
    conn = sqlite3.connect(db_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    where_clause = ""
    params = []
    
    if subject:
        where_clause += " AND c.subject = ?"
        params.append(subject)
    if tag:
        where_clause += " AND c.tag LIKE ?"
        params.append(f"%{tag}%")
        
    if q:
        # 支持用英文逗号 (,) 或中文逗号 (，) 拆分多关键词进行 AND 组合检索
        keywords = [k.strip() for k in re.split(r'[,，]', q) if k.strip()]
        for kw in keywords:
            where_clause += """ AND (
                c.description LIKE ? OR 
                c.subject LIKE ? OR 
                c.tag LIKE ? OR 
                c.action LIKE ? OR 
                c.scene LIKE ? OR
                c.keywords LIKE ? OR
                c.camera_movement LIKE ? OR
                c.atmosphere LIKE ? OR
                c.color_tone LIKE ? OR
                v.title LIKE ?
            )"""
            p_str = f"%{kw}%"
            params.extend([p_str] * 10)
            
    # 计算匹配总数
    count_query = "SELECT COUNT(*) as total FROM clips c LEFT JOIN videos v ON c.video_id = v.video_id WHERE 1=1" + where_clause
    try:
        cursor.execute(count_query, params)
        total = cursor.fetchone()["total"]
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"统计失败: {e}")
        
    query = """
        SELECT c.*, v.title as video_title, v.source_url
        FROM clips c
        LEFT JOIN videos v ON c.video_id = v.video_id
        WHERE 1=1
    """ + where_clause + " ORDER BY c.created_at DESC LIMIT ? OFFSET ?"
    
    offset = (page - 1) * limit
    
    try:
        cursor.execute(query, params + [limit, offset])
        rows = cursor.fetchall()
        
        result = []
        for r in rows:
            # 转换成前端能支持的结构
            local_path = r["local_path"]
            resolved_path = resolve_local_path(local_path)
            
            web_path = ""
            if resolved_path and os.path.exists(resolved_path):
                # 取得相对于 sucai/ 的路径
                rel_path = os.path.relpath(resolved_path, SUCAI_DIR)
                # 转换成静态暴露的 URL 路径
                web_path = f"/stream/{rel_path.replace(os.sep, '/')}"

            result.append({
                "video_id": r["video_id"],
                "clip_id": r["clip_id"],
                "video_title": r["video_title"],
                "source_url": r["source_url"],
                "duration": r["duration"],
                "tag": r["tag"],
                "subject": r["subject"],
                "scene": r["scene"],
                "action": r["action"],
                "camera_movement": r["camera_movement"],
                "atmosphere": r["atmosphere"],
                "color_tone": r["color_tone"],
                "description": r["description"],
                "use_case": r["use_case"],
                "keywords": r["keywords"],
                "resolution": r["resolution"],
                "fps": r["fps"],
                "aspect_ratio": r["aspect_ratio"],
                "web_path": web_path,
                "local_path": local_path,
                "created_at": r["created_at"]
            })
        return {
            "clips": result,
            "total": total,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库检索失败: {e}")
    finally:
        conn.close()

@app.get("/api/tags")
def get_all_tags():
    """
    获取 SQLite 数据库中 clips 表的所有去重非空 tag 字段。
    """
    conn = sqlite3.connect(db_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT tag FROM clips WHERE tag IS NOT NULL AND tag != '' ORDER BY tag ASC")
        rows = cursor.fetchall()
        return [row["tag"] for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取标签失败: {e}")
    finally:
        conn.close()

@app.get("/api/clips/thumbnail")
def get_clip_thumbnail(path: str):
    """
    实时调用 FFmpeg 截取视频首帧，并流式输出为 JPEG 格式图片（不保存临时文件到本地，且支持懒加载）。
    """
    # 跨平台路径智能解析
    resolved_path = resolve_local_path(path)
        
    if not resolved_path or not os.path.exists(resolved_path):
        raise HTTPException(status_code=404, detail="视频文件不存在，无法提取缩略图")
    
    # 构建 ffmpeg 抽取首帧命令
    # -ss 0.0 快速定位开头
    # -i 输入路径
    # -vframes 1 抽取 1 帧
    # -f image2 输出图像格式
    # -c:v mjpeg 编码为 JPEG
    # pipe:1 输出到 stdout 管道
    cmd = [
        "ffmpeg", "-y",
        "-ss", "0.0",
        "-i", resolved_path,
        "-vframes", "1",
        "-f", "image2",
        "-c:v", "mjpeg",
        "pipe:1"
    ]
    
    try:
        # 兼容 Windows 系统的子进程无窗口拉起
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo
        )
        
        stdout, stderr = process.communicate(timeout=8.0)
        
        if process.returncode != 0 or not stdout:
            raise HTTPException(status_code=500, detail="首帧画面提取失败")
            
        return StreamingResponse(io.BytesIO(stdout), media_type="image/jpeg")
    except subprocess.TimeoutExpired:
        if process:
            process.kill()
        raise HTTPException(status_code=504, detail="首帧画面提取超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"首帧抽取异常: {e}")

# ==================== 异步下载调度系统 ====================
# 全局下载状态字典
# 键为 JSON 文件名，值为：{"status": "waiting"|"running"|"completed"|"failed", "cookie": str, "start_time": float, "pid": int, "logs": str}
download_status: Dict[str, Dict[str, Any]] = {}
download_queue: List[str] = []
active_workers: Dict[str, subprocess.Popen] = {}
# 锁对象用于线程安全操作
status_lock = threading.Lock()

def read_subprocess_logs(json_filename: str, process: subprocess.Popen, log_file_path: str):
    """循环读取子进程控制台输出，写入全局状态并追加至独立日志文件"""
    with open(log_file_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n\n=== DOWNLOAD START AT {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        lf.flush()
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            decoded_line = line.decode("utf-8", errors="ignore")
            # 实时写入独立日志文件
            lf.write(decoded_line)
            lf.flush()
            
            with status_lock:
                if json_filename in download_status:
                    download_status[json_filename]["logs"] += decoded_line
                    # 限制内存日志行数以防溢出
                    log_lines = download_status[json_filename]["logs"].splitlines()
                    if len(log_lines) > 500:
                        download_status[json_filename]["logs"] = "\n".join(log_lines[-500:]) + "\n"

    process.wait()
    
    with status_lock:
        if json_filename in active_workers:
            del active_workers[json_filename]
        
        status = "completed" if process.returncode == 0 else "failed"
        if json_filename in download_status:
            download_status[json_filename]["status"] = status
            download_status[json_filename]["end_time"] = time.time()
            download_status[json_filename]["exit_code"] = process.returncode
            
            # 追加进程退出说明
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(f"\n=== PROCESS EXITED WITH CODE {process.returncode} ({status}) ===\n")

    # 触发下载调度轮询以启动下一个任务
    trigger_queue_dispatcher()

def trigger_queue_dispatcher():
    """核心队列分发调度器。每次有任务结束或新加任务时调用"""
    with status_lock:
        # 1. 扫描当前可用的全部 Cookie
        cookie_list = list_cookies()
        available_cookies = [c["path"] for c in cookie_list]
        
        # 如果一个 Cookie 都没有，默认使用空路径(直连模式或浏览器读取)
        if not available_cookies:
            # 看看能不能直接并发（默认给最多1个）
            max_workers = 1
            available_cookies = [None]
        else:
            max_workers = len(available_cookies)
            
        # 2. 检查当前正在运转的 Worker 数量
        current_running = len(active_workers)
        
        if current_running >= max_workers:
            return  # 达到并发上限，等待
            
        # 3. 找出当前已经被分配占用的 Cookie 路径
        leased_cookies = set()
        for filename, info in download_status.items():
            if info["status"] == "running" and info.get("cookie"):
                leased_cookies.add(info["cookie"])
                
        # 4. 从队列中依次取出任务进行分配
        while download_queue and len(active_workers) < max_workers:
            # 找到一个空闲的 Cookie
            free_cookie = None
            for c_path in available_cookies:
                if c_path not in leased_cookies:
                    free_cookie = c_path
                    break
                    
            if free_cookie is None and available_cookies != [None]:
                # 虽然还有并发槽，但没有空闲的 Cookie 可分租了
                break
                
            json_filename = download_queue.pop(0)
            
            # 锁定该 Cookie 路径
            if free_cookie:
                leased_cookies.add(free_cookie)
                
            # 启动子进程时，动态定位 JSON 真实存在的位置（可能在 data/ 或 data/processed/ 归档区）
            json_path = os.path.join(DATA_DIR, json_filename)
            if not os.path.exists(json_path):
                processed_path = os.path.join(DATA_DIR, "processed", json_filename)
                if os.path.exists(processed_path):
                    json_path = processed_path
            settings = load_settings()
            proxy_str = settings.get("proxy", "").strip()
            res_str = settings.get("resolution", "2k").strip()
            
            # 动态从 JSON 文件中获取分类文件夹命名 (group_dir)
            json_group_dir = None
            try:
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as jf:
                        config_data = json.load(jf)
                        json_group_dir = config_data.get("group_dir", "").strip()
            except Exception as j_err:
                print(f"[WARNING] 读取 JSON 自带分组分类失败: {j_err}")
                
            cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "batch_download.py"),
                json_path,
                "-p", proxy_str,
                "-r", res_str,
                "-o", SUCAI_DIR,
                "-t", DOWNLOADS_DIR
            ]
            
            if json_group_dir:
                cmd.extend(["-d", json_group_dir])
            
            # 如果分租了 Cookie，加入 -c 参数
            if free_cookie:
                cmd.extend(["-c", free_cookie])
            else:
                # 看看是否有根目录的默认 cookie
                root_default = os.path.join(BASE_DIR, "0d24036b-958b-437b-a104-e9b0338dafc6.txt")
                if os.path.exists(root_default):
                    cmd.extend(["-c", root_default])
                
            log_file_path = os.path.join(LOGS_DIR, f"{os.path.splitext(json_filename)[0]}.log")
            
            try:
                # 以管道输出的方式异步拉起 Python 下载子进程
                # 兼容 Windows 系统的子进程无窗口拉起
                startupinfo = None
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    
                # 强制子进程以 UTF-8 编码进行 I/O，完美解决 Windows CLI 默认 GBK 导致前端 Mojibake 乱码问题
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=BASE_DIR,
                    startupinfo=startupinfo,
                    env=env
                )
                
                active_workers[json_filename] = process
                
                download_status[json_filename].update({
                    "status": "running",
                    "cookie": free_cookie,
                    "start_time": time.time(),
                    "pid": process.pid,
                    "cmd": " ".join(cmd)
                })
                
                # 开启线程读取进度流
                t = threading.Thread(
                    target=read_subprocess_logs, 
                    args=(json_filename, process, log_file_path),
                    daemon=True
                )
                t.start()
                
            except Exception as e:
                download_status[json_filename].update({
                    "status": "failed",
                    "logs": f"进程拉起失败: {e}\n",
                    "end_time": time.time()
                })
                if free_cookie in leased_cookies:
                    leased_cookies.remove(free_cookie)

@app.post("/api/download/start")
def start_download(filename: str):
    path = os.path.join(DATA_DIR, filename)
    processed_path = os.path.join(DATA_DIR, "processed", filename)
    if not os.path.exists(path) and not os.path.exists(processed_path):
        raise HTTPException(status_code=404, detail="指定的配置文件不存在")
        
    with status_lock:
        # 重置或初始化状态
        download_status[filename] = {
            "status": "waiting",
            "cookie": None,
            "start_time": 0.0,
            "end_time": 0.0,
            "pid": 0,
            "logs": "排队等待中...\n"
        }
        
        if filename not in download_queue:
            download_queue.append(filename)
            
    # 异步触发分发调度
    threading.Thread(target=trigger_queue_dispatcher, daemon=True).start()
    return {"status": "ok", "message": f"任务已成功加入下载队列: {filename}"}

@app.post("/api/download/start_all")
def start_all_downloads():
    """扫描所有 pending 状态 of JSON 并加入下载队列"""
    json_list = list_jsons(limit=100000)["jsons"]
    added = []
    
    with status_lock:
        for item in json_list:
            filename = item["filename"]
            # 只要不是 100% 完成的且没在队列中没在运行中的，就加入
            is_active = (filename in download_queue) or (filename in active_workers)
            if item["completed_count"] < item["clips_count"] and not is_active:
                download_status[filename] = {
                    "status": "waiting",
                    "cookie": None,
                    "start_time": 0.0,
                    "end_time": 0.0,
                    "pid": 0,
                    "logs": "排队等待中...\n"
                }
                download_queue.append(filename)
                added.append(filename)
                
    if added:
        threading.Thread(target=trigger_queue_dispatcher, daemon=True).start()
        
    return {"status": "ok", "message": f"已成功扫描并向下载队列中添加了 {len(added)} 个挂起任务", "added": added}

@app.get("/api/download/status")
def get_download_status():
    with status_lock:
        # 复制状态以提供给前端
        result = {}
        for k, v in download_status.items():
            result[k] = {
                "status": v["status"],
                "cookie": os.path.basename(v["cookie"]) if v.get("cookie") else None,
                "start_time": v["start_time"],
                "end_time": v["end_time"],
                "pid": v["pid"]
            }
        return {
            "active_workers_count": len(active_workers),
            "queue_len": len(download_queue),
            "queue": download_queue,
            "jobs": result
        }

@app.get("/api/download/logs")
def get_download_logs(filename: str):
    """读取指定配置文件的全量输出日志"""
    # 优先读文件日志
    log_file_path = os.path.join(LOGS_DIR, f"{os.path.splitext(filename)[0]}.log")
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                return {"filename": filename, "logs": f.read()}
        except Exception:
            pass
            
    with status_lock:
        if filename in download_status:
            return {"filename": filename, "logs": download_status[filename]["logs"]}
        else:
            return {"filename": filename, "logs": "暂无该任务的下载执行日志记录。\n"}

@app.post("/api/download/kill")
def kill_download(filename: str):
    """中止某个下载进程"""
    with status_lock:
        if filename in download_queue:
            download_queue.remove(filename)
            if filename in download_status:
                download_status[filename]["status"] = "failed"
                download_status[filename]["logs"] += "\n[!] 任务在排队时被手动取消。\n"
            return {"status": "ok", "message": "已从排队队列中移除任务"}
            
        if filename in active_workers:
            process = active_workers[filename]
            try:
                # 杀死子进程
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                else:
                    process.kill()
                return {"status": "ok", "message": "正在终止后台下载进程..."}
            except Exception as e:
                return {"status": "error", "message": f"杀死子进程失败: {e}"}
                
@app.post("/api/system/restart")
def restart_system(background_tasks: BackgroundTasks):
    """
    优雅重启后端服务。通过触发退出，使 Docker or systemd 自动重启容器/服务。
    """
    def shutdown():
        time.sleep(1.0)
        print("[*] 正在执行服务重启请求...")
        os._exit(0)
        
    background_tasks.add_task(shutdown)
    return {"status": "ok", "message": "已成功发出重启指令，服务将在 1 秒后自动重启... 请稍后刷新页面！"}

# ==================== 静态文件路由与映射 ====================
# 映射已下载视频素材目录到 /stream
app.mount("/stream", StaticFiles(directory=SUCAI_DIR), name="sucai")

# 映射前端静态网页资源
STATIC_WEB_DIR = os.path.join(BASE_DIR, "static")
if os.path.exists(STATIC_WEB_DIR):
    app.mount("/", StaticFiles(directory=STATIC_WEB_DIR, html=True), name="static")
else:
    @app.get("/", response_class=HTMLResponse)
    def index_fallback():
        return "<h1>FastAPI 正在运行！请在此根目录创建 static/ 文件夹以及 index.html 以启用可视化界面。</h1>"

# 调试自拉起
if __name__ == "__main__":
    import uvicorn
    # 初始化
    load_settings()
    print("[*] 正在本地启动 FastAPI 后端服务器...")
    print("[*] 请在浏览器中打开: http://127.0.0.1:7878")
    uvicorn.run("web_app:app", host="127.0.0.1", port=7878, reload=True)
