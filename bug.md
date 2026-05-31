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

## [2026-05-31] YouTube 下载 n-signature 解密失败 (Requested format is not available)
**问题描述:**
在 YouTube 下载过程中，即使安装了 Node.js，依然报错 `Requested format is not available` 并伴随警告 `Remote component challenge solver script (node) was skipped`。

**原因分析:**
YouTube 会动态更改其反爬虫签名算法。`yt-dlp` 为了安全默认禁用了自动从网络下载最新的外部 JavaScript 解密组件。在内置解密算法失效的情况下，如果没有显式授权 `remote_components` 选项，它会拒绝拉取最新的解密脚本，从而导致签名算法解析（n challenge solving）失败。

**修复方案:**
在 `youtube_downloader.py` 的 `ydl_opts` 配置中，显式添加 `'remote_components': ['ejs:github']` 授权，允许 `yt-dlp` 自动抓取 GitHub 上最新的解密脚本。

