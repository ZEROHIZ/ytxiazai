// ==================== 全局状态与初始化 ====================
const API_BASE = ""; // 本地/Docker 容器暴露的 API 地址前缀，同域留空
let allJsons = [];
let jsonPage = 1;
let jsonLimit = 20;
let jsonTotal = 0;
let clipsPage = 1;
let clipsLimit = 20;
let clipsTotal = 0;
let activeTab = "dashboard";
let selectedJobForLogs = null;
let logPollInterval = null;
let statusPollInterval = null;

// 新建/编辑 JSON 时的缓存对象
let editingJsonData = {
    filename: "",
    content: {
        url: "",
        title: "",
        group_dir: "",
        clips: {}
    }
};

document.addEventListener("DOMContentLoaded", () => {
    // 1. 初始化加载
    loadJsons();
    loadSettings();
    loadCookies();
    
    // 2. 轮询后台状态和下载任务队列
    startStatusPolling();
    
    // 3. 拖拽上传 Cookie 逻辑
    setupCookieDragAndDrop();
});

// ==================== TAB 切换逻辑 ====================
function switchTab(tabId) {
    activeTab = tabId;
    
    // 移除所有 Tab 按钮和面板的 active 状态
    document.querySelectorAll(".nav-item").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
    
    // 激活选中的 Tab 按钮和面板
    const activeBtn = document.getElementById(`tab-btn-${tabId}`);
    const activePanel = document.getElementById(`panel-${tabId}`);
    if (activeBtn) activeBtn.classList.add("active");
    if (activePanel) activePanel.classList.add("active");
    
    // 触发特定 Tab 激活时的额外加载
    if (tabId === "library") {
        loadClips();
    } else if (tabId === "cookies") {
        loadCookies();
        loadSettings();
    } else if (tabId === "dashboard") {
        loadJsons();
    }
}

// ==================== TAB 1: JSON 配置文件管理 ====================
let currentJsonFilter = 'all';

async function loadJsons() {
    try {
        const q = document.getElementById("json-search-input").value;
        const res = await fetch(`${API_BASE}/api/jsons?status=${currentJsonFilter}&q=${encodeURIComponent(q)}&page=${jsonPage}&limit=${jsonLimit}`);
        if (!res.ok) throw new Error("无法读取配置文件列表");
        const data = await res.json();
        allJsons = data.jsons;
        jsonTotal = data.total;
        renderJsonsGrid(allJsons);
        renderJsonPagination();
    } catch (err) {
        console.error(err);
        showNotification("读取配置文件失败", "error");
    }
}

function setJsonFilter(filterType) {
    currentJsonFilter = filterType;
    jsonPage = 1;
    document.querySelectorAll('.filter-tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = document.getElementById(`json-filter-${filterType}`);
    if (activeBtn) {
        activeBtn.classList.add('active');
    }
    loadJsons();
}

function renderJsonsGrid(jsons) {
    const grid = document.getElementById("json-grid");
    const countText = document.getElementById("json-count-text");
    
    grid.innerHTML = "";
    countText.innerText = `共 ${jsons.length} 个配置文件`;
    
    if (jsons.length === 0) {
        grid.innerHTML = `
            <div class="glass-card" style="grid-column: 1/-1; padding: 40px; text-align: center; color: var(--text-muted);">
                <p>📂 暂无匹配的配置文件。</p>
            </div>
        `;
        return;
    }
    
    jsons.forEach(item => {
        const card = document.createElement("div");
        card.className = "card json-card";
        
        let statusPill = "";
        if (item.is_processed) {
            statusPill = `<span class="status-pill status-completed">✓ 已归档 (${item.completed_count}/${item.clips_count})</span>`;
        } else if (item.status === "completed") {
            statusPill = `<span class="status-pill status-completed">✓ 已完成 (${item.completed_count}/${item.clips_count})</span>`;
        } else if (item.status === "running") {
            statusPill = `<span class="status-pill status-running">⏳ 下载中...</span>`;
        } else {
            statusPill = `<span class="status-pill status-pending">● 挂起中 (${item.completed_count}/${item.clips_count})</span>`;
        }
        
        card.innerHTML = `
            <div class="json-card-header">
                <span class="json-card-title">${escapeHtml(item.filename)}</span>
                ${statusPill}
            </div>
            <div class="json-card-meta">
                <strong>视频标题:</strong>
                <span>${escapeHtml(item.title || "未知")}</span>
                <strong>源视频链接:</strong>
                ${item.url ? `<a href="${item.url}" target="_blank" title="${item.url}">${escapeHtml(item.url)}</a>` : '<span class="dim-text">未填</span>'}
                <strong>切片个数:</strong>
                <span>${item.clips_count} 个分段</span>
            </div>
            <div class="json-card-footer">
                <button class="btn btn-secondary btn-sm" onclick="editJsonConfig('${item.filename}')">⚙ 编辑</button>
                <button class="btn btn-danger btn-sm" onclick="deleteJsonConfig('${item.filename}')">🗑 删除</button>
                <button class="btn btn-primary btn-sm" style="margin-left: auto;" onclick="triggerDownload('${item.filename}')">⚡ 下载</button>
            </div>
        `;
        grid.appendChild(card);
    });
}

function filterJsons() {
    jsonPage = 1;
    loadJsons();
}

function renderJsonPagination() {
    const totalPages = Math.ceil(jsonTotal / jsonLimit) || 1;
    if (jsonPage > totalPages) {
        jsonPage = totalPages;
    }
    document.getElementById("json-page-info").innerText = `第 ${jsonPage} / ${totalPages} 页 (共 ${jsonTotal} 个任务)`;
    
    document.getElementById("json-prev-btn").disabled = jsonPage <= 1;
    document.getElementById("json-next-btn").disabled = jsonPage >= totalPages;
}

function jsonPrevPage() {
    if (jsonPage > 1) {
        jsonPage--;
        loadJsons();
    }
}

function jsonNextPage() {
    const totalPages = Math.ceil(jsonTotal / jsonLimit) || 1;
    if (jsonPage < totalPages) {
        jsonPage++;
        loadJsons();
    }
}

function changeJsonLimit() {
    jsonLimit = parseInt(document.getElementById("json-limit-select").value);
    jsonPage = 1;
    loadJsons();
}

async function deleteJsonConfig(filename) {
    if (!confirm(`确定要删除配置文件 [${filename}] 吗？此操作不会删除已下载的物理视频素材，但会清除配置。`)) return;
    try {
        const res = await fetch(`${API_BASE}/api/jsons/${filename}`, { method: "DELETE" });
        if (!res.ok) throw new Error("删除失败");
        showNotification("删除配置文件成功");
        loadJsons();
    } catch (err) {
        showNotification(err.message, "error");
    }
}

async function copyPromptToClipboard(filename) {
    try {
        const res = await fetch(`${API_BASE}/api/prompts/${filename}`);
        if (!res.ok) throw new Error("获取提示词内容失败");
        const data = await res.json();
        
        // 写入剪贴板
        await navigator.clipboard.writeText(data.content);
        showNotification(`📋 提示词 [${filename}] 已成功复制到剪贴板！可以直接粘贴到 AI Studio。`);
    } catch (err) {
        console.error(err);
        showNotification("复制提示词失败: " + err.message, "error");
    }
}

// ==================== JSON 弹窗与动态快速编辑表单 ====================
function openJsonModal(isNew = false) {
    const modal = document.getElementById("modal-json");
    const title = document.getElementById("modal-json-title");
    const filenameInput = document.getElementById("form-json-filename");
    
    modal.classList.add("active");
    
    if (isNew) {
        title.innerText = "新建配置文件 (JSON)";
        filenameInput.disabled = false;
        editingJsonData = {
            filename: `video_${Date.now().toString().slice(-6)}.json`,
            content: {
                url: "",
                title: "",
                group_dir: "",
                clips: {
                    "1": {
                        "time": "[00:00,00:10]",
                        "tag": "主体分类_子场景描述_属性1_属性2",
                        "attributes": {
                            "主体": "分类目录",
                            "场景": "写字楼",
                            "动作": "行走",
                            "镜头": "推镜头",
                            "氛围": "商务",
                            "描述": "西装男走向大楼",
                            "关键词": ["西装", "写字楼"]
                        }
                    }
                }
            }
        };
    }
    
    filenameInput.value = editingJsonData.filename;
    renderJsonFormFromData();
    syncJsonRawView();
}

function closeJsonModal() {
    document.getElementById("modal-json").classList.remove("active");
}

function renderJsonFormFromData() {
    const container = document.getElementById("form-json-clips-container");
    container.innerHTML = "";
    
    // 渲染全局 URL & Title & Group Dir
    document.getElementById("form-json-url").value = editingJsonData.content.url || "";
    document.getElementById("form-json-title").value = editingJsonData.content.title || "";
    document.getElementById("form-json-group-dir").value = editingJsonData.content.group_dir || "";
    
    const clips = editingJsonData.content.clips || {};
    
    Object.keys(clips).forEach(clipId => {
        const clip = clips[clipId];
        const attrs = clip.attributes || {};
        
        const row = document.createElement("div");
        row.className = "clip-form-row";
        row.dataset.clipId = clipId;
        
        row.innerHTML = `
            <div class="clip-form-row-header">
                <strong>片段 ID: #${clipId}</strong>
                <button class="btn-remove-clip" onclick="removeClipFormRow('${clipId}')">✕ 移除片段</button>
            </div>
            <div class="form-row-2col">
                <div class="form-group">
                    <label>时间轴区间 (格式: [HH:MM:SS,HH:MM:SS])</label>
                    <input type="text" class="clip-time" value="${escapeHtml(clip.time || '')}" placeholder="如 [00:10,00:15]" oninput="syncJsonFromInputs()">
                </div>
                <div class="form-group">
                    <label>整合 Tag 物理重命名标签</label>
                    <input type="text" class="clip-tag" value="${escapeHtml(clip.tag || '')}" placeholder="如 运动_跑步_室外" oninput="syncJsonFromInputs()">
                </div>
            </div>
            <div class="form-row-2col">
                <div class="form-group">
                    <label>主体 (第一级分类目录)</label>
                    <input type="text" class="attr-subject" value="${escapeHtml(attrs['主体'] || '')}" placeholder="如 科技、美食、美妆" oninput="syncJsonFromInputs()">
                </div>
                <div class="form-group">
                    <label>场景 (如 办公室/公园)</label>
                    <input type="text" class="attr-scene" value="${escapeHtml(attrs['场景'] || '')}" oninput="syncJsonFromInputs()">
                </div>
            </div>
            <div class="form-row-2col">
                <div class="form-group">
                    <label>动作行为 (如 奔跑/微笑)</label>
                    <input type="text" class="attr-action" value="${escapeHtml(attrs['动作'] || '')}" oninput="syncJsonFromInputs()">
                </div>
                <div class="form-group">
                    <label>镜头运动 (如 推镜头/拉镜头)</label>
                    <input type="text" class="attr-camera" value="${escapeHtml(attrs['镜头'] || '')}" oninput="syncJsonFromInputs()">
                </div>
            </div>
            <div class="form-group" style="margin-bottom: 0;">
                <label>片段细节描述 (用于搜索匹配)</label>
                <input type="text" class="attr-desc" value="${escapeHtml(attrs['描述'] || '')}" placeholder="描述该视频片段的核心画面..." oninput="syncJsonFromInputs()">
            </div>
        `;
        container.appendChild(row);
    });
}

function addNewClipFormRow() {
    const clips = editingJsonData.content.clips || {};
    // 自动寻找下一个 ID
    let nextId = 1;
    while (clips[nextId.toString()]) {
        nextId++;
    }
    
    clips[nextId.toString()] = {
        "time": "[00:00,00:10]",
        "tag": "主体分类_子场景描述_属性",
        "attributes": {
            "主体": "分类目录",
            "场景": "",
            "动作": "",
            "镜头": "",
            "描述": "",
            "关键词": []
        }
    };
    
    renderJsonFormFromData();
    syncJsonRawView();
}

function removeClipFormRow(clipId) {
    if (editingJsonData.content.clips && editingJsonData.content.clips[clipId]) {
        delete editingJsonData.content.clips[clipId];
        renderJsonFormFromData();
        syncJsonRawView();
    }
}

// 从左侧快速表单输入中同步至缓存并写回右侧 JSON 代码框
function syncJsonFromInputs() {
    const filenameInput = document.getElementById("form-json-filename");
    editingJsonData.filename = filenameInput.value.strip ? filenameInput.value.strip() : filenameInput.value;
    
    editingJsonData.content.url = document.getElementById("form-json-url").value;
    editingJsonData.content.title = document.getElementById("form-json-title").value;
    editingJsonData.content.group_dir = document.getElementById("form-json-group-dir").value;
    
    const rows = document.querySelectorAll(".clip-form-row");
    const newClips = {};
    
    rows.forEach(row => {
        const clipId = row.dataset.clipId;
        const timeVal = row.querySelector(".clip-time").value;
        const tagVal = row.querySelector(".clip-tag").value;
        
        const subjVal = row.querySelector(".attr-subject").value;
        const sceneVal = row.querySelector(".attr-scene").value;
        const actionVal = row.querySelector(".attr-action").value;
        const cameraVal = row.querySelector(".attr-camera").value;
        const descVal = row.querySelector(".attr-desc").value;
        
        newClips[clipId] = {
            "time": timeVal,
            "tag": tagVal,
            "attributes": {
                "主体": subjVal,
                "场景": sceneVal,
                "动作": actionVal,
                "镜头": cameraVal,
                "描述": descVal,
                "关键词": tagVal.split("_").map(s => s.trim()).filter(Boolean)
            }
        };
    });
    
    editingJsonData.content.clips = newClips;
    syncJsonRawView();
}

// 刷新右侧文本框代码
function syncJsonRawView() {
    const textarea = document.getElementById("form-json-raw");
    textarea.value = JSON.stringify(editingJsonData.content, null, 4);
    document.getElementById("json-syntax-error").style.display = "none";
}

// 从右侧原始 JSON 代码框反向同步到左侧表单
function syncInputsFromJsonRaw() {
    const rawText = document.getElementById("form-json-raw").value;
    try {
        const parsed = JSON.parse(rawText);
        editingJsonData.content = parsed;
        document.getElementById("json-syntax-error").style.display = "none";
        
        // 刷新左侧表单展示，但保留输入光标活动（若需防闪烁可以仅单向刷新）
        renderJsonFormFromData();
    } catch (e) {
        document.getElementById("json-syntax-error").style.display = "block";
    }
}

async function editJsonConfig(filename) {
    try {
        const res = await fetch(`${API_BASE}/api/jsons/${filename}`);
        if (!res.ok) throw new Error("读取配置文件出错");
        const content = await res.json();
        
        editingJsonData = {
            filename: filename,
            content: content
        };
        
        openJsonModal(false);
        // 限制编辑时文件名修改
        document.getElementById("form-json-filename").disabled = true;
    } catch (err) {
        showNotification(err.message, "error");
    }
}

async function saveJsonConfig() {
    syncJsonFromInputs();
    
    const filename = editingJsonData.filename.trim();
    if (!filename) {
        alert("请输入配置文件名！");
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/api/jsons`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                filename: filename,
                content: editingJsonData.content
            })
        });
        if (!res.ok) throw new Error("配置文件保存失败");
        
        showNotification("配置文件保存成功");
        closeJsonModal();
        loadJsons();
    } catch (err) {
        showNotification(err.message, "error");
    }
}

// ==================== TAB 2: 素材库列表与搜索预览 ====================
async function loadClips() {
    const q = document.getElementById("clip-search-input").value;
    const tag = document.getElementById("clip-filter-tag").value;
    const grid = document.getElementById("clips-grid");
    
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;">🎬 正在扫描 SQLite 数据库加载片段...</div>`;
    
    let url = `${API_BASE}/api/clips?page=${clipsPage}&limit=${clipsLimit}`;
    if (q) url += `&q=${encodeURIComponent(q)}`;
    if (tag) url += `&tag=${encodeURIComponent(tag)}`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error("无法加载已录入的片段数据");
        const data = await res.json();
        clipsTotal = data.total;
        renderClipsGrid(data.clips);
        renderClipsPagination();
        updateTagFilterDropdown();
    } catch (err) {
        showNotification(err.message, "error");
    }
}

function renderClipsPagination() {
    const totalPages = Math.ceil(clipsTotal / clipsLimit) || 1;
    if (clipsPage > totalPages) {
        clipsPage = totalPages;
    }
    document.getElementById("clips-page-info").innerText = `第 ${clipsPage} / ${totalPages} 页 (共 ${clipsTotal} 个片段)`;
    
    document.getElementById("clips-prev-btn").disabled = clipsPage <= 1;
    document.getElementById("clips-next-btn").disabled = clipsPage >= totalPages;
}

function clipsPrevPage() {
    if (clipsPage > 1) {
        clipsPage--;
        loadClips();
    }
}

function clipsNextPage() {
    const totalPages = Math.ceil(clipsTotal / clipsLimit) || 1;
    if (clipsPage < totalPages) {
        clipsPage++;
        loadClips();
    }
}

function changeClipsLimit() {
    clipsLimit = parseInt(document.getElementById("clips-limit-select").value);
    clipsPage = 1;
    loadClips();
}

function renderClipsGrid(clips) {
    const grid = document.getElementById("clips-grid");
    grid.innerHTML = "";
    
    if (clips.length === 0) {
        grid.innerHTML = `
            <div class="glass-card" style="grid-column: 1/-1; padding: 60px; text-align: center; color: var(--text-muted);">
                <p>🎬 暂未在本地数据库发现匹配的片段素材。请先进入控制中心启动下载任务。</p>
            </div>
        `;
        return;
    }
    
    clips.forEach(clip => {
        const card = document.createElement("div");
        card.className = "card clip-card";
        
        // 视频时长格式化
        const durSec = parseFloat(clip.duration || 0);
        const min = Math.floor(durSec / 60);
        const sec = Math.floor(durSec % 60);
        const durationStr = `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
        
        card.innerHTML = `
            <div class="clip-video-preview" onclick="playVideoClip(${JSON.stringify(clip).replace(/"/g, '&quot;')})">
                <img src="${API_BASE}/api/clips/thumbnail?path=${encodeURIComponent(clip.local_path)}" loading="lazy" style="width:100%; height:100%; object-fit:cover; display:block;" alt="视频首帧封面">
                <span class="play-overlay-btn" style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%);">▶</span>
                <span class="clip-duration-badge">${durationStr}</span>
            </div>
            <div class="clip-info-body">
                <span class="clip-tag"># ${escapeHtml(clip.tag || '未命名')}</span>
                
                <div style="font-size:0.9rem; margin-top:2px;">
                    <strong>细节描述:</strong> <span style="color:var(--text-muted);">${escapeHtml(clip.description || '暂无描述')}</span>
                </div>
                
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.75rem; color:var(--text-muted); margin-top:4px; background:rgba(255,255,255,0.01); padding:8px; border-radius:4px;">
                    <div><strong>🎬 镜头:</strong> ${escapeHtml(clip.camera_movement || '-')}</div>
                    <div><strong>🏃 动作:</strong> ${escapeHtml(clip.action || '-')}</div>
                    <div><strong>🏢 场景:</strong> ${escapeHtml(clip.scene || '-')}</div>
                    <div><strong>✨ 氛围:</strong> ${escapeHtml(clip.atmosphere || '-')}</div>
                    <div><strong>🎨 色调:</strong> ${escapeHtml(clip.color_tone || '-')}</div>
                    <div style="grid-column:1/-1;"><strong>📐 属性:</strong> ${escapeHtml(clip.resolution || '-')} @ ${clip.fps ? clip.fps + 'fps' : '-'}</div>
                </div>

                <div class="clip-title-original" title="来自：${clip.video_title}">
                    📺 ${escapeHtml(clip.video_title)}
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

async function updateTagFilterDropdown() {
    const dropdown = document.getElementById("clip-filter-tag");
    const currentVal = dropdown.value;
    try {
        const res = await fetch(`${API_BASE}/api/tags`);
        if (!res.ok) return;
        const tags = await res.json();
        
        dropdown.innerHTML = `<option value="">所有 Tag 标签</option>`;
        tags.forEach(tag => {
            dropdown.innerHTML += `<option value="${escapeHtml(tag)}">${escapeHtml(tag)}</option>`;
        });
        
        dropdown.value = currentVal;
    } catch (e) {
        console.error("加载标签下拉框失败:", e);
    }
}

function playVideoClip(clip) {
    const modal = document.getElementById("modal-video-preview");
    const video = document.getElementById("preview-video-player");
    const title = document.getElementById("modal-video-title");
    const metaCard = document.getElementById("preview-video-metadata");
    
    modal.classList.add("active");
    title.innerText = `预览素材：${clip.tag || clip.clip_id}`;
    
    // 载入流路径并播放
    video.src = clip.web_path;
    video.load();
    video.play();
    
    // 渲染特征元数据
    metaCard.innerHTML = `
        <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; font-size:0.85rem;">
            <div><strong>主体分类:</strong> ${escapeHtml(clip.subject)}</div>
            <div><strong>画面色调:</strong> ${escapeHtml(clip.color_tone || '-')}</div>
            <div><strong>物理分辨率:</strong> ${escapeHtml(clip.resolution)}</div>
            <div><strong>宽高比例:</strong> ${escapeHtml(clip.aspect_ratio)}</div>
            <div><strong>帧率 (FPS):</strong> ${clip.fps}</div>
            <div><strong>时长 (秒):</strong> ${clip.duration}s</div>
            <div><strong>转场审核对齐:</strong> 已物理对齐微调</div>
            <div style="grid-column: 1/-1; border-top:1px solid var(--border-glass); padding-top:8px; margin-top:8px;">
                <strong>物理保存路径:</strong> <code style="font-size:0.75rem;">${escapeHtml(clip.local_path)}</code>
            </div>
        </div>
    `;
}

function closeVideoModal() {
    const modal = document.getElementById("modal-video-preview");
    const video = document.getElementById("preview-video-player");
    video.pause();
    video.src = "";
    modal.classList.remove("active");
}

// ==================== TAB 3: COOKIES & 代理系统参数 ====================
async function loadSettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        document.getElementById("setting-proxy").value = data.proxy || "";
        document.getElementById("setting-resolution").value = data.resolution || "2k";
    } catch (e) {
        showNotification("加载设置失败", "error");
    }
}

async function saveSettings(event) {
    event.preventDefault();
    const proxy = document.getElementById("setting-proxy").value;
    const resolution = document.getElementById("setting-resolution").value;
    
    try {
        const res = await fetch(`${API_BASE}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ proxy, resolution })
        });
        if (!res.ok) throw new Error("修改设置失败");
        showNotification("配置更新持久化保存成功！");
    } catch (err) {
        showNotification(err.message, "error");
    }
}

async function loadCookies() {
    try {
        const res = await fetch(`${API_BASE}/api/cookies`);
        if (!res.ok) throw new Error();
        const cookies = await res.json();
        
        const box = document.getElementById("cookie-list-box");
        box.innerHTML = "";
        
        document.getElementById("metric-cookies-count").innerText = cookies.length;
        
        if (cookies.length === 0) {
            box.innerHTML = `<p class="dim-text" style="text-align:center;padding:20px;">🔑 尚未配置任何 Cookie 凭证（单路下载排队模式）</p>`;
            return;
        }
        
        cookies.forEach(c => {
            const item = document.createElement("div");
            item.className = "cookie-item";
            
            const sizeKB = (c.size / 1024).toFixed(1);
            const isDefaultBadge = c.is_default ? ` <span class="badge" style="background:#10b981;position:static;transform:none;padding:2px 6px;margin-left:6px;">默认 Cookie</span>` : "";
            
            item.innerHTML = `
                <div>
                    <div class="cookie-item-name">🔑 ${escapeHtml(c.filename)}${isDefaultBadge}</div>
                    <div class="cookie-item-meta">大小: ${sizeKB} KB | 文件路径: cookies/${escapeHtml(c.filename)}</div>
                </div>
                <div style="display:flex; gap:8px;">
                    <button class="btn btn-secondary btn-sm" onclick="renameCookie('${c.filename}')">✏️ 重命名</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteCookie('${c.filename}')">🗑 删除</button>
                </div>
            `;
            box.appendChild(item);
        });
    } catch (e) {
        showNotification("加载 Cookie 失败", "error");
    }
}

function openCookieModal() {
    document.getElementById("modal-cookie").classList.add("active");
    document.getElementById("form-cookie-filename").value = `cookies_${Date.now().toString().slice(-4)}.txt`;
    document.getElementById("form-cookie-content").value = "";
}

function closeCookieModal() {
    document.getElementById("modal-cookie").classList.remove("active");
}

async function saveCookieManual() {
    const name = document.getElementById("form-cookie-filename").value.trim();
    const content = document.getElementById("form-cookie-content").value.trim();
    
    if (!name || !content) {
        alert("请输入完整的文件名和文本内容！");
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/api/cookies?filename=${encodeURIComponent(name)}&content=${encodeURIComponent(content)}`, {
            method: "POST"
        });
        if (!res.ok) throw new Error("保存 Cookie 失败");
        showNotification("Cookie 新建成功！");
        closeCookieModal();
        loadCookies();
    } catch (err) {
        showNotification(err.message, "error");
    }
}

function setupCookieDragAndDrop() {
    const dropzone = document.getElementById("cookie-dropzone");
    const fileInput = document.getElementById("cookie-file-input");
    
    dropzone.addEventListener("click", () => fileInput.click());
    
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "var(--primary)";
    });
    
    dropzone.addEventListener("dragleave", () => {
        dropzone.style.borderColor = "var(--border-glass)";
    });
    
    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "var(--border-glass)";
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            uploadCookieFile();
        }
    });
}

async function uploadCookieFile() {
    const fileInput = document.getElementById("cookie-file-input");
    if (fileInput.files.length === 0) return;
    
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const res = await fetch(`${API_BASE}/api/cookies/upload`, {
            method: "POST",
            body: formData
        });
        if (!res.ok) throw new Error("上传 Cookie 失败");
        showNotification("Cookie 上传导入成功！");
        loadCookies();
    } catch (err) {
        showNotification(err.message, "error");
    } finally {
        fileInput.value = "";
    }
}

async function deleteCookie(filename) {
    if (!confirm(`确认要删除 Cookie 凭证 [${filename}] 吗？这会导致绑定此账号的并发槽被移除。`)) return;
    try {
        const res = await fetch(`${API_BASE}/api/cookies/${filename}`, { method: "DELETE" });
        if (!res.ok) throw new Error("删除失败");
        showNotification("Cookie 已物理清除");
        loadCookies();
    } catch (err) {
        showNotification(err.message, "error");
    }
}

async function renameCookie(filename) {
    const newName = prompt("请输入新的 Cookie 文件名 (需以 .txt 结尾):", filename);
    if (!newName) return;
    
    if (newName.trim() === filename) return;
    
    try {
        const res = await fetch(`${API_BASE}/api/cookies/rename?filename=${encodeURIComponent(filename)}&new_filename=${encodeURIComponent(newName.trim())}`, {
            method: "POST"
        });
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "重命名失败");
        }
        showNotification("Cookie 重命名成功！");
        loadCookies();
    } catch (err) {
        showNotification(err.message, "error");
    }
}

// ==================== TAB 4: 下载中心并发调度管理 ====================
async function triggerDownload(filename) {
    try {
        const res = await fetch(`${API_BASE}/api/download/start?filename=${encodeURIComponent(filename)}`, {
            method: "POST"
        });
        if (!res.ok) throw new Error("加入下载队列失败");
        const data = await res.json();
        showNotification("已加入并发下载队列");
        // 自动跳转到下载控制台
        switchTab("console");
        // 默认选中查看其日志
        viewJobLogs(filename);
    } catch (err) {
        showNotification(err.message, "error");
    }
}

async function triggerAllDownloads() {
    if (!confirm("确定要启动全部挂起（未下载成功）的任务吗？系统将利用多 Cookie 动态分配到并发线程中。")) return;
    try {
        const res = await fetch(`${API_BASE}/api/download/start_all`, { method: "POST" });
        if (!res.ok) throw new Error("启动失败");
        const data = await res.json();
        showNotification(data.message);
        switchTab("console");
    } catch (err) {
        showNotification(err.message, "error");
    }
}

function startStatusPolling() {
    if (statusPollInterval) clearInterval(statusPollInterval);
    
    const pollFunc = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/download/status`);
            if (!res.ok) return;
            const data = await res.json();
            
            // 更新指标
            document.getElementById("metric-active-count").innerText = data.active_workers_count;
            document.getElementById("metric-queue-count").innerText = data.queue_len;
            
            // 侧边栏活动指示徽章
            const badge = document.getElementById("badge-running-count");
            if (data.active_workers_count > 0) {
                badge.innerText = data.active_workers_count;
                badge.style.display = "block";
            } else {
                badge.style.display = "none";
            }
            
            // 渲染控制台任务列表
            renderConsoleJobs(data);
        } catch (e) {
            console.error("轮询状态出错:", e);
        }
    };
    
    // 每 2.5 秒刷新一次全局任务状态
    pollFunc();
    statusPollInterval = setInterval(pollFunc, 2500);
}

function renderConsoleJobs(data) {
    const list = document.getElementById("console-jobs-list");
    list.innerHTML = "";
    
    const jobs = data.jobs || {};
    const queued = data.queue || [];
    
    // 合并展示
    const allJobKeys = new Set([...Object.keys(jobs), ...queued]);
    
    if (allJobKeys.size === 0) {
        list.innerHTML = `<p class="dim-text" style="text-align:center;padding:20px;">📺 当前下载队列与运行器中无活跃作业</p>`;
        return;
    }
    
    Array.from(allJobKeys).forEach(filename => {
        const item = document.createElement("div");
        item.className = `job-item ${selectedJobForLogs === filename ? 'active' : ''}`;
        item.onclick = () => viewJobLogs(filename);
        
        let status = "waiting";
        let cookieText = "";
        let pidText = "";
        
        if (jobs[filename]) {
            status = jobs[filename].status;
            if (jobs[filename].cookie) {
                cookieText = ` | 🔑 ${jobs[filename].cookie}`;
            }
            if (jobs[filename].pid) {
                pidText = ` | PID: ${jobs[filename].pid}`;
            }
        }
        
        let statusBadge = "";
        if (status === "running") {
            statusBadge = `<span class="status-pill status-running">⏳ 运行中</span>`;
        } else if (status === "completed") {
            statusBadge = `<span class="status-pill status-completed">✓ 已完成</span>`;
        } else if (status === "failed") {
            statusBadge = `<span class="status-pill status-pending" style="background:rgba(239,68,68,0.15);color:#f87171;">✕ 失败</span>`;
        } else {
            statusBadge = `<span class="status-pill status-pending">排队等待</span>`;
        }
        
        item.innerHTML = `
            <div>
                <div class="job-item-name">${escapeHtml(filename)}</div>
                <div class="job-item-desc">配置路径: data/${escapeHtml(filename)}${cookieText}${pidText}</div>
            </div>
            <div style="display:flex;align-items:center;gap:10px;">
                ${statusBadge}
                ${(status === 'running' || status === 'waiting') ? `<button class="btn-remove-clip" onclick="killJob(event, '${filename}')" style="font-size:1.1rem;padding:4px;">🛑</button>` : ''}
            </div>
        `;
        list.appendChild(item);
    });
}

async function killJob(event, filename) {
    event.stopPropagation(); // 阻止触发查看日志
    if (!confirm(`确定要强行终止/取消该作业 [${filename}] 吗？`)) return;
    try {
        const res = await fetch(`${API_BASE}/api/download/kill?filename=${encodeURIComponent(filename)}`, {
            method: "POST"
        });
        if (!res.ok) throw new Error("取消作业失败");
        showNotification("作业已被强行中止");
    } catch (err) {
        showNotification(err.message, "error");
    }
}

// 查看某个具体作业的日志流
function viewJobLogs(filename) {
    selectedJobForLogs = filename;
    
    // 高亮被选中的作业项
    document.querySelectorAll(".job-item").forEach(item => {
        if (item.querySelector(".job-item-name").innerText === filename) {
            item.classList.add("active");
        } else {
            item.classList.remove("active");
        }
    });
    
    document.getElementById("terminal-job-title").innerText = `📺 终端日志：${filename}`;
    
    // 强制显示手动刷新按钮
    const refreshBtn = document.getElementById("btn-refresh-logs");
    refreshBtn.style.display = "inline-block";
    refreshBtn.onclick = () => pollJobLogsFunc(true);
    
    // 开始轮询该日志
    if (logPollInterval) clearInterval(logPollInterval);
    
    const pollJobLogsFunc = async (forceScroll = false) => {
        try {
            const res = await fetch(`${API_BASE}/api/download/logs?filename=${encodeURIComponent(filename)}`);
            if (!res.ok) return;
            const data = await res.json();
            
            const terminal = document.getElementById("terminal-output");
            
            // 检测用户是否处于滚动条底部，若是则自动滚动
            const isScrolledToBottom = terminal.scrollHeight - terminal.clientHeight <= terminal.scrollTop + 40;
            
            terminal.innerText = data.logs || "等待日志输出...\n";
            
            if (isScrolledToBottom || forceScroll) {
                terminal.scrollTop = terminal.scrollHeight;
            }
        } catch (e) {
            console.error("加载终端日志出错:", e);
        }
    };
    
    pollJobLogsFunc(true);
    // 每 1.5 秒轮询一次当前选中的日志
    logPollInterval = setInterval(pollJobLogsFunc, 1500);
}

// ==================== 辅助通用工具函数 ====================
function showNotification(msg, type = "success") {
    // 简洁优雅的页面顶部微提示
    const div = document.createElement("div");
    div.style.position = "fixed";
    div.style.top = "20px";
    div.style.left = "50%";
    div.style.transform = "translateX(-50%) translateY(-20px)";
    div.style.background = type === "success" ? "rgba(16, 185, 129, 0.95)" : "rgba(239, 68, 68, 0.95)";
    div.style.color = "#fff";
    div.style.padding = "10px 24px";
    div.style.borderRadius = "30px";
    div.style.boxShadow = "0 10px 25px rgba(0,0,0,0.3)";
    div.style.zIndex = "10000";
    div.style.fontFamily = "var(--font-outfit)";
    div.style.fontWeight = "600";
    div.style.transition = "all 0.3s ease";
    div.style.opacity = "0";
    
    div.innerText = msg;
    document.body.appendChild(div);
    
    // 动效飞入
    setTimeout(() => {
        div.style.transform = "translateX(-50%) translateY(0)";
        div.style.opacity = "1";
    }, 50);
    
    // 自动淡出
    setTimeout(() => {
        div.style.transform = "translateX(-50%) translateY(-20px)";
        div.style.opacity = "0";
        setTimeout(() => div.remove(), 300);
    }, 2500);
}

function escapeHtml(str) {
    if (!str) return "";
    return str.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
