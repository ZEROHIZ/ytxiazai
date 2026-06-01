# API 接口文档 (API_DOC.md)

> **文件职责**：本文档详细说明了“YouTube 下载与素材管理系统”后端所支持的全部 RESTful API 接口。它为前端网页交互、脚本调用及系统维护提供了完整的参考规范。

---

# YouTube 下载与素材管理系统 API 接口文档

本项目后端基于 **FastAPI** 框架构建，对外提供 RESTful API 接口，并使用多进程/多线程执行器来异步调度视频下载任务、管理配置文件、管理 Cookies 以及提供素材库的高效检索与流媒体服务。

---

## 1. 配置系统 API (Settings)

### 获取全局配置
* **接口地址**: `GET /api/settings`
* **接口描述**: 获取系统的全局配置参数（如代理、默认分辨率、最大并发数等），保存在 `data/settings.json` 中。
* **返回示例**:
  ```json
  {
      "proxy": "127.0.0.1:7890",
      "resolution": "2k",
      "max_concurrency": 3
  }
  ```

### 更新全局配置
* **接口地址**: `POST /api/settings`
* **Body 格式**: `JSON`
* **Body 参数**:
  ```json
  {
      "proxy": "127.0.0.1:7890",
      "resolution": "2k"
  }
  ```
* **返回示例**:
  ```json
  {
      "status": "ok",
      "message": "配置更新成功"
  }
  ```

---

## 2. JSON 配置文件管理 API

### 获取 JSON 配置列表（支持分页与搜索）
* **接口地址**: `GET /api/jsons`
* **Query 参数**:
  * `status` (string, 可选): 任务过滤，`all` (全部，默认)、`pending` (待处理/下载中)、`completed` (已完成)。
  * `q` (string, 可选): 模糊检索关键字，可根据文件名、视频标题、URL 进行筛选。
  * `page` (int, 默认 1): 当前页码。
  * `limit` (int, 默认 20): 每页限制数量。
* **接口描述**: 分页获取 `data` 目录及已完成归档目录 `data/processed/` 下的所有配置文件的概要与实时状态。
* **返回示例**:
  ```json
  {
      "jsons": [
          {
              "filename": "demo_video.json",
              "url": "https://www.youtube.com/watch?v=xxxx",
              "title": "测试视频标题",
              "clips_count": 5,
              "completed_count": 3,
              "status": "running",
              "is_processed": false
          }
      ],
      "total": 1,
      "page": 1,
      "limit": 20
  }
  ```

### 获取单个 JSON 配置详情
* **接口地址**: `GET /api/jsons/{filename}`
* **Path 参数**: `filename` (如 `example.json`)
* **返回示例**: 返回该 JSON 文件的完整配置内容（包含 clips 裁剪片段的定义信息）。

### 新建/保存 JSON 配置文件
* **接口地址**: `POST /api/jsons`
* **Body 格式**: `JSON`
* **Body 参数**:
  ```json
  {
      "filename": "example.json",
      "content": {
          "title": "视频标题",
          "url": "https://youtube...",
          "clips": []
      }
  }
  ```
* **返回示例**:
  ```json
  {
      "status": "ok",
      "message": "保存成功",
      "filename": "example.json"
  }
  ```

### 删除指定 JSON 配置文件
* **接口地址**: `DELETE /api/jsons/{filename}`
* **Path 参数**: `filename`
* **返回示例**: `{"status": "ok", "message": "删除成功"}`

### 获取原始 AI 提示词内容
* **接口地址**: `GET /api/prompts/{filename}`
* **Path 参数**: `filename` (仅支持 `prompt.md` 或 `prompt2.md`)
* **接口描述**: 获取预设的 Markdown 格式 AI 提示词原始文本内容，用于前端界面方便用户一键复制去提炼视频片段。

---

## 3. COOKIES 文件管理 API

多账号/多 Cookie 是本系统并发下载的基础。下载引擎将轮询可用 Cookie 并在下载时独占绑定。

### 获取 Cookies 列表
* **接口地址**: `GET /api/cookies`
* **接口描述**: 获取 `cookies/` 目录以及项目根目录下可用的全部 Cookie `.txt` 文本文件列表。

### 新建/保存 Cookie
* **接口地址**: `POST /api/cookies`
* **Query 参数**: `filename` (如 `account1.txt`)
* **Body (Plain Text)**: 完整的 Netscape 格式 Cookie 文本内容。

### 上传 Cookie 文件
* **接口地址**: `POST /api/cookies/upload`
* **Body 格式**: `multipart/form-data` (表单字段为 `file`)
* **接口描述**: 允许直接从前端拖拽或选择 `.txt` 文件上传存入 `cookies/` 目录下。

### 重命名 Cookie
* **接口地址**: `POST /api/cookies/rename`
* **Query 参数**:
  * `filename`: 旧文件名
  * `new_filename`: 新文件名

### 删除 Cookie
* **接口地址**: `DELETE /api/cookies/{filename}`

---

## 4. 素材库检索与预览 API (SQLite + FFmpeg)

### 模糊检索视频片段 (Clips)
* **接口地址**: `GET /api/clips`
* **Query 参数**:
  * `q` (string, 可选): 模糊检索关键字。支持以中/英文逗号分隔的多关键词，进行 `AND` 组合检索。检索覆盖视频标题、片段描述、主题、动作、画面镜运、色调、氛围等10个维度。
  * `subject` (string, 可选): 精确过滤特定主题。
  * `tag` (string, 可选): 精确过滤特定标签。
  * `page` (int, 默认 1): 当前页码。
  * `limit` (int, 默认 20): 每页限制数量。
* **返回示例**:
  ```json
  {
      "clips": [
      {
          "video_id": "video_12345",
          "clip_id": "clip_01",
          "video_title": "测试视频",
          "source_url": "https://www.youtube.com/watch?v=xxxx",
          "duration": 15.5,
          "tag": "空镜",
          "subject": "城市风光",
          "scene": "户外街道",
          "action": "车辆行驶",
          "camera_movement": "摇移 (Pan)",
          "atmosphere": "宁静",
          "color_tone": "暖色调",
          "description": "一段清晨城市风光的空镜画面",
          "use_case": "转场素材",
          "keywords": "城市, 清晨, 空镜, 延时",
          "resolution": "1920x1080",
          "fps": 30.0,
          "aspect_ratio": "16:9",
          "web_path": "/stream/城市风光/clip_01.mp4",
          "local_path": "d:/daima/youtube下载/sucai/城市风光/clip_01.mp4",
          "created_at": "2026-05-31 20:00:00"
      }
      ],
      "total": 1,
      "page": 1,
      "limit": 20
  }
  ```

### 获取所有去重的素材标签 (Tags)
* **接口地址**: `GET /api/tags`
* **接口描述**: 从已成功下载的片段数据中提炼所有现存的去重 Tag，方便前端做筛选过滤器。

### 实时视频首帧缩略图提取 (FFmpeg 管道流)
* **接口地址**: `GET /api/clips/thumbnail`
* **Query 参数**: `path` (视频的本地路径)
* **接口描述**: 使用 `ffmpeg` 进程实时定位至首帧 `0.0` 秒并提取为 `image/jpeg` 格式的图片以标准二进制流形式返回。无物理缓存，支持前端的高效图片懒加载。

---

## 5. 异步下载调度系统 API

### 开始/入队指定下载任务
* **接口地址**: `POST /api/download/start`
* **Query 参数**: `filename` (JSON 配置文件名)
* **接口描述**: 将此任务加入后台排队队列，系统会自动通过 Cookie 轮询机制唤醒空闲的并发 worker 并启动 `batch_download.py` 执行下载。

### 批量加入所有待下载任务
* **接口地址**: `POST /api/download/start_all`
* **接口描述**: 自动扫描系统中所有存在未下载完成片段的 JSON 任务，并一键将其全部列队排产。

### 获取当前下载队列与状态
* **接口地址**: `GET /api/download/status`
* **返回示例**:
  ```json
  {
      "active_workers_count": 1,
      "queue_len": 0,
      "queue": [],
      "jobs": {
          "demo.json": {
              "status": "running",
              "cookie": "account1.txt",
              "start_time": 1717154200.0,
              "end_time": 0.0,
              "pid": 12345
          }
      }
  }
  ```

### 获取任务的实时/历史全量日志
* **接口地址**: `GET /api/download/logs`
* **Query 参数**: `filename` (JSON 文件名)
* **接口描述**: 从 `data/logs/{filename}.log` 文件（若存在）或内存缓冲区中提取该下载子进程的全部控制台输出（完美解除了乱码风险的 UTF-8 标准输出）。

### 终止或移除排队中的下载任务
* **接口地址**: `POST /api/download/kill`
* **Query 参数**: `filename`
* **接口描述**: 对正在下载的任务将采用底层进程树强制 kill（在 Windows 上执行 `taskkill`，Linux 执行 `kill`），对排队中任务直接移出队列。

---

## 6. 系统管理 API

### 优雅重启后端服务
* **接口地址**: `POST /api/system/restart`
* **接口描述**: 通过 FastAPI 后台任务在一秒后向系统发底层 `_exit(0)` 指令。配合 Docker 自动拉起机制（如 `--restart=always`）或 systemd 完成平滑的热重启与配置加载。

---

## 7. 静态资源路由映射与素材文件下载

后端使用 FastAPI 的 `StaticFiles` 模块将本地素材库目录（`sucai/` 文件夹）和前端网页静态目录（`static/` 文件夹）直接映射到 Web 服务中，为视频文件提供了直接的下载与预览通道。

### 视频素材文件下载与播放 (GET)
* **接口地址**: `GET /stream/{relative_path}`
* **Path 参数**: `relative_path` (在 `/api/clips` 接口响应中返回的 `web_path` 字段中剔除 `/stream/` 前缀的部分，如 `风景/樱花/樱花-6-A7NUHDuaGXk.mp4`)
* **接口描述**: 
  1. **素材直接下载**：客户端（如 Python `requests` 脚本、浏览器、下载器等）可以直接向 `http://<服务器IP>:<端口>/stream/{relative_path}` 发起标准的 HTTP `GET` 请求进行视频文件流式下载。
  2. **Range 流式拖拽点播**：此接口原生支持 HTTP Range 请求。当使用 HTML5 播放器（如 `<video>` 标签）预览视频时，可根据视频时间轴自由拖拽进度条，服务器将按需分片（Chunked Range）返回视频数据。
* **实际下载地址拼接规则**:
  在调用 `/api/clips` 获取到片段数据后，直接使用服务器基地址拼接 `web_path` 字段即可：
  ```text
  下载链接 = http://<服务器IP>:7878 + web_path
  例如: http://192.168.110.30:7878/stream/风景/樱花/樱花-6-A7NUHDuaGXk.mp4
  ```

### 可视化前端界面 (GET)
* **接口地址**: `GET /`
* **接口描述**: 映射本地 `static/` 文件夹。用户在浏览器中直接输入 `http://<服务器IP>:7878/` 时，将自动装载前端 UI 可视化管理页（即 `index.html`）。
