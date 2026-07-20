/**
 * LiteCron Web UI - 前端交互逻辑
 */

const state = {
    tasks: [],
    logs: [],
    containerStatus: null,
    isRunning: false
};

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
    currentFilename: document.getElementById('current-filename'),
    btnDownload: document.getElementById('btn-download'),
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
    editEnabled: document.getElementById('edit-enabled'),
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
    isSaving: false,
    cronTimer: null,        // cron 实时校验防抖
    scriptTimer: null       // script 实时校验防抖
};

function init() {
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
            title: '确认全部启用',
            message: '确定要启用所有定时任务吗？',
            onConfirm: () => batchToggleTasks(true)
        });
    });
    
    elements.btnDisableAll.addEventListener('click', () => {
        showConfirm({
            title: '确认全部禁用',
            message: '确定要禁用所有定时任务吗？此操作将暂停所有定时任务的执行。',
            onConfirm: () => batchToggleTasks(false)
        });
    });
    elements.btnClean.addEventListener('click', () => {
        showConfirm({
            title: '确认清理日志',
            message: '确定要清理超过 7 天的日志文件吗？此操作无法撤销。',
            onConfirm: cleanLogs
        });
    });
    
    elements.btnMaximize.addEventListener('click', toggleMaximize);
    
    elements.modalClose.addEventListener('click', () => closeModal('logs'));
    elements.runModalClose.addEventListener('click', () => closeModal('run'));
    elements.editModalClose.addEventListener('click', () => closeModal('edit'));
    elements.editCancel.addEventListener('click', () => closeModal('edit'));
    
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            const modal = e.target.closest('.modal');
            if (modal) {
                const modalType = modal.id.replace('-modal', '');
                closeModal(modalType);
            }
        });
    });
    
    elements.btnDownload.addEventListener('click', downloadLog);
    
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
                    showToast(reloadData.message || '配置重载失败', 'warning');
                }
            } catch (reloadError) {
                console.error('重载配置失败:', reloadError);
                showToast('重载配置失败', 'error');
            }
        }
        await loadTasks();
    } catch (error) {
        console.error('加载数据失败:', error);
        showToast('加载数据失败', 'error');
    }
}

async function loadTasks() {
    try {
        elements.taskList.innerHTML = `
            <tr class="loading-row">
                <td colspan="6" class="loading-cell">
                    <div class="spinner"></div>
                    <span>加载中...</span>
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
        elements.enabledCount.textContent = `${enabledCount} 个启用`;
        
        if (state.tasks.length === 0 && data.config_exists === false) {
            elements.taskList.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-state">
                        <i data-lucide="list-checks" class="empty-icon"></i>
                        <div class="empty-text">未找到 config.yml 配置文件</div>
                        <div class="empty-subtext">请创建 config.yml 文件并重新加载</div>
                    </td>
                </tr>
            `;
            return;
        }
        
        renderTasks();
        lucide.createIcons();

    } catch (error) {
        console.error('加载任务失败:', error);
        elements.taskList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <i data-lucide="alert-triangle" class="empty-icon"></i>
                    <div class="empty-text">加载任务失败: ${error.message}</div>
                    <div class="empty-subtext">
                        <button onclick="loadTasks()" class="btn btn-secondary" style="margin-top: 12px;">
                            <i data-lucide="refresh-cw" class="btn-icon"></i> 重试
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }
}

function renderTasks() {
    const mobileTaskList = document.getElementById('mobile-task-list');
    
    if (state.tasks.length === 0) {
        elements.taskList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <i data-lucide="list-checks" class="empty-icon"></i>
                    <div class="empty-text">暂无配置的任务</div>
                    <div class="empty-subtext">在 config.yml 中添加任务配置</div>
                </td>
            </tr>
        `;
        
        if (mobileTaskList) {
            mobileTaskList.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="list-checks" class="empty-icon"></i>
                    <div class="empty-text">暂无配置的任务</div>
                    <div class="empty-subtext">在 config.yml 中添加任务配置</div>
                </div>
            `;
        }
        return;
    }
    
    elements.taskList.innerHTML = state.tasks.map(task => `
        <tr data-task-name="${task.name}" class="task-row">
            <td>
                <span class="task-status ${task.enabled ? 'enabled' : 'disabled'}">
                    <span class="status-dot"></span>
                    ${task.enabled ? '启用' : '禁用'}
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
                            title="立即执行">
                        <i data-lucide="play" class="btn-action-icon"></i> 执行
                    </button>
                    <button class="btn-action btn-toggle ${task.enabled ? 'disable' : 'enable'}"
                            onclick="toggleTask('${task.name}', ${!task.enabled})"
                            title="${task.enabled ? '禁用' : '启用'}">
                        ${task.enabled ? '<i data-lucide="pause" class="btn-action-icon"></i> 禁用' : '<i data-lucide="play" class="btn-action-icon"></i> 启用'}
                    </button>
                    <button class="btn-action btn-edit"
                            onclick="editTask('${task.name}')"
                            title="编辑任务">
                        <i data-lucide="pencil" class="btn-action-icon"></i> 编辑
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
    
    if (mobileTaskList) {
        mobileTaskList.innerHTML = state.tasks.map(task => `
            <div class="mobile-task-card" data-task-name="${task.name}">
                <div class="mobile-task-header">
                    <span class="mobile-task-name">${task.name}</span>
                    <span class="mobile-task-status ${task.enabled ? 'enabled' : 'disabled'}">
                        <span class="mobile-task-status-dot"></span>
                        ${task.enabled ? '启用' : '禁用'}
                    </span>
                </div>
                <div class="mobile-task-info">
                    <div class="mobile-task-info-item">
                        <span class="mobile-task-info-label">调度</span>
                        <span class="mobile-task-info-value mono">${task.schedule}</span>
                    </div>
                    <div class="mobile-task-info-item">
                        <span class="mobile-task-info-label">描述</span>
                        <span class="mobile-task-info-value">${task.description || '-'}</span>
                    </div>
                    <div class="mobile-task-info-item">
                        <span class="mobile-task-info-label">下次</span>
                        <span class="mobile-task-info-value">${task.next_run || '-'}</span>
                    </div>
                </div>
                <div class="mobile-task-actions">
                    <button class="btn-action btn-run"
                            onclick="runTask('${task.name}')"
                            ${!task.enabled ? 'disabled' : ''}
                            title="立即执行">
                        <i data-lucide="play" class="btn-action-icon"></i> 执行
                    </button>
                    <button class="btn-action btn-toggle ${task.enabled ? 'disable' : 'enable'}"
                            onclick="toggleTask('${task.name}', ${!task.enabled})"
                            title="${task.enabled ? '禁用' : '启用'}">
                        ${task.enabled ? '<i data-lucide="pause" class="btn-action-icon"></i> 禁用' : '<i data-lucide="play" class="btn-action-icon"></i> 启用'}
                    </button>
                    <button class="btn-action btn-edit"
                            onclick="editTask('${task.name}')"
                            title="编辑任务">
                        <i data-lucide="pencil" class="btn-action-icon"></i> 编辑
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
    elements.runStatus.textContent = '准备执行...';
    elements.terminal.innerHTML = '<div class="terminal-line system">等待开始...</div>';
    
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
        appendTerminal(elements.terminal, `执行出错: ${error.message}`, 'error');
        showToast('执行失败', 'error');
    } finally {
        state.isRunning = false;
    }
}

function handleRunOutput(data) {
    if (data.status === 'started') {
        elements.terminal.innerHTML = '';
        appendTerminal(elements.terminal, data.message, 'system');
        elements.runStatus.textContent = '执行中...';
    } else if (data.status === 'running') {
        appendTerminal(elements.terminal, data.output);
        elements.terminal.scrollTop = elements.terminal.scrollHeight;
    } else if (data.status === 'completed') {
        const type = data.success ? 'success' : 'error';
        appendTerminal(elements.terminal, data.message, type);
        elements.runStatus.textContent = data.success ? '执行完成' : '执行失败';
        
        if (data.success) {
            showToast('任务执行成功', 'success');
        } else {
            showToast('任务执行失败', 'error');
        }
    } else if (data.status === 'error') {
        appendTerminal(elements.terminal, data.message, 'error');
        elements.runStatus.textContent = '执行出错';
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
            showToast(data.message || '操作失败', 'error');
        }
        
    } catch (error) {
        console.error('切换任务失败:', error);
        showToast('操作失败', 'error');
    }
}

async function batchToggleTasks(enabled) {
    try {
        const btn = enabled ? elements.btnEnableAll : elements.btnDisableAll;
        btn.disabled = true;
        btn.innerHTML = '<i data-lucide="loader-2" class="btn-icon"></i> 处理中...';
        
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
            showToast(data.message || '操作失败', 'error');
        }
        
    } catch (error) {
        console.error('批量操作失败:', error);
        showToast('操作失败', 'error');
    } finally {
        const btn = enabled ? elements.btnEnableAll : elements.btnDisableAll;
        btn.disabled = false;
        btn.innerHTML = enabled 
            ? '<i data-lucide="play" class="btn-icon"></i> 全部启用'
            : '<i data-lucide="pause" class="btn-icon"></i> 全部禁用';
        lucide.createIcons({ root: btn });
    }
}

async function loadLogs() {
    elements.fileList.innerHTML = '<li class="file-item loading">加载中...</li>';
    elements.logsViewer.innerHTML = '<code>点击左侧文件查看内容</code>';
    elements.currentFilename.textContent = '选择一个日志文件';
    elements.btnDownload.disabled = true;
    
    try {
        const response = await fetch('/api/logs');
        const data = await response.json();
        
        state.logs = data.logs || [];
        state.logs.sort((a, b) => b.modified.localeCompare(a.modified));

        if (state.logs.length === 0) {
            elements.fileList.innerHTML = '<li class="file-item">暂无日志文件</li>';
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
        elements.fileList.innerHTML = '<li class="file-item">加载失败</li>';
    }
}

async function viewLog(filename, index) {
    document.querySelectorAll('.file-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
    });
    
    elements.currentFilename.textContent = filename;
    elements.logsViewer.innerHTML = '<code>加载中...</code>';
    elements.btnDownload.disabled = false;
    elements.btnDownload.dataset.filename = filename;
    
    try {
        const response = await fetch(`/api/logs/${encodeURIComponent(filename)}?limit=1000`);
        const data = await response.json();
        
        if (data.error) {
            elements.logsViewer.innerHTML = `<code class="error">${data.error}</code>`;
        } else {
            const escaped = escapeHtml(data.content);
            elements.logsViewer.innerHTML = `<code>${escaped}</code>`;
            elements.logsViewer.scrollTop = elements.logsViewer.scrollHeight;
        }
        
    } catch (error) {
        console.error('加载日志失败:', error);
        elements.logsViewer.innerHTML = '<code class="error">加载失败</code>';
    }
}

function downloadLog() {
    const filename = elements.btnDownload.dataset.filename;
    if (!filename) return;
    
    fetch(`/api/logs/${encodeURIComponent(filename)}`)
        .then(response => response.json())
        .then(data => {
            if (data.content) {
                const blob = new Blob([data.content], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        });
}

async function cleanLogs() {
    try {
        elements.btnClean.disabled = true;
        elements.btnClean.innerHTML = '<i data-lucide="loader-2" class="btn-icon"></i> 清理中...';
        
        const response = await fetch('/api/clean', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showToast('日志清理完成', 'success');
            closeModal('confirm');
            loadLogs();
        } else {
            showToast(data.message || '清理失败', 'error');
        }
        
    } catch (error) {
        console.error('清理失败:', error);
        showToast('清理请求失败', 'error');
    } finally {
        elements.btnClean.disabled = false;
        elements.btnClean.innerHTML = '<i data-lucide="trash-2" class="btn-icon"></i> 清理日志';
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

function toggleMaximize() {
    const modalContent = elements.logsModal.querySelector('.modal-content');
    const isMaximized = modalContent.classList.toggle('maximized');
    
    const btnIcon = elements.btnMaximize.querySelector('.btn-icon');
    if (isMaximized) {
        btnIcon.setAttribute('data-lucide', 'minimize-2');
        elements.btnMaximize.title = '还原';
    } else {
        btnIcon.setAttribute('data-lucide', 'maximize-2');
        elements.btnMaximize.title = '最大化';
    }
    lucide.createIcons({ root: elements.btnMaximize });
}

let confirmCallback = null;

function showConfirm(options) {
    const { title, message, onConfirm } = options;
    
    elements.confirmTitle.textContent = title || '确认操作';
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
    setHint(elements.editNameHint, '加载中...', 'info');
    elements.editSave.disabled = true;
    elements.editSave.innerHTML = '<i data-lucide="loader-2" class="btn-icon"></i> 加载中...';
    
    try {
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskName)}/detail`);
        const data = await response.json();
        
        if (!data.success || !data.task) {
            showToast(data.message || '加载任务失败', 'error');
            closeModal('edit');
            return;
        }
        
        const task = data.task;
        editState.originalName = task.original_name || taskName;
        editState.allTaskNames = task.all_task_names || [];
        editState.envAliasKeys = new Set(
            (task.env || []).filter(e => e.is_alias).map(e => e.key)
        );
        
        elements.editName.value = task.name;
        elements.editDescription.value = task.description;
        elements.editSchedule.value = task.schedule;
        elements.editScript.value = task.script;
        elements.editEnabled.checked = task.enabled;
        
        // 渲染 env 列表
        elements.envList.innerHTML = '';
        if (task.env && task.env.length > 0) {
            task.env.forEach(e => addEnvRow(e.key, e.value, e.is_alias, e.alias_target));
        } else {
            addEnvRow();
        }
        
        setHint(elements.editNameHint, '', '');
        elements.editSave.disabled = false;
        elements.editSave.innerHTML = '<i data-lucide="save" class="btn-icon"></i> 保存并重载';
        
        // 触发实时校验预览
        validateCronRealtime();
        validateScriptRealtime();
    } catch (error) {
        console.error('加载任务详情失败:', error);
        showToast('加载任务详情失败', 'error');
        closeModal('edit');
    }
}

function resetEditForm() {
    elements.editForm.reset();
    elements.envList.innerHTML = '';
    editState.originalName = '';
    editState.allTaskNames = [];
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
        valueInput.title = `共享变量（引用锚点 ${aliasTarget}），值在多处共享，不可直接编辑`;
        const badge = document.createElement('span');
        badge.className = 'env-alias-badge';
        badge.innerHTML = `<i data-lucide="link" style="width: 12px; height: 12px; margin-right: 2px;"></i> ${aliasTarget}`;
        badge.title = '此值通过 YAML 锚点引用共享，编辑会改为字面量';
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
        setHint(elements.editScheduleHint, '校验请求失败', 'error');
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
        setHint(elements.editScriptHint, '校验请求失败', 'error');
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
        setHint(elements.editNameHint, '✗ 名称已被其他任务占用', 'error');
    } else {
        elements.editName.classList.remove('invalid');
        elements.editName.classList.add('valid');
        setHint(elements.editNameHint, '✓ 名称可用', 'success');
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
        enabled: elements.editEnabled.checked,
        env
    };
}

async function saveTaskEdit() {
    if (editState.isSaving) return;
    
    const data = collectFormData();
    
    // 客户端预校验（服务端也会再校验一次）
    const clientErrors = [];
    if (!data.name) clientErrors.push('任务名称不能为空');
    if (!data.schedule) clientErrors.push('调度规则不能为空');
    if (!data.script) clientErrors.push('脚本路径不能为空');
    
    // 重复键校验
    const seenKeys = new Set();
    for (const item of data.env) {
        if (seenKeys.has(item.key)) {
            clientErrors.push(`环境变量键名重复: ${item.key}`);
        }
        seenKeys.add(item.key);
    }
    
    if (clientErrors.length > 0) {
        showToast(clientErrors.join('；'), 'error');
        return;
    }
    
    editState.isSaving = true;
    const originalContent = elements.editSave.innerHTML;
    elements.editSave.disabled = true;
    elements.editSave.innerHTML = '<i data-lucide="loader-2" class="btn-icon"></i> 保存中...';
    
    try {
        const response = await fetch(`/api/tasks/${encodeURIComponent(editState.originalName)}/edit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        
        if (result.success) {
            const reloadNote = result.reloaded
                ? '，配置已重载生效'
                : `（重载失败: ${result.reload_message || ''}）`;
            showToast(`${result.message}${reloadNote}`, result.reloaded ? 'success' : 'warning', 4000);
            closeModal('edit');
            loadTasks();
        } else {
            showToast(result.message || '保存失败', 'error', 5000);
        }
    } catch (error) {
        console.error('保存任务失败:', error);
        showToast('保存请求失败', 'error');
    } finally {
        editState.isSaving = false;
        elements.editSave.disabled = false;
        elements.editSave.innerHTML = originalContent;
    }
}

document.addEventListener('DOMContentLoaded', init);