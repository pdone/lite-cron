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
    btnMaximize: document.getElementById('btn-maximize'),
    logsModal: document.getElementById('logs-modal'),
    runModal: document.getElementById('run-modal'),
    confirmModal: document.getElementById('confirm-modal'),
    modalClose: document.getElementById('modal-close'),
    runModalClose: document.getElementById('run-modal-close'),
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
    confirmCancel: document.getElementById('confirm-cancel')
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
        loadLogs();
        openModal('logs');
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
                        <div class="empty-icon">📋</div>
                        <div class="empty-text">未找到 config.yml 配置文件</div>
                        <div class="empty-subtext">请创建 config.yml 文件并重新加载</div>
                    </td>
                </tr>
            `;
            return;
        }
        
        renderTasks();

    } catch (error) {
        console.error('加载任务失败:', error);
        elements.taskList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <div class="empty-icon">⚠️</div>
                    <div class="empty-text">加载任务失败: ${error.message}</div>
                    <div class="empty-subtext">
                        <button onclick="loadTasks()" class="btn btn-secondary" style="margin-top: 12px;">
                            <span class="btn-icon">🔄</span> 重试
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
                    <div class="empty-icon">📋</div>
                    <div class="empty-text">暂无配置的任务</div>
                    <div class="empty-subtext">在 config.yml 中添加任务配置</div>
                </td>
            </tr>
        `;
        
        if (mobileTaskList) {
            mobileTaskList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📋</div>
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
                <div class="schedule-info">
                    <span class="schedule-expr">${task.schedule}</span>
                    ${task.schedule_desc && task.schedule_desc !== task.schedule ? 
                        `<span class="schedule-desc">${task.schedule_desc}</span>` : ''}
                </div>
            </td>
            <td>
                <span class="task-desc" title="${task.description || ''}">
                    ${task.description || '-'}
                </span>
            </td>
            <td>
                ${task.next_run ? 
                    `<span class="next-run">
                        <span class="next-run-icon">⏰</span>
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
                        ▶ 执行
                    </button>
                    <button class="btn-action btn-toggle ${task.enabled ? 'disable' : 'enable'}"
                            onclick="toggleTask('${task.name}', ${!task.enabled})"
                            title="${task.enabled ? '禁用' : '启用'}">
                        ${task.enabled ? '⏸ 禁用' : '▶ 启用'}
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
                    ${task.schedule_desc && task.schedule_desc !== task.schedule ? `
                        <div class="mobile-task-info-item">
                            <span class="mobile-task-info-label">说明</span>
                            <span class="mobile-task-info-value">${task.schedule_desc}</span>
                        </div>
                    ` : ''}
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
                        ▶ 执行
                    </button>
                    <button class="btn-action btn-toggle ${task.enabled ? 'disable' : 'enable'}"
                            onclick="toggleTask('${task.name}', ${!task.enabled})"
                            title="${task.enabled ? '禁用' : '启用'}">
                        ${task.enabled ? '⏸ 禁用' : '▶ 启用'}
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
        elements.btnClean.innerHTML = '<span class="btn-icon">⏳</span> 清理中...';
        
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
        elements.btnClean.innerHTML = '<span class="btn-icon">🧹</span> 清理日志';
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
        btnIcon.textContent = '⛶';
        elements.btnMaximize.title = '还原';
    } else {
        btnIcon.textContent = '⛶';
        elements.btnMaximize.title = '最大化';
    }
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
    if (confirmCallback) {
        confirmCallback();
        confirmCallback = null;
    } else {
        closeModal('confirm');
    }
});

function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="removeToast(this.parentElement)">&times;</button>
    `;
    
    elements.toastContainer.appendChild(toast);
    
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

document.addEventListener('DOMContentLoaded', init);