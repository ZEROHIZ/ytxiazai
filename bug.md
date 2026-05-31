# Bug 档案记录 (Bug Log)

## [2024-05-30] LLM 切片数量锐减 (AI 偷懒/上下文截断问题)
**问题描述:** 
在提示词中增加了复杂的 `attributes` 字段（如多维描述、动作、场景等）后，LLM 提取的切片数量大幅减少（从同视频 22 个锐减到 7 个）。

**原因分析:**
1. 提示词中明确禁止了 LLM 输出思考过程（“不要输出思考过程，只输出最终 JSON”），导致 LLM 无法进行 Chain of Thought (CoT) 推理。在面对每个切片庞大的结构化数据生成任务时，LLM “脑容量”耗尽，产生偷懒和提早截断的行为。
2. 提示词中存在隐性锚点（如示例中的“如果有 10 个好片段，就提取 10 个”），导致 LLM 将较小的数字作为心理预期上限。

**修复方案:**
1. **引入思维链 (CoT):** 在 `prompt.md` 的 JSON 输出模板的最外层，强制新增 `"thoughts"` 字段，要求 LLM 在输出具体的 `clips` 字典前，必须先在 `"thoughts"` 字符串内以文字形式进行全片时间轴的扫描推演。这迫使大模型保持运算不中断，防止偷懒。
2. **移除数量锚点:** 将提示词改为“【切片无上限原则】：绝不限制提取数量！”，明确要求“穷尽提取，严禁遗漏”，打破 LLM 默认的数量上限认知。

## [2026-05-31] 已归档任务删除失败 (delete_json 路径错误)
**问题描述:** 
用户尝试删除控制中心里处于“已归档/已处理” (processed) 目录下的 JSON 配置文件时报错或删除失败。

**原因分析:**
在 `web_app.py` 的 `/api/jsons/{filename}` [DELETE] 路由中，代码虽然正确判断并检测了已归档文件 `processed_path`，但最后执行物理删除时却硬编码写成了 `os.remove(path)`（即仅删除 data/ 主目录路径），导致抛出“文件不存在”的 500 异常。

**修复方案:**
将 `os.remove(path)` 改为使用检测定位出的正确目标路径 `os.remove(target)`，从而使 `data/` 主目录和 `data/processed/` 归档目录下的 JSON 文件均能被精准、无误地物理清除。

## [2026-05-31] 远端 Docker 环境下下载 YouTube 视频报错 (EJS 强制在线拉取导致 n challenge 失败)
**问题描述:**
在远端 Docker 环境中下载 YouTube 视频时失败，报错：`ERROR: [youtube] A7NUHDuaGXk: Requested format is not available. Use --list-formats for a list of available formats`。
同时伴随警告：`WARNING: [youtube] A7NUHDuaGXk: n challenge solving failed: Some formats may be missing. Ensure you have a supported JavaScript runtime and challenge solver script distribution installed.`

**原因分析:**
1. 现代 YouTube 采用混淆的 JavaScript 计算 `n` 签名参数来限制带宽和隐藏高清晰度视频格式。
2. `yt-dlp` 需要 JavaScript 运行时（如 `Node.js`）以及 `yt-dlp-ejs` 解密脚本来执行此运算。
3. **关键症结**：代码中在 `ydl_opts` 内强行指定了 `'remote_components': ['ejs:github']`。这强迫 `yt-dlp` 绕过本地已通过 `pip` 安装好的 `yt-dlp-ejs` 库，转而在每次运行期间动态去 GitHub 拉取解密脚本。
4. 在 Docker 容器内部，因为没有安装 `git` 命令行工具，且容器处于受限网络（或遭受国内 GFW 对 GitHub 的 DNS 污染与连通阻碍），导致动态拉取 GitHub 资源失败。由于异常被外层静默吸收，导致解密脚本完全缺失，进而使得求解器彻底失效。
5. 在本地 Windows 环境下，由于系统自带 `git` 且本地网络可顺畅访问 GitHub（或已有缓存），因此表现为能够正常下载。

**修复方案:**
1. **代码级别修复**：在 [youtube_downloader.py](file:///d:/daima/youtube%E4%B8%8B%E8%BD%BD/youtube_downloader.py) 中，将 `get_video_info` 与 `download_clip` 两处 `ydl_opts` 内的 `'remote_components': ['ejs:github']` 显式移除（已完成）。这使得 `yt-dlp` 会以极速且 100% 离线的方式直接导入并使用本地通过 `pip` (已安装有 `yt-dlp-ejs`) 获取的解密脚本。
2. **环境基础增强**：同步将本地的 `Dockerfile` 升级为 `python3.10-nodejs22-slim`（已完成），以确保与未来最新的 `yt-dlp` 规范完美对齐。
3. 在远端执行代码拉取和强制无缓存重构：
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```
