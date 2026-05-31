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

## [2026-05-31] 远端 Docker 环境下下载 YouTube 视频报错 (缺少 JS 运行时导致 n challenge 失败)
**问题描述:**
在远端 Docker 环境中下载 YouTube 视频时失败，报错：`ERROR: [youtube] A7NUHDuaGXk: Requested format is not available. Use --list-formats for a list of available formats`。
同时伴随警告：`WARNING: [youtube] A7NUHDuaGXk: n challenge solving failed: Some formats may be missing. Ensure you have a supported JavaScript runtime and challenge solver script distribution installed.`

**原因分析:**
1. 现代 YouTube 采用混淆的 JavaScript 计算 `n` 签名参数来限制带宽和隐藏格式。
2. `yt-dlp` (>=2025.0.0) 采用全新的 EJS (External JavaScript) 挑战求解器，其运行必须依赖外部 JavaScript 运行时（如 `Deno`、`Node.js` 或 `QuickJS`）以及 `yt-dlp-ejs` 库。
3. **关键原因**：作为 2026 年中最新的策略，`yt-dlp` 已经**彻底停止对 Node.js v20 和 v21 的支持，目前要求最低的 Node.js 版本为 v22+**。虽然远端容器中已经安装了 Node.js，但其版本为 `v20.20.2`（来自旧版基础镜像 `python3.10-nodejs20-slim`），被 `yt-dlp` 视为不支持的 JavaScript 运行时，从而拒绝运行，导致 `n challenge` 求解失败。
4. 本地项目的 `Dockerfile` 之前使用了包含 `nodejs20` 的基础镜像，现已被更新为 `FROM nikolaik/python-nodejs:python3.10-nodejs22-slim`。

**修复方案:**
1. 将本地的 `Dockerfile` 升级为 `python3.10-nodejs22-slim`（已完成）。
2. 在远端服务器上拉取最新代码，并清理缓存强制重新构建容器：
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```
3. 重建后，在远端容器中确认 Node.js 版本是否已经更新为 v22+：
```bash
docker exec -it youtube-downloader-web node -v
```
