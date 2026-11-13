/**
 * LiteCron Web UI - 前端交互逻辑
 */

const state = {
    tasks: [],
    logs: [],
    containerStatus: null,
    isRunning: false,
    sortColumn: null,
    sortDirection: 'asc',
    hideDisabledTasks: false,
    theme: 'system',
    langMode: typeof window !== 'undefined' && window.LANG_MODE ? window.LANG_MODE : 'system',
    currentLogFilename: null,
    currentLogGroups: [],
    currentLogFilter: 'all'
};

// 任务颜色：基于任务名 hash + 黄金角(137.508°)色相分布，动态生成任意数量的高区分度颜色
// —— 取代固定颜色池，任务数再多也不易撞色，且同一任务名始终同色
function hashString(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) {
        h = ((h << 5) - h + str.charCodeAt(i)) | 0;
    }
    return Math.abs(h);
}

const GOLDEN_ANGLE = 137.508;

// 只算出色相，饱和度/明度/透明度交给 CSS 按当前主题派生（见 style.css 的 .task-colored）。
// 这样切换主题（含系统主题变化）不需要清缓存、不需要重渲染，配色随级联自动更新。
function taskHue(name) {
    return Math.round((hashString(name || 'task') * GOLDEN_ANGLE) % 360);
}

// ==================== 界面语言（服务端注入字典，切换后整页刷新） ====================
// 字典由模板注入为 window.I18N：服务端已按当前语言合并补齐（缺翻项回落中文），
// 因此这里不需要异步取字典，也没有「字典到位后再重绘」的过程。
const LANG_COOKIE_NAME = 'litecron_lang';
const LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function T(key, params) {
    const catalog = window.I18N || {};
    const text = catalog[key];
    if (typeof text !== 'string') return key;
    if (!params) return text;
    return text.replace(/\{(\w+)\}/g, (match, name) =>
        Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match
    );
}

/**
 * 写语言偏好并刷新页面。
 * 选「跟随系统」时清除 Cookie——「没选过」与「显式跟随系统」在服务端等价，
 * 服务端据 Cookie 缺失走 Accept-Language 协商。
 */
function setLanguagePreference(mode) {
    try {
        const value = mode === 'system' ? '' : mode;
        const maxAge = mode === 'system' ? 0 : LANG_COOKIE_MAX_AGE;
        document.cookie = `${LANG_COOKIE_NAME}=${value}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
    } catch (e) {
        console.warn('保存语言偏好失败:', e);
    }
    // 整页刷新：静态骨架与已渲染的动态区块一次到位，不会出现半页翻译
    window.location.reload();
}

function syncLangSegmented() {
    if (!elements.langSegmented) return;
    elements.langSegmented.querySelectorAll('.theme-segment').forEach((btn) => {
        const active = btn.dataset.langValue === state.langMode;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-checked', active ? 'true' : 'false');
    });
}

const elements = {
    taskList: document.getElementById('task-list'),
    taskCount: document.getElementById('task-count'),
    enabledCount: document.getElementById('enabled-count'),
    btnLogs: document.getElementById('btn-logs'),
    btnClean: document.getElementById('btn-clean'),
    btnRefresh: document.getElementById('btn-refresh'),
    btnEnableAll: document.getElementById('btn-enable-all'),
    btnDisableAll: document.getElementById('btn-disable-all'),
    btnMaximize: document.getElementById('btn-maximize'),
    btnSettings: document.getElementById('btn-settings'),
    btnSettingsMaximize: document.getElementById('btn-settings-maximize'),
    settingsModal: document.getElementById('settings-modal'),
    settingsModalClose: document.getElementById('settings-modal-close'),
    hideDisabledToggle: document.getElementById('hide-disabled-tasks'),
    themeSegmented: document.getElementById('theme-segmented'),
    langSegmented: document.getElementById('lang-segmented'),
    logsModal: document.getElementById('logs-modal'),
    runModal: document.getElementById('run-modal'),
    editModal: document.getElementById('edit-modal'),
    confirmModal: document.getElementById('confirm-modal'),
    modalClose: document.getElementById('modal-close'),
    runModalClose: document.getElementById('run-modal-close'),
    editModalClose: document.getElementById('edit-modal-close'),
    confirmModalClose: document.getElementById('confirm-modal-close'),
    fileList: document.getElementById('file-list'),
    logsViewer: document.getElementById('logs-viewer'),
    logsFilterContainer: document.getElementById('logs-filter-container') || document.createElement('div'),
    currentFilename: document.getElementById('current-filename'),
    runTaskName: document.getElementById('run-task-name'),
    runStatus: document.getElementById('run-status'),
    terminal: document.getElementById('terminal'),
    toastContainer: document.getElementById('toast-container'),
    confirmTitle: document.getElementById('confirm-title'),
    confirmMessage: document.getElementById('confirm-message'),
    confirmOk: document.getElementById('confirm-ok'),
    confirmCancel: document.getElementById('confirm-cancel'),
    // 编辑表单元素
    editForm: document.getElementById('edit-form'),
    editName: document.getElementById('edit-name'),
    editNameHint: document.getElementById('edit-name-hint'),
    editDescription: document.getElementById('edit-description'),
    editSchedule: document.getElementById('edit-schedule'),
    editScheduleHint: document.getElementById('edit-schedule-hint'),
    editScript: document.getElementById('edit-script'),
    editScriptHint: document.getElementById('edit-script-hint'),
    cronPreview: document.getElementById('cron-preview'),
    cronNextRun: document.getElementById('cron-next-run'),
    cronDesc: document.getElementById('cron-desc'),
    envList: document.getElementById('env-list'),
    envRowTemplate: document.getElementById('env-row-template'),
    btnAddEnv: document.getElementById('btn-add-env'),
    editSave: document.getElementById('edit-save'),
    editCancel: document.getElementById('edit-cancel')
};

// 编辑表单状态
const editState = {
    originalName: '',       // 当前正在编辑的任务原始名（URL 中使用）
    allTaskNames: [],       // 系统中所有任务名（用于唯一性校验）
    envAliasKeys: new Set(),// 当前任务的别名键集合（只读展示）
    enabled: false,         // 当前任务的启用状态（编辑时不修改）
    isSaving: false,
    cronTimer: null,        // cron 实时校验防抖
    scriptTimer: null       // script 实时校验防抖
};

const SORT_STORAGE_KEY = 'litecron_task_sort';
const HIDE_DISABLED_STORAGE_KEY = 'litecron_hide_disabled_tasks';

// 401 鉴权失效拦截：统一跳转登录页（fetch 包装，对所有 API 调用生效）
const _originalFetch = window.fetch;
window.fetch = function (input, init) {
    return _originalFetch.call(this, input, init).then(response => {
        if (response.status === 401) {
            window.location.href = '/login';
        }
        return response;
    });
};

function loadSortState() {
    try {
        const saved = localStorage.getItem(SORT_STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (parsed && parsed.column && ['asc', 'desc'].includes(parsed.direction)) {
                state.sortColumn = parsed.column;
                state.sortDirection = parsed.direction;
            }
        }
    } catch (e) {
        console.warn('读取排序状态失败:', e);
    }
}

function saveSortState() {
    try {
        if (state.sortColumn) {
            localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify({
                column: state.sortColumn,
                direction: state.sortDirection
            }));
        } else {
            localStorage.removeItem(SORT_STORAGE_KEY);
        }
    } catch (e) {
        console.warn('保存排序状态失败:', e);
    }
}

// ==================== 隐藏已禁用任务（偏好由设置弹窗记录到 localStorage） ====================

function syncHideDisabledToggle() {
    if (elements.hideDisabledToggle) {
        elements.hideDisabledToggle.checked = state.hideDisabledTasks;
    }
}

function loadHideDisabledState() {
    try {
        state.hideDisabledTasks = localStorage.getItem(HIDE_DISABLED_STORAGE_KEY) === 'true';
    } catch (e) {
        console.warn('读取隐藏禁用任务状态失败:', e);
    }
    syncHideDisabledToggle();
}

function saveHideDisabledState() {
    try {
        if (state.hideDisabledTasks) {
            localStorage.setItem(HIDE_DISABLED_STORAGE_KEY, 'true');
        } else {
            localStorage.removeItem(HIDE_DISABLED_STORAGE_KEY);
        }
    } catch (e) {
        console.warn('保存隐藏禁用任务状态失败:', e);
    }
}

function setHideDisabledTasks(hidden) {
    state.hideDisabledTasks = Boolean(hidden);
    syncHideDisabledToggle();
    saveHideDisabledState();
    renderTasks();
    lucide.createIcons();
}

// ==================== 主题模式（浅色 / 跟随系统 / 深色，纯浏览器偏好） ====================
// 只维护 <html data-theme>：浅色/深色的解析与配色全在 style.css 完成，
// 因此切换主题不需要重渲染任何内容（日志分组、任务标签由 CSS 级联自动跟随）。
// 「跟随系统」交给 prefers-color-scheme，系统主题变化浏览器会原生重算，无需 JS 参与。

const THEME_STORAGE_KEY = 'litecron_theme';
const THEME_MODES = ['light', 'system', 'dark'];

function loadThemePreference() {
    try {
        const saved = localStorage.getItem(THEME_STORAGE_KEY);
        if (THEME_MODES.includes(saved)) state.theme = saved;
    } catch (e) {
        console.warn('读取主题偏好失败:', e);
    }
    return state.theme;
}

function saveThemePreference(mode) {
    try {
        localStorage.setItem(THEME_STORAGE_KEY, mode);
    } catch (e) {
        // 存储不可用（隐私模式等）：本次会话内仍然生效，只是不再持久化
        console.warn('保存主题偏好失败:', e);
    }
}

function syncThemeSegmented() {
    if (!elements.themeSegmented) return;
    elements.themeSegmented.querySelectorAll('.theme-segment').forEach((btn) => {
        const active = btn.dataset.themeValue === state.theme;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-checked', active ? 'true' : 'false');
    });
}

// 「跟随系统」由 JS 解析成具体的 light/dark 再写入 data-theme。
// 这样系统主题变化时能先起淡化再改属性，与手动切换走完全相同的路径、完全同步。
// CSS 里 @media (prefers-color-scheme: light) { :root[data-theme="system"] } 仍保留：
// 首屏（脚本未执行前）与 JS 不可用时由它兜底。
const THEME_DARK_QUERY = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
const THEME_REDUCED_MOTION = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

function resolveTheme(mode) {
    if (mode !== 'system') return mode;
    return THEME_DARK_QUERY && THEME_DARK_QUERY.matches ? 'dark' : 'light';
}

// 整页淡化靠同文档 View Transition 的两张快照完成：过渡期间页面只是两张静态位图
// 在合成器上混合，逐帧的样式重算、全页重绘与遮罩 backdrop-filter 重算全部归零。
// 不支持该能力、或用户要求减少动态效果时直接切色，不退化成逐元素动画。
function canCrossfadeTheme() {
    return typeof document.startViewTransition === 'function'
        && !(THEME_REDUCED_MOTION && THEME_REDUCED_MOTION.matches);
}

// 快照窗口期（配合 style.css 的 html.theme-snapshotting）。
// 元素自带的 transition 会让「新快照」拍到的是过渡中途的旧色，于是带 transition 的
// 卡片、按钮、弹窗底色在淡化期间明显落后于没有 transition 的区域（实测落后 60~90ms）。
// 窗口期内统一禁掉 transition，新快照必然取到终值。
const THEME_SNAPSHOT_CLASS = 'theme-snapshotting';

let appliedTheme = null;  // 上一次实际生效的 light/dark

function writeTheme(concrete) {
    // 解析成具体主题后没变（如浅色 -> 跟随系统且系统也是浅色）：不做无谓淡化
    if (appliedTheme === concrete) return;

    const root = document.documentElement;
    const commit = () => {
        appliedTheme = concrete;
        root.dataset.theme = concrete;
    };

    // 首屏第一次应用必须同步直写：此刻 data-theme 已由 <head> 内联脚本给到首帧终值，
    // 走淡化会变成「从另一配色淡入」，违反「首次载入不播放过渡」
    if (appliedTheme === null || !canCrossfadeTheme()) {
        commit();
        return;
    }

    // 必须在改 data-theme 之前挂上，才能让这次样式重算在无 transition 的前提下完成
    const endSnapshotWindow = () => root.classList.remove(THEME_SNAPSHOT_CLASS);
    root.classList.add(THEME_SNAPSHOT_CLASS);

    let transition = null;
    try {
        transition = document.startViewTransition(commit);
    } catch (e) {
        endSnapshotWindow();
        commit();
        return;
    }
    // finished 在过渡被跳过时以 AbortError 拒绝，两个分支都要摘掉窗口期 class。
    // 此时元素值已是终值，摘掉 class 不会重新触发任何过渡。
    if (transition && transition.finished) {
        transition.finished.then(endSnapshotWindow, endSnapshotWindow);
    } else {
        setTimeout(endSnapshotWindow, 400);
    }
}

function applyTheme(mode, persist) {
    const next = THEME_MODES.includes(mode) ? mode : 'system';
    state.theme = next;
    writeTheme(resolveTheme(next));
    syncThemeSegmented();
    if (persist) saveThemePreference(next);
}

// ==================== 日志分组与着色渲染 ====================

function parseLogGroups(content) {
    const lines = content.split('\n');
    const groups = [];
    let currentGroup = null;
    const taskRegex = /\[TASK:([^\]]+)\]/;

    for (const line of lines) {
        const match = line.match(taskRegex);
        let taskName = null;
        if (match) {
            taskName = match[1];
        }
        // 无 [TASK:] 标签的行统一归"系统"组（taskName 保持 null），不做旧格式回退解析

        if (currentGroup && currentGroup.task === taskName) {
            currentGroup.lines.push(line);
        } else {
            currentGroup = { task: taskName, lines: [line] };
            groups.push(currentGroup);
        }
    }

    return groups;
}

function buildLogFilter(groups) {
    const tasks = [];
    const seen = new Set();
    // 按日志分组出现的顺序去重，保持首次出现顺序
    for (const g of groups) {
        if (g.task && !seen.has(g.task)) {
            seen.add(g.task);
            tasks.push(g.task);
        }
    }
    return tasks;
}

function renderLogGroups(groups, filter) {
    const container = document.createElement('div');
    container.className = 'log-groups-container';

    for (const group of groups) {
        // 选中具体任务时仅显示该任务分组（系统日志 task 为 null，会被一并过滤）；选中"全部"时才显示系统日志
        if (filter !== 'all' && group.task !== filter) continue;

        const section = document.createElement('div');
        section.className = 'log-group';

        if (group.task) {
            section.classList.add('task-colored');
            section.style.setProperty('--task-hue', taskHue(group.task));

            const header = document.createElement('div');
            header.className = 'log-group-header';
            header.innerHTML = `<i data-lucide="chevron-down" class="log-group-chevron"></i><span class="log-group-task-name">${escapeHtml(group.task)}</span><span class="log-group-line-count">${T('logs.group_lines', { n: group.lines.length })}</span>`;
            section.appendChild(header);
        } else {
            section.classList.add('log-group-system');
            const header = document.createElement('div');
            header.className = 'log-group-header';
            header.innerHTML = `<i data-lucide="chevron-down" class="log-group-chevron"></i><span class="log-group-task-name">${T('logs.group_system')}</span><span class="log-group-line-count">${T('logs.group_lines', { n: group.lines.length })}</span>`;
            section.appendChild(header);
        }

        const body = document.createElement('div');
        body.className = 'log-group-body';
        for (const line of group.lines) {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'log-line';
            // 提取并高亮日志级别
            const levelMatch = line.match(/\[(INF|ERR|WAR|DBG)\]/);
            let escapedLine = escapeHtml(line);
            if (levelMatch) {
                const levelMap = { 'INF': 'info', 'ERR': 'error', 'WAR': 'warning', 'DBG': 'debug' };
                escapedLine = escapedLine.replace(
                    `[${levelMatch[1]}]`,
                    `<span class="log-level log-level-${levelMap[levelMatch[1]]}">[${levelMatch[1]}]</span>`
                );
            }
            // 高亮任务标签
            if (group.task) {
                escapedLine = escapedLine.replace(
                    `[TASK:${escapeHtml(group.task)}]`,
                    `<span class="log-task-tag">[TASK:${escapeHtml(group.task)}]</span>`
                );
            }
            lineDiv.innerHTML = escapedLine;
            body.appendChild(lineDiv);
        }
        section.appendChild(body);

        // 折叠/展开交互：点击标题栏切换同组 body 的 collapsed class 与箭头图标
        const header = section.querySelector('.log-group-header');
        header.style.cursor = 'pointer';
        header.addEventListener('click', () => {
            const collapsed = body.classList.toggle('collapsed');
            const chevron = header.querySelector('.log-group-chevron');
            if (chevron) {
                chevron.setAttribute('data-lucide', collapsed ? 'chevron-right' : 'chevron-down');
                if (window.lucide) window.lucide.createIcons();
            }
        });

        container.appendChild(section);
    }

    return container;
}

function renderTaskFilter(groups) {
    const tasks = buildLogFilter(groups);
    const container = document.createElement('div');
    container.className = 'log-filter-bar';

    const label = document.createElement('span');
    label.className = 'log-filter-label';
    label.textContent = T('logs.filter_label');
    container.appendChild(label);

    const btnAll = document.createElement('button');
    btnAll.className = 'log-filter-btn' + (state.currentLogFilter === 'all' ? ' active' : '');
    btnAll.textContent = T('logs.filter_all');
    btnAll.onclick = () => {
        state.currentLogFilter = 'all';
        refreshLogView();
    };
    container.appendChild(btnAll);

    for (const task of tasks) {
        const isActive = state.currentLogFilter === task;
        const btn = document.createElement('button');
        // task-colored + --task-hue：选中态的边框/描边/字色由 CSS 按当前主题派生
        btn.className = 'log-filter-btn task-colored' + (isActive ? ' active' : '');
        btn.textContent = task;
        btn.style.setProperty('--task-hue', taskHue(task));
        btn.onclick = () => {
            state.currentLogFilter = task;
            refreshLogView();
        };
        container.appendChild(btn);
    }

    return container;
}

function refreshLogView() {
    if (!state.currentLogGroups.length) return;
    const viewer = elements.logsViewer;
    const filterContainer = elements.logsFilterContainer;

    filterContainer.innerHTML = '';
    const filterBar = renderTaskFilter(state.currentLogGroups);
    filterContainer.appendChild(filterBar);

    viewer.innerHTML = '';
    const groupsContainer = renderLogGroups(state.currentLogGroups, state.currentLogFilter);
    viewer.appendChild(groupsContainer);

    // 初始化动态生成的 lucide 图标（折叠箭头等），确保首次渲染即显示
    if (window.lucide) lucide.createIcons({ root: viewer });

    viewer.scrollTop = viewer.scrollHeight;
}

function init() {
    loadSortState();
    loadHideDisabledState();
    // 首屏主题已由 <head> 内联脚本应用，这里只把控件状态与存储值对齐
    applyTheme(loadThemePreference(), false);
    // 语言控件状态取自服务端注入的 LANG_MODE，不回读 Cookie，避免两者不一致
    syncLangSegmented();
    bindEvents();
    loadData(false);
}

function bindEvents() {
    elements.btnRefresh.addEventListener('click', () => {
        elements.btnRefresh.classList.add('rotating');
        loadData(true);
        setTimeout(() => elements.btnRefresh.classList.remove('rotating'), 500);
    });
    
    elements.btnLogs.addEventListener('click', () => {
        openModal('logs');
        loadLogs();
        lucide.createIcons({ root: elements.logsModal });
    });
    
    elements.btnEnableAll.addEventListener('click', () => {
        showConfirm({
            title: T('tasks.batch.confirm_enable_title'),
            message: T('tasks.batch.confirm_enable_message'),
            onConfirm: () => batchToggleTasks(true)
        });
    });
    
    elements.btnDisableAll.addEventListener('click', () => {
        showConfirm({
            title: T('tasks.batch.confirm_disable_title'),
            message: T('tasks.batch.confirm_disable_message'),
            onConfirm: () => batchToggleTasks(false)
        });
    });

    elements.btnSettings.addEventListener('click', () => {
        syncHideDisabledToggle();
        openModal('settings');
        if (typeof window.loadSettingsModal === 'function') {
            window.loadSettingsModal();
        }
        lucide.createIcons({ root: elements.settingsModal });
    });

    elements.btnSettingsMaximize.addEventListener('click', () => {
        toggleMaximize(elements.btnSettingsMaximize);
    });

    elements.hideDisabledToggle.addEventListener('change', (e) => {
        setHideDisabledTasks(e.target.checked);
    });

    if (elements.themeSegmented) {
        elements.themeSegmented.addEventListener('click', (e) => {
            const btn = e.target.closest('.theme-segment');
            if (!btn) return;
            applyTheme(btn.dataset.themeValue, true);
        });
    }

    // 语言切换：写 Cookie 后整页刷新，避免只有部分区域被翻译
    if (elements.langSegmented) {
        elements.langSegmented.addEventListener('click', (e) => {
            const btn = e.target.closest('.theme-segment');
            if (!btn) return;
            const next = btn.dataset.langValue;
            if (!next || next === state.langMode) return;
            setLanguagePreference(next);
        });
    }

    // 「跟随系统」下操作系统主题变化：由 JS 重新解析并写入具体主题，
    // 与手动切换走同一条路径，因此过渡窗口与同步性完全一致
    if (THEME_DARK_QUERY) {
        const onSchemeChange = () => {
            if (state.theme === 'system') writeTheme(resolveTheme('system'));
        };
        if (THEME_DARK_QUERY.addEventListener) {
            THEME_DARK_QUERY.addEventListener('change', onSchemeChange);
        } else if (THEME_DARK_QUERY.addListener) {
            THEME_DARK_QUERY.addListener(onSchemeChange);
        }
    }

    // 其他标签页修改显示偏好时，实时同步首页列表与设置弹窗开关
    window.addEventListener('storage', (e) => {
        if (e.key === HIDE_DISABLED_STORAGE_KEY) {
            loadHideDisabledState();
            renderTasks();
            lucide.createIcons();
        }
    });

    elements.btnClean.addEventListener('click', () => {
        showConfirm({
            title: T('logs.confirm_clean_title'),
            message: T('logs.confirm_clean_message'),
            onConfirm: cleanLogs
        });
    });
    
    elements.btnMaximize.addEventListener('click', () => {
        toggleMaximize(elements.btnMaximize);
    });
    
    elements.modalClose.addEventListener('click', () => closeModal('logs'));
    elements.runModalClose.addEventListener('click', () => closeModal('run'));
    elements.editModalClose.addEventListener('click', () => closeModal('edit'));
    elements.editCancel.addEventListener('click', () => closeModal('edit'));
    elements.settingsModalClose.addEventListener('click', () => closeModal('settings'));
    
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            const modal = e.target.closest('.modal');
            if (modal) {
                const modalType = modal.id.replace('-modal', '');
                closeModal(modalType);
            }
        });
    });
    
    elements.confirmModalClose.addEventListener('click', () => closeModal('confirm'));
    elements.confirmCancel.addEventListener('click', () => closeModal('confirm'));
    
    // 编辑表单事件
    elements.btnAddEnv.addEventListener('click', () => addEnvRow());
    elements.envList.addEventListener('click', (e) => {
        if (e.target.classList.contains('env-remove')) {
            e.target.closest('.env-row').remove();
        }
    });
    elements.envList.addEventListener('input', (e) => {
        if (e.target.classList.contains('env-value')) {
            autoGrowTextarea(e.target);
        }
    });
    // 实时校验：Cron
    elements.editSchedule.addEventListener('input', () => {
        clearTimeout(editState.cronTimer);
        editState.cronTimer = setTimeout(validateCronRealtime, 300);
    });
    // 实时校验：脚本路径
    elements.editScript.addEventListener('input', () => {
        clearTimeout(editState.scriptTimer);
        editState.scriptTimer = setTimeout(validateScriptRealtime, 300);
    });
    // 实时校验：任务名唯一性
    elements.editName.addEventListener('input', validateNameRealtime);
    // 保存
    elements.editSave.addEventListener('click', saveTaskEdit);
    // 阻止表单默认提交
    elements.editForm.addEventListener('submit', (e) => {
        e.preventDefault();
        saveTaskEdit();
    });
    
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAllModals();
        }
    });

    // 表头排序事件
    document.querySelectorAll('#task-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            handleSort(column);
        });
    });

    // 退出登录（仅在鉴权启用时渲染）
    const btnLogout = document.getElementById('btn-logout');
    if (btnLogout) {
        btnLogout.addEventListener('click', async () => {
            try {
                await fetch('/logout', { method: 'POST' });
            } catch (e) {
                // 忽略网络错误，仍跳转登录页
            }
            window.location.href = '/login';
        });
    }
}

async function loadData(reload = false) {
    try {
        if (reload) {
            try {
                const reloadResponse = await fetch('/api/reload', { method: 'POST' });
                const reloadData = await reloadResponse.json();
                if (reloadData.success) {
                    showToast(reloadData.message, 'success');
                } else {
                    showToast(reloadData.message || T('tasks.reload_failed'), 'warning');
                }
            } catch (reloadError) {
                console.error('重载配置失败:', reloadError);
                showToast(T('tasks.reload_failed'), 'error');
            }
        }
        await loadTasks();
    } catch (error) {
        console.error('加载数据失败:', error);
        showToast(T('tasks.load_failed'), 'error');
    }
}

async function loadTasks() {
    try {
        elements.taskList.innerHTML = `
            <tr class="loading-row">
                <td colspan="6" class="loading-cell">
                    <div class="spinner"></div>
                    <span>${T('common.loading')}</span>
                </td>
            </tr>
        `;
        
        const response = await fetch('/api/tasks');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        state.tasks = data.tasks || [];
        
        const enabledCount = state.tasks.filter(t => t.enabled).length;
        elements.taskCount.textContent = state.tasks.length || 0;
        elements.enabledCount.textContent = enabledCount;
        
        if (state.tasks.length === 0 && data.config_exists === false) {
            elements.taskList.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-state">
                        <i data-lucide="list-checks" class="empty-icon"></i>
                        <div class="empty-text">${T('tasks.config_missing')}</div>
                        <div class="empty-subtext">${T('tasks.config_missing_hint')}</div>
                    </td>
                </tr>
            `;
            return;
        }
        
        renderTasks();
        updateSortIcons();
        lucide.createIcons();

    } catch (error) {
        console.error('加载任务失败:', error);
        elements.taskList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <i data-lucide="alert-triangle" class="empty-icon"></i>
                    <div class="empty-text">${T('tasks.load_failed_row', { message: error.message })}</div>
                    <div class="empty-subtext">
                        <button onclick="loadTasks()" class="btn btn-secondary" style="margin-top: 12px;">
                            <i data-lucide="refresh-cw" class="btn-icon"></i> ${T('common.retry')}
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }
}

function handleSort(column) {
    if (state.sortColumn === column) {
        if (state.sortDirection === 'asc') {
            state.sortDirection = 'desc';
        } else {
            state.sortColumn = null;
            state.sortDirection = 'asc';
        }
    } else {
        state.sortColumn = column;
        state.sortDirection = 'asc';
    }
    renderTasks();
    updateSortIcons();
    saveSortState();
}

function updateSortIcons() {
    document.querySelectorAll('#task-table th.sortable').forEach(th => {
        const column = th.dataset.sort;
        const icon = th.querySelector('.sort-icon');
        if (!icon) return;
        th.classList.remove('active');
        if (state.sortColumn === column) {
            th.classList.add('active');
            icon.setAttribute('data-lucide', state.sortDirection === 'asc' ? 'arrow-up' : 'arrow-down');
        } else {
            icon.setAttribute('data-lucide', 'arrow-up-down');
        }
    });
    lucide.createIcons({ root: document.getElementById('task-table') });
}

function getSortedTasks(tasks) {
    if (!state.sortColumn) return tasks;
    const col = state.sortColumn;
    const dir = state.sortDirection === 'asc' ? 1 : -1;
    return [...tasks].sort((a, b) => {
        let valA, valB;
        if (col === 'enabled') {
            valA = a.enabled ? 1 : 0;
            valB = b.enabled ? 1 : 0;
        } else {
            valA = (a[col] || '').toString().toLowerCase();
            valB = (b[col] || '').toString().toLowerCase();
        }
        if (valA < valB) return -1 * dir;
        if (valA > valB) return 1 * dir;
        return 0;
    });
}

function renderTasks() {
    const mobileTaskList = document.getElementById('mobile-task-list');
    const visibleTasks = state.hideDisabledTasks
        ? state.tasks.filter(t => t.enabled)
        : state.tasks;
    const tasks = getSortedTasks(visibleTasks);

    if (tasks.length === 0) {
        const hiddenCount = state.tasks.length - visibleTasks.length;
        const emptyHtml = hiddenCount > 0
            ? `
                <i data-lucide="eye-off" class="empty-icon"></i>
                <div class="empty-text">${T('tasks.empty_hidden', { n: hiddenCount })}</div>
                <div class="empty-subtext">
                    <button onclick="setHideDisabledTasks(false)" class="btn btn-secondary" style="margin-top: 12px;">
                        <i data-lucide="eye" class="btn-icon"></i> ${T('tasks.show_all')}
                    </button>
                </div>
              `
            : `
                <i data-lucide="list-checks" class="empty-icon"></i>
                <div class="empty-text">${T('tasks.empty')}</div>
                <div class="empty-subtext">${T('tasks.empty_hint')}</div>
              `;

        elements.taskList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">${emptyHtml}</td>
            </tr>
        `;
        
        if (mobileTaskList) {
            mobileTaskList.innerHTML = `<div class="empty-state">${emptyHtml}</div>`;
        }
        return;
    }
    
    elements.taskList.innerHTML = tasks.map(task => `
        <tr data-task-name="${task.name}" class="task-row">
            <td>
                <span class="task-status ${task.enabled ? 'enabled' : 'disabled'}">
                    <span class="status-dot"></span>
                    ${task.enabled ? T('tasks.status.enabled') : T('tasks.status.disabled')}
                </span>
            </td>
            <td>
                <span class="task-name">${task.name}</span>
            </td>
            <td>
                <span class="schedule-expr">${task.schedule}</span>
            </td>
            <td>
                <span class="task-desc" title="${task.description || ''}">
                    ${task.description || '-'}
                </span>
            </td>
            <td>
                ${task.next_run ? 
                    `<span class="next-run">
                        <i data-lucide="clock" class="next-run-icon"></i>
                        ${task.next_run}
                    </span>` : 
                    '<span class="next-run">-</span>'}
            </td>
            <td>
                <div class="task-actions">
                    <button class="btn-action btn-run"
                            onclick="runTask('${task.name}')"
                            ${!task.enabled ? 'disabled' : ''}
                            title="${T('tasks.action.run_title')}">
                        <i data-lucide="play" class="btn-action-icon"></i> ${T('tasks.action.run')}
                    </button>
                    <button class="btn-action btn-toggle ${task.enabled ? 'disable' : 'enable'}"
                            onclick="toggleTask('${task.name}', ${!task.enabled})"
                            title="${task.enabled ? T('tasks.action.disable') : T('tasks.action.enable')}">
                        ${task.enabled ? `<i data-lucide="pause" class="btn-action-icon"></i> ${T('tasks.action.disable')}` : `<i data-lucide="play" class="btn-action-icon"></i> ${T('tasks.action.enable')}`}
                    </button>
                    <button class="btn-action btn-edit"
                            onclick="editTask('${task.name}')"
                            title="${T('tasks.action.edit_title')}">
                        <i data-lucide="pencil" class="btn-action-icon"></i> ${T('tasks.action.edit')}
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
    
    if (mobileTaskList) {
        mobileTaskList.innerHTML = tasks.map(task => `
            <div class="mobile-task-card" data-task-name="${task.name}">
                <div class="mobile-task-header">
                    <span class="mobile-task-name">${task.name}</span>
                    <span class="mobile-task-status ${task.enabled ? 'enabled' : 'disabled'}">
                        <span class="mobile-task-status-dot"></span>
                        ${task.enabled ? T('tasks.status.enabled') : T('tasks.status.disabled')}
                    </span>
                </div>
                <div class="mobile-task-info">
                    <div class="mobile-task-info-item">
                        <span class="mobile-task-info-label">${T('tasks.mobile.schedule')}</span>
                        <span class="mobile-task-info-value mono">${task.schedule}</span>
                    </div>
                    <div class="mobile-task-info-item">
                        <span class="mobile-task-info-label">${T('tasks.mobile.description')}</span>
                        <span class="mobile-task-info-value">${task.description || '-'}</span>
                    </div>
                    <div class="mobile-task-info-item">
                        <span class="mobile-task-info-label">${T('tasks.mobile.next')}</span>
                        <span class="mobile-task-info-value">${task.next_run || '-'}</span>
                    </div>
                </div>
                <div class="mobile-task-actions">
                    <button class="btn-action btn-run"
                            onclick="runTask('${task.name}')"
                            ${!task.enabled ? 'disabled' : ''}
                            title="${T('tasks.action.run_title')}">
                        <i data-lucide="play" class="btn-action-icon"></i> ${T('tasks.action.run')}
                    </button>
                    <button class="btn-action btn-toggle ${task.enabled ? 'disable' : 'enable'}"
                            onclick="toggleTask('${task.name}', ${!task.enabled})"
                            title="${task.enabled ? T('tasks.action.disable') : T('tasks.action.enable')}">
                        ${task.enabled ? `<i data-lucide="pause" class="btn-action-icon"></i> ${T('tasks.action.disable')}` : `<i data-lucide="play" class="btn-action-icon"></i> ${T('tasks.action.enable')}`}
                    </button>
                    <button class="btn-action btn-edit"
                            onclick="editTask('${task.name}')"
                            title="${T('tasks.action.edit_title')}">
                        <i data-lucide="pencil" class="btn-action-icon"></i> ${T('tasks.action.edit')}
                    </button>
                </div>
            </div>
        `).join('');
    }
}

async function runTask(taskName) {
    if (state.isRunning) return;
    
    state.isRunning = true;
    elements.runTaskName.textContent = taskName;
    elements.runStatus.textContent = T('run.preparing');
    elements.terminal.innerHTML = `<div class="terminal-line system">${T('run.waiting')}</div>`;
    
    openModal('run');
    
    try {
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskName)}/run`, {
            method: 'POST'
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            const lines = text.trim().split('\n');
            
            for (const line of lines) {
                if (!line.trim()) continue;
                
                try {
                    const data = JSON.parse(line);
                    handleRunOutput(data);
                } catch (e) {
                    appendTerminal(elements.terminal, line);
                }
            }
        }
        
    } catch (error) {
        appendTerminal(elements.terminal, T('run.error_prefix', { message: error.message }), 'error');
        showToast(T('run.toast_request_failed'), 'error');
    } finally {
        state.isRunning = false;
    }
}

function handleRunOutput(data) {
    if (data.status === 'started') {
        elements.terminal.innerHTML = '';
        appendTerminal(elements.terminal, data.message, 'system');
        elements.runStatus.textContent = T('run.running');
    } else if (data.status === 'running') {
        appendTerminal(elements.terminal, data.output);
        elements.terminal.scrollTop = elements.terminal.scrollHeight;
    } else if (data.status === 'completed') {
        const type = data.success ? 'success' : 'error';
        appendTerminal(elements.terminal, data.message, type);
        elements.runStatus.textContent = data.success ? T('run.completed') : T('run.failed');
        
        if (data.success) {
            showToast(T('run.toast_success'), 'success');
        } else {
            showToast(T('run.toast_failed'), 'error');
        }
    } else if (data.status === 'error') {
        appendTerminal(elements.terminal, data.message, 'error');
        elements.runStatus.textContent = T('run.error');
        showToast(data.message, 'error');
    }
}

function appendTerminal(terminal, text, type = '') {
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    line.textContent = text;
    terminal.appendChild(line);
}

async function toggleTask(taskName, enable) {
    try {
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskName)}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            loadTasks();
        } else {
            showToast(data.message || T('common.action_failed'), 'error');
        }
        
    } catch (error) {
        console.error('切换任务失败:', error);
        showToast(T('common.action_failed'), 'error');
    }
}

async function batchToggleTasks(enabled) {
    try {
        const btn = enabled ? elements.btnEnableAll : elements.btnDisableAll;
        btn.disabled = true;
        btn.innerHTML = `<i data-lucide="loader-2" class="btn-icon"></i> ${T('common.processing')}`;
        
        const response = await fetch('/api/tasks/batch/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            loadTasks();
        } else {
            showToast(data.message || T('common.action_failed'), 'error');
        }
        
    } catch (error) {
        console.error('批量操作失败:', error);
        showToast(T('common.action_failed'), 'error');
    } finally {
        const btn = enabled ? elements.btnEnableAll : elements.btnDisableAll;
        btn.disabled = false;
        btn.innerHTML = enabled 
            ? `<i data-lucide="play" class="btn-icon"></i> ${T('tasks.btn.enable_all')}`
            : `<i data-lucide="pause" class="btn-icon"></i> ${T('tasks.btn.disable_all')}`;
        lucide.createIcons({ root: btn });
    }
}

async function loadLogs() {
    elements.fileList.innerHTML = `<li class="file-item loading">${T('common.loading')}</li>`;
    elements.logsViewer.innerHTML = `<div class="log-line" style="color: var(--text-muted); padding: 16px;">${T('logs.click_file')}</div>`;
    elements.logsFilterContainer.innerHTML = '';
    elements.currentFilename.textContent = T('logs.select_file');
    state.currentLogGroups = [];
    state.currentLogFilter = 'all';
    
    try {
        const response = await fetch('/api/logs');
        const data = await response.json();
        
        state.logs = data.logs || [];
        state.logs.sort((a, b) => b.modified.localeCompare(a.modified));

        if (state.logs.length === 0) {
            elements.fileList.innerHTML = `<li class="file-item">${T('logs.none')}</li>`;
            return;
        }
        
        elements.fileList.innerHTML = state.logs.map((log, index) => `
            <li class="file-item" data-filename="${log.name}" onclick="viewLog('${log.name}', ${index})">
                <span class="file-name">${log.name}</span>
                <span class="file-meta">${log.size_human} · ${log.modified}</span>
            </li>
        `).join('');
        
        if (state.logs.length > 0) {
            viewLog(state.logs[0].name, 0);
        }
        
    } catch (error) {
        console.error('加载日志失败:', error);
        elements.fileList.innerHTML = `<li class="file-item">${T('common.failed')}</li>`;
    }
}

async function viewLog(filename, index) {
    document.querySelectorAll('.file-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
    });
    
    elements.currentFilename.textContent = filename;
    elements.logsViewer.innerHTML = `<div class="log-line" style="color: var(--text-muted); padding: 16px;">${T('common.loading')}</div>`;
    elements.logsFilterContainer.innerHTML = '';
    state.currentLogFilename = filename;
    state.currentLogFilter = 'all';
    
    try {
        const response = await fetch(`/api/logs/${encodeURIComponent(filename)}?limit=1000`);
        const data = await response.json();
        
        if (data.error) {
            elements.logsViewer.innerHTML = `<div class="log-line" style="color: var(--accent-danger); padding: 16px;">${data.error}</div>`;
        } else {
            state.currentLogGroups = parseLogGroups(data.content);
            refreshLogView();
        }
        
    } catch (error) {
        console.error('加载日志失败:', error);
        elements.logsViewer.innerHTML = `<div class="log-line" style="color: var(--accent-danger); padding: 16px;">${T('common.failed')}</div>`;
        elements.logsFilterContainer.innerHTML = '';
    }
}

async function cleanLogs() {
    try {
        elements.btnClean.disabled = true;
        elements.btnClean.innerHTML = `<i data-lucide="loader-2" class="btn-icon"></i> ${T('logs.cleaning')}`;
        
        const response = await fetch('/api/clean', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showToast(T('logs.cleaned'), 'success');
            closeModal('confirm');
            loadLogs();
        } else {
            showToast(data.message || T('logs.clean_failed'), 'error');
        }
        
    } catch (error) {
        console.error('清理失败:', error);
        showToast(T('logs.clean_request_failed'), 'error');
    } finally {
        elements.btnClean.disabled = false;
        elements.btnClean.innerHTML = `<i data-lucide="trash-2" class="btn-icon"></i> ${T('logs.btn.clean')}`;
    }
}

function openModal(type) {
    const modal = document.getElementById(`${type}-modal`);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(type) {
    const modal = document.getElementById(`${type}-modal`);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('active');
    });
    document.body.style.overflow = '';
}

function toggleMaximize(btn) {
    // 从按钮向上找到所属弹窗，日志与设置弹窗共用同一套最大化逻辑
    const modalContent = btn.closest('.modal').querySelector('.modal-content');
    const isMaximized = modalContent.classList.toggle('maximized');
    
    const btnIcon = btn.querySelector('.btn-icon');
    if (isMaximized) {
        btnIcon.setAttribute('data-lucide', 'minimize-2');
        btn.title = T('common.restore');
    } else {
        btnIcon.setAttribute('data-lucide', 'maximize-2');
        btn.title = T('common.maximize');
    }
    lucide.createIcons({ root: btn });
}

let confirmCallback = null;

function showConfirm(options) {
    const { title, message, onConfirm } = options;
    
    elements.confirmTitle.textContent = title || T('common.confirm');
    elements.confirmMessage.textContent = message || '';
    confirmCallback = onConfirm;
    
    openModal('confirm');
}

elements.confirmOk.addEventListener('click', () => {
    closeModal('confirm');
    if (confirmCallback) {
        confirmCallback();
        confirmCallback = null;
    }
});

function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: 'check-circle',
        error: 'x-circle',
        warning: 'alert-triangle',
        info: 'info'
    };
    
    toast.innerHTML = `
        <i data-lucide="${icons[type]}" class="toast-icon"></i>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="removeToast(this.parentElement)">&times;</button>
    `;
    
    elements.toastContainer.appendChild(toast);
    lucide.createIcons({ root: toast });
    
    setTimeout(() => {
        removeToast(toast);
    }, duration);
}

function removeToast(toast) {
    if (!toast || !toast.parentElement) return;
    toast.style.animation = 'toastOut 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards';
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 300);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 任务编辑 ====================

async function editTask(taskName) {
    // 打开模态并加载任务数据
    openModal('edit');
    resetEditForm();
    setHint(elements.editNameHint, T('edit.loading'), 'info');
    elements.editSave.disabled = true;
    elements.editSave.innerHTML = `<i data-lucide="loader-2" class="btn-icon"></i> ${T('edit.loading')}`;
    
    try {
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskName)}/detail`);
        const data = await response.json();
        
        if (!data.success || !data.task) {
            showToast(data.message || T('edit.load_failed'), 'error');
            closeModal('edit');
            return;
        }
        
        const task = data.task;
        editState.originalName = task.original_name || taskName;
        editState.allTaskNames = task.all_task_names || [];
        editState.enabled = !!task.enabled;
        editState.envAliasKeys = new Set(
            (task.env || []).filter(e => e.is_alias).map(e => e.key)
        );

        elements.editName.value = task.name;
        elements.editDescription.value = task.description;
        elements.editSchedule.value = task.schedule;
        elements.editScript.value = task.script;
        
        // 渲染 env 列表
        elements.envList.innerHTML = '';
        if (task.env && task.env.length > 0) {
            task.env.forEach(e => addEnvRow(e.key, e.value, e.is_alias, e.alias_target));
        } else {
            addEnvRow();
        }
        
        setHint(elements.editNameHint, '', '');
        elements.editSave.disabled = false;
        elements.editSave.innerHTML = `<i data-lucide="save" class="btn-icon"></i> ${T('edit.save')}`;
        
        // 触发实时校验预览
        validateCronRealtime();
        validateScriptRealtime();
    } catch (error) {
        console.error('加载任务详情失败:', error);
        showToast(T('edit.detail_failed'), 'error');
        closeModal('edit');
    }
}

function resetEditForm() {
    elements.editForm.reset();
    elements.envList.innerHTML = '';
    editState.originalName = '';
    editState.allTaskNames = [];
    editState.enabled = false;
    editState.envAliasKeys = new Set();
    setHint(elements.editNameHint, '', '');
    setHint(elements.editScheduleHint, '', '');
    setHint(elements.editScriptHint, '', '');
    elements.cronPreview.hidden = true;
    elements.editName.classList.remove('invalid', 'valid');
    elements.editSchedule.classList.remove('invalid', 'valid');
    elements.editScript.classList.remove('invalid', 'valid');
}

function addEnvRow(key = '', value = '', isAlias = false, aliasTarget = null) {
    const fragment = elements.envRowTemplate.content.cloneNode(true);
    const row = fragment.querySelector('.env-row');
    const keyInput = row.querySelector('.env-key');
    const valueInput = row.querySelector('.env-value');
    
    keyInput.value = key;
    valueInput.value = value;
    
    if (isAlias) {
        row.classList.add('env-row-alias');
        // 别名键：键名可改但会破坏引用（仅提示），值只读
        valueInput.readOnly = true;
        valueInput.title = T('edit.alias_value_title', { anchor: aliasTarget });
        const badge = document.createElement('span');
        badge.className = 'env-alias-badge';
        badge.innerHTML = `<i data-lucide="link" style="width: 12px; height: 12px; margin-right: 2px;"></i> ${aliasTarget}`;
        badge.title = T('edit.alias_badge_title');
        row.querySelector('.env-key-col').appendChild(badge);
    }
    
    elements.envList.appendChild(row);
    autoGrowTextarea(valueInput);
    lucide.createIcons({ root: row });
}

function autoGrowTextarea(el) {
    el.style.height = 'auto';
    const minHeight = 38;
    const maxHeight = 120;
    el.style.height = Math.min(Math.max(el.scrollHeight, minHeight), maxHeight) + 'px';
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

function setHint(el, message, type) {
    if (!el) return;
    el.textContent = message || '';
    el.className = 'form-field-hint' + (type ? ` hint-${type}` : '');
}

async function validateCronRealtime() {
    const expr = elements.editSchedule.value.trim();
    if (!expr) {
        setHint(elements.editScheduleHint, '', '');
        elements.cronPreview.hidden = true;
        elements.editSchedule.classList.remove('valid', 'invalid');
        return;
    }
    
    try {
        const response = await fetch('/api/validate/cron', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ schedule: expr })
        });
        const data = await response.json();
        
        if (data.valid) {
            elements.editSchedule.classList.remove('valid', 'invalid');
            setHint(elements.editScheduleHint, '', '');
            elements.cronPreview.hidden = false;
            elements.cronNextRun.textContent = data.next_run || '-';
            elements.cronDesc.textContent = data.description || '-';
        } else {
            elements.editSchedule.classList.remove('valid');
            elements.editSchedule.classList.add('invalid');
            setHint(elements.editScheduleHint, `✗ ${data.error}`, 'error');
            elements.cronPreview.hidden = true;
        }
    } catch (error) {
        setHint(elements.editScheduleHint, T('edit.validate_request_failed'), 'error');
        elements.cronPreview.hidden = true;
    }
}

async function validateScriptRealtime() {
    const script = elements.editScript.value.trim();
    if (!script) {
        setHint(elements.editScriptHint, '', '');
        elements.editScript.classList.remove('valid', 'invalid');
        return;
    }
    
    try {
        const response = await fetch('/api/validate/script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script })
        });
        const data = await response.json();
        
        if (data.valid) {
            elements.editScript.classList.remove('valid', 'invalid');
            setHint(elements.editScriptHint, '', '');
        } else {
            elements.editScript.classList.remove('valid');
            elements.editScript.classList.add('invalid');
            setHint(elements.editScriptHint, `✗ ${data.error}`, 'error');
        }
    } catch (error) {
        setHint(elements.editScriptHint, T('edit.validate_request_failed'), 'error');
    }
}

function validateNameRealtime() {
    const name = elements.editName.value.trim();
    if (!name) {
        setHint(elements.editNameHint, '', '');
        elements.editName.classList.remove('valid', 'invalid');
        return;
    }
    
    // 唯一性校验：与 originalName 不区分大小写比较
    const isOwnName = name.toLowerCase() === editState.originalName.toLowerCase();
    const duplicate = editState.allTaskNames.some(
        n => n.toLowerCase() === name.toLowerCase() && n.toLowerCase() !== editState.originalName.toLowerCase()
    );
    
    if (duplicate && !isOwnName) {
        elements.editName.classList.remove('valid');
        elements.editName.classList.add('invalid');
        setHint(elements.editNameHint, T('edit.name_taken'), 'error');
    } else {
        elements.editName.classList.remove('invalid');
        elements.editName.classList.add('valid');
        setHint(elements.editNameHint, T('edit.name_ok'), 'success');
    }
}

function collectFormData() {
    const envRows = elements.envList.querySelectorAll('.env-row');
    const env = [];
    envRows.forEach(row => {
        const key = row.querySelector('.env-key').value.trim();
        const value = row.querySelector('.env-value').value;
        if (key) {
            env.push({ key, value });
        }
    });
    
    return {
        name: elements.editName.value.trim(),
        description: elements.editDescription.value.trim(),
        schedule: elements.editSchedule.value.trim(),
        script: elements.editScript.value.trim(),
        enabled: editState.enabled,
        env
    };
}

async function saveTaskEdit() {
    if (editState.isSaving) return;
    
    const data = collectFormData();
    
    // 客户端预校验（服务端也会再校验一次）
    const clientErrors = [];
    if (!data.name) clientErrors.push(T('edit.err_name'));
    if (!data.schedule) clientErrors.push(T('edit.err_schedule'));
    if (!data.script) clientErrors.push(T('edit.err_script'));
    
    // 重复键校验
    const seenKeys = new Set();
    for (const item of data.env) {
        if (seenKeys.has(item.key)) {
            clientErrors.push(T('edit.err_dup_env', { key: item.key }));
        }
        seenKeys.add(item.key);
    }
    
    if (clientErrors.length > 0) {
        showToast(clientErrors.join(T('common.error_sep')), 'error');
        return;
    }
    
    editState.isSaving = true;
    const originalContent = elements.editSave.innerHTML;
    elements.editSave.disabled = true;
    elements.editSave.innerHTML = `<i data-lucide="loader-2" class="btn-icon"></i> ${T('edit.saving')}`;
    
    try {
        const response = await fetch(`/api/tasks/${encodeURIComponent(editState.originalName)}/edit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        
        if (result.success) {
            const reloadNote = result.reloaded
                ? T('edit.reloaded_note')
                : T('edit.reload_failed_note', { message: result.reload_message || '' });
            showToast(`${result.message}${reloadNote}`, result.reloaded ? 'success' : 'warning', 4000);
            closeModal('edit');
            loadTasks();
        } else {
            showToast(result.message || T('edit.save_failed'), 'error', 5000);
        }
    } catch (error) {
        console.error('保存任务失败:', error);
        showToast(T('edit.save_request_failed'), 'error');
    } finally {
        editState.isSaving = false;
        elements.editSave.disabled = false;
        elements.editSave.innerHTML = originalContent;
    }
}

document.addEventListener('DOMContentLoaded', init);