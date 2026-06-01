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

## [2026-05-31] 远端 Docker 环境下下载 YouTube 视频报错 (EJS 默认引擎白名单策略与 API 参数格式问题)
**问题描述:**
在远端 Docker 环境中下载 YouTube 视频时失败，报错：`ERROR: [youtube] A7NUHDuaGXk: Requested format is not available. Use --list-formats for a list of available formats`。
同时伴随警告：`WARNING: [youtube] A7NUHDuaGXk: n challenge solving failed: Some formats may be missing. Ensure you have a supported JavaScript runtime and challenge solver script distribution installed.`

**原因分析:**
1. 现代 YouTube 采用混淆的 JavaScript 计算 `n` 签名参数来限制带宽和隐藏高清晰度视频格式，`yt-dlp` 必须依赖外部 JS 运行时（如 Node.js 或 Deno）以及 `yt-dlp-ejs` 库进行求解。
2. **为什么本地可以但 Docker 不行（深层病因）**：
   * **白名单安全策略限制**：在默认情况下，`yt-dlp` 的 EJS 求解器**仅自动启用并放行 Deno 引擎**，对 Node.js、Bun、QuickJS 默认全部采取**禁用（unavailable）**策略。
   * **本地环境**：本地 Windows 电脑上安装了 **Deno**（属于默认允许引擎），因此自动检测通过。
   * **Docker 环境**：容器内仅存在 **Node.js**，导致即使 Node 完美可运行，也会被 `yt-dlp` 无情屏蔽并报 `node (unavailable)`，最终在无 JS 运行时的情况下报错。
3. **为什么参数配置报错**：为了强行开启 Node.js 运行时，我们在 Python `ydl_opts` 中配置了 `'js_runtimes': ['node']`，但 `yt-dlp` 官方 API 限制该参数**必须为 Dict 格式**，导致抛出 `Invalid js_runtimes format, expected a dict of {runtime: {config}}` 错误。

**修复方案:**
1. **代码级别修复**：在 [youtube_downloader.py](file:///d:/daima/youtube%E4%B8%8B%E8%BD%BD/youtube_downloader.py) 中：
   * 移除无用的 `'remote_components'` 在线拉取逻辑，全面使用本地 `pip` 离线打包的 `yt-dlp-ejs` 脚本。
   * 强制显式启用 Node.js 引擎，并修正为正确的 Dict 传参格式：`'js_runtimes': {'node': {}}`。
2. **重新部署运行**：在远端重新拉取代码并重启 Docker 容器即可。
