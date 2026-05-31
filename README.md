# YouTube Video Clip Downloader (yt-dlp)

这是一个专为**下载 YouTube 视频特定时间段**（例如 2 小时的视频中仅下载 10 到 20 分钟）而设计的高效、模块化下载工具。

通过利用 `yt-dlp` 的 `download_ranges`（HTTP Range 请求分段下载）和 `ffmpeg` 进行精细切割合并，该工具**无需下载整个视频文件**，即可秒级提取出精准的视频片段，能为您**节省大量的网络流量和等待时间**。

---

## ✨ 核心特性

1. **流量极省**：仅通过 HTTP Range 分段请求下载所需时长对应的视频数据分片，零流量浪费。
2. **格式选择策略**：默认最高下载 **2K (1440p)** 分辨率，若视频不支持 2K 则自动向下兼容提取 1080p、720p，保障最高画质的同时兼顾小体积。
3. **安全网络代理**：内置 Fail-Fast 连通性测试。默认连接 Clash/Clash Verge 的 `127.0.0.1:7890` 代理，检测到代理不可用时会立即报错并提供详尽引导。
4. **Cookie 权限支持**：自动附带 Netscape 格式的 Cookie（预置文件 `0d24036b-958b-437b-a104-e9b0338dafc6.txt`），可直接下载包含会员专享、私有或年龄限制的视频。
5. **双向时间解析**：支持多种直观的人类可读起止时间输入，例如 `10:00` (10分钟)、`01:30:15` (1时30分15秒) 或 `600` (秒数)。
6. **自动溢出截断**：
   * 开始时间大于总时长：抛出异常退出。
   * 结束时间超出视频实际结尾：自动**安全截断至视频末尾**并成功下载。

---

## 📂 文件职责说明

项目遵循高度模块化设计（无功能堆积），代码组织结构如下：

* **[clip_parser.py](clip_parser.py)**：时间字符串（分:秒、时:分:秒）的数学转换与边界对齐验证器。
* **[youtube_downloader.py](youtube_downloader.py)**：底层 `yt-dlp` 的选项配置、代理网络连接诊断与分段下载核心。
* **[download_clip.py](download_clip.py)**：命令行界面（CLI）控制器，用于收集参数并展示清晰的日志信息。
* **[test_download.py](test_download.py)**：一键式快速自动化集成测试脚本（下载特定视频的 10 秒到 20 秒片段）。
* **[download_clip.bat](download_clip.bat)**：Windows 双击即用的交互式批处理对话脚本。

---

## 🚀 快速上手使用

### 方式 1：执行自动化集成测试（推荐）
在项目目录下直接运行专用的测试脚本，以下载测试视频中 `10秒` 至 `20秒` 的 2K 片段：
```bash
.\venv\Scripts\python test_download.py
```
*下载成功后，生成的文件将保存在 `downloads` 文件夹中。*

### 方式 2：使用交互式双击运行（极简）
在 Windows 资源管理器中，直接**双击运行 `download_clip.bat`**：
1. 根据引导输入 YouTube 视频 URL。
2. 输入开始时间（如 `10:00`）。
3. 输入结束时间（如 `20:00`）。
4. 选择分辨率限制选项。
5. 脚本将自动完成所有下载和精准切割！

### 方式 3：通过命令行运行（极客）
使用 `download_clip.py` 主程序并传入自定义参数：
```bash
# 例子 1：下载视频的 10分钟 至 20分钟 片段，限制最高 1080p 分辨率
.\venv\Scripts\python download_clip.py "https://www.youtube.com/watch?v=TnG89ChN9LQ" -s "10:00" -e "20:00" -r "1080p"

# 例子 2：从 1小时30分 开始下载至视频结尾，不使用代理
.\venv\Scripts\python download_clip.py "https://www.youtube.com/watch?v=TnG89ChN9LQ" -s "01:30:00" -p ""
```

### 方式 4：使用 Docker 极速容器化部署 (推荐 🖥️)

您可以通过以下两种极简的一行命令方式快速启动带有顶级图形控制中心的 Web 后端服务器，所有的数据和物理切片素材均将持久化保存在本地。

#### 方案 A：通过 Docker Compose 一键本地构建拉起 (最便捷)
如果您已经克隆了本项目，直接在项目根目录下执行以下单行命令：
```bash
docker compose up -d --build
```
启动成功后，即可在浏览器中访问：`http://localhost:7878` 体验完整的智能控制中心。

#### 方案 B：使用预构建的 GitHub 镜像一键拉起 (无需下载源码 - 🚀 一行命令部署)
GitHub 正在为您自动构建并将最新容器推送到 GitHub 容器托管服务（GHCR）。您可以在没有源码的全新电脑上，直接运行以下一行命令拉起最新的预构建版本：

* **Windows (PowerShell 终端)**:
```powershell
docker run -d --name youtube-downloader -p 7878:7878 -v ${PWD}/data:/app/data -v ${PWD}/cookies:/app/cookies -v ${PWD}/sucai:/app/sucai -v ${PWD}/downloads:/app/downloads -v ${PWD}/temp_downloads:/app/temp_downloads -v ${PWD}/prompts:/app/prompts --add-host=host.docker.internal:host-gateway --restart unless-stopped ghcr.io/zerohiz/ytxiazai:latest
```

* **Linux / macOS / Linux Server (Bash 终端)**:
```bash
docker run -d --name youtube-downloader -p 7878:7878 -v $(pwd)/data:/app/data -v $(pwd)/cookies:/app/cookies -v $(pwd)/sucai:/app/sucai -v $(pwd)/downloads:/app/downloads -v $(pwd)/temp_downloads:/app/temp_downloads -v $(pwd)/prompts:/app/prompts --add-host=host.docker.internal:host-gateway --restart unless-stopped ghcr.io/zerohiz/ytxiazai:latest
```

> **💡 说明**：
> - 端口占用：容器内服务运行在 **7878** 端口。
> - 宿主机代理访问：通过配置 `--add-host` 并在 Web 界面代理处填写 `http://host.docker.internal:7890`，Docker 容器即可安全无缝地调用您宿主机本地（如 Clash / v2ray）的科学上网代理。

---

## 🛠️ 环境依赖项

1. **Python**: 3.7+ (已在本地虚拟环境 `venv` 中配置好)
2. **FFmpeg**: 用于底层的视频剪裁、音频和视频无损合并。(本系统已原生配置好，支持全球标准格式)
3. **网络环境**: 确保您的代理代理客户端已在 `127.0.0.1:7890` 开放，或者通过参数自定义代理。
