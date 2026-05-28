@echo off
:: ======================================================
:: download_clip.bat
::
:: 核心职责：
:: 提供一个对 Windows 用户极其友好的、交互式双击启动脚本。
:: 它会主动引导用户输入链接与起止时间，并安全地在本地虚拟环境中启动下载脚本。
::
:: 主要特性：
:: - chcp 65001: 激活 UTF-8 编码，彻底避免 Windows 终端中的中文乱码问题。
:: - 自动补全默认值：回车即可应用默认时间与分辨率。
:: - 尾部 pause 挂起：保证任务结束后窗口不会自动闪退，以便查看保存路径与错误诊断。
:: ======================================================

chcp 65001 > nul
title YouTube Partial Video Clip Downloader

echo ======================================================
echo     YouTube Partial Video Clip Downloader (yt-dlp)
echo ======================================================
echo.

:: 引导用户输入链接
set /p URL="[1/4] 请输入 YouTube 视频 URL 并回车: "
if "%URL%"=="" (
    echo [❌ 错误] 视频链接不能为空！
    goto END
)

:: 引导用户输入开始时间
set /p START_TIME="[2/4] 请输入开始时间 [直接回车默认为 0 秒] (如 10:00 或 600): "
if "%START_TIME%"=="" set START_TIME=0

:: 引导用户输入结束时间
set /p END_TIME="[3/4] 请输入结束时间 [直接回车默认到视频结尾] (如 20:00 或 1200): "

:: 引导用户选择分辨率
echo.
echo [4/4] 请选择最高分辨率限制等级:
echo      [1] 2K (1440p) - 如果视频包含2K则优先下载，否则向下兼容 (推荐)
echo      [2] 1080p      - 高清格式限制
echo      [3] 720p       - 节省流量格式限制
echo.
set /p RES_CHOICE="请输入对应选项的数字 [默认 1]: "
set RESOLUTION=2k
if "%RES_CHOICE%"=="2" set RESOLUTION=1080p
if "%RES_CHOICE%"=="3" set RESOLUTION=720p

echo.
echo ======================================================
echo [*] 正在调配本地虚拟环境 Python 启动下载器...
echo ======================================================
echo.

:: 构建并组合命令参数
set CMD_ARGS="%URL%" -s "%START_TIME%"
if not "%END_TIME%"=="" (
    set CMD_ARGS=%CMD_ARGS% -e "%END_TIME%"
)
set CMD_ARGS=%CMD_ARGS% -r "%RESOLUTION%"

:: 打印具体执行命令
echo [*] 执行底层命令: venv\Scripts\python download_clip.py %CMD_ARGS%
echo.

:: 执行
.\venv\Scripts\python download_clip.py %CMD_ARGS%

:END
echo.
echo ======================================================
echo [*] 任务运行已结束。按任意键关闭此窗口...
echo ======================================================
pause > nul
