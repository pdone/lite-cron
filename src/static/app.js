/**
 * LiteCron Web UI - 前端交互逻辑
 * 提供任务管理、日志查看、构建等功能
 */

// 全局状态
const state = {
    tasks: [],
    logs: [],
    containerStatus: null,
    isRunning: false
};

// DOM 元素
const elements = {
    taskList: document.getElementById('task-list'),
    taskCount: document.getElementById('task-count'),
    enabledCount: document.getElementById('enabled-count'),
    updateTime: document.getElementById('update-time'),
    
    // 按钮
    btnLogs: document.getElementById('btn-logs'),
    btnClean: document.getElementById('btn-clean'),
    btnRefresh: document.getElementById('btn-refresh'),
    
    // 模态框
    logsModal: document.getElementById('logs-modal'),
    runModal: document.getElementById('run-modal'),
    modalClose: document.getElementById('modal-close'),
    runModalClose: document.getElementById('run-modal-close'),
    
    // 日志模态框
    fileList: document.getElementById('file-list'),
    logsViewer: document.getElementById('logs-viewer'),
    currentFilename: document.getElementById('current-filename'),
    btnDownload: document.getElementById('btn-download'),
    
    // 执行模态框
    runTaskName: document.getElementById('run-task-name'),
    runStatus: document.getElementById('run-status'),
    terminal: document.getElementById('terminal'),
    
    // Toast
    toastContainer: document.getElementById('toast-container')
};

/**
 * 初始化应用
 */
function init() {
    bindEvents();
    loadData(false);
}

/**
 * 绑定事件
 */
function bindEvents() {
    // 工具栏按钮
    elements.btnRefresh.addEventListener('click', () => {
        elements.btnRefresh.classList.add('rotating');
        loadData(true);
        setTimeout(() => elements.btnRefresh.classList.remove('rotating'), 500);
    });
    
    elements.btnLogs.addEventListener('click', () => {
        loadLogs();
        openModal('logs');
    });
    elements.btnClean.addEventListener('click', cleanLogs);
    
    // 模态框关闭
    elements.modalClose.addEventListener('click', () => closeModal('logs'));
    elements.runModalClose.addEventListener('click', () => closeModal('run'));
    
    // 点击遮罩关闭
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            const modal = e.target.closest('.modal');
            if (modal) {
                const modalType = modal.id.replace('-modal', '');
                closeModal(modalType);
            }
        });
    });
    
    // 下载按钮
    elements.btnDownload.addEventListener('click', downloadLog);
    
    // ESC 键关闭模态框
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAllModals();
        }
    });
}

/**
 * 加载所有数据
 * @param {boolean} reload - 是否重载配置（默认 false）
 */
async function loadData(reload = false) {
    try {
        if (reload) {
            // 先重载配置和 cron 调度
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

        // 再刷新任务列表
        await loadTasks();
    } catch (error) {
        console.error('加载数据失败:', error);
        showToast('加载数据失败', 'error');
    }
}

/**
 * 加载任务列表
 */
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
        
        // 检查API是否返回错误
        if (data.error) {
            throw new Error(data.error);
        }
        
        state.tasks = data.tasks || [];
        
        // 更新任务统计
        const enabledCount = state.tasks.filter(t => t.enabled).length;
        elements.taskCount.textContent = state.tasks.length || 0;
        elements.enabledCount.textContent = `${enabledCount} 个启用`;
        
        // 如果任务列表为空且配置不存在，显示提示
        if (state.tasks.length === 0 && data.config_exists === false) {
            elements.taskList.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-state">
                        <div class="empty-icon">📋</div>
                        <div class="empty-text">未找到 config.yml 配置文件</div>
                        <div style="margin-top: 12px; color: var(--text-muted); font-size: 0.875rem;">
                            请创建 config.yml 文件并重新加载
                        </div>
                    </td>
                </tr>
            `;
            // 更新时间
            elements.updateTime.textContent = new Date().toLocaleString();
            return;
        }
        
        renderTasks();
        
        // 更新时间
        elements.updateTime.textContent = new Date().toLocaleString();
        
    } catch (error) {
        console.error('加载任务失败:', error);
        elements.taskList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <div class="empty-icon">⚠️</div>
                    <div class="empty-text">加载任务失败: ${error.message}</div>
                    <div style="margin-top: 12px; color: var(--text-muted); font-size: 0.875rem;">
                        <button onclick="loadTasks()" class="btn btn-secondary" style="margin-top: 8px;">
                            <span class="btn-icon">🔄</span> 重试
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }
}

/**
 * 渲染任务列表
 */
function renderTasks() {
    if (state.tasks.length === 0) {
        elements.taskList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <div class="empty-icon">📋</div>
                    <div class="empty-text">暂无配置的任务</div>
                </td>
            </tr>
        `;
        return;
    }
    
    elements.taskList.innerHTML = state.tasks.map(task => `
        <tr data-task-name="${task.name}">
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
                        ▶️ 执行
                    </button>
                    <button class="btn-action btn-toggle" 
                            onclick="toggleTask('${task.name}', ${!task.enabled})"
                            title="${task.enabled ? '禁用' : '启用'}">
                        ${task.enabled ? '⏸️' : '☑️'}
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

/**
 * 执行任务
 */
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

/**
 * 处理执行输出
 */
function handleRunOutput(data) {
    if (data.status === 'started') {
        elements.terminal.innerHTML = '';
        appendTerminal(elements.terminal, data.message, 'system');
        elements.runStatus.textContent = '执行中...';
    } else if (data.status === 'running') {
        appendTerminal(elements.terminal, data.output);
        // 自动滚动到底部
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

/**
 * 添加终端输出行
 */
function appendTerminal(terminal, text, type = '') {
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    line.textContent = text;
    terminal.appendChild(line);
}

/**
 * 切换任务状态
 */
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
            loadTasks(); // 刷新任务列表
        } else {
            showToast(data.message || '操作失败', 'error');
        }
        
    } catch (error) {
        console.error('切换任务失败:', error);
        showToast('操作失败', 'error');
    }
}

/**
 * 加载日志列表
 */
async function loadLogs() {
    elements.fileList.innerHTML = '<li class="file-item loading">加载中...</li>';
    elements.logsViewer.innerHTML = '<code>点击左侧文件查看内容</code>';
    elements.currentFilename.textContent = '选择一个日志文件';
    elements.btnDownload.disabled = true;
    
    try {
        const response = await fetch('/api/logs');
        const data = await response.json();
        
        state.logs = data.logs || [];

        // 按日期降序排序（文件名格式: YYYYMMDD.log）
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
        
        // 自动查看最新的日志
        if (state.logs.length > 0) {
            viewLog(state.logs[0].name, 0);
        }
        
    } catch (error) {
        console.error('加载日志失败:', error);
        elements.fileList.innerHTML = '<li class="file-item">加载失败</li>';
    }
}

/**
 * 查看日志内容
 */
async function viewLog(filename, index) {
    // 更新选中状态
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
            // 转义 HTML 并高亮
            const escaped = escapeHtml(data.content);
            elements.logsViewer.innerHTML = `<code>${escaped}</code>`;
            
            // 滚动到底部
            elements.logsViewer.scrollTop = elements.logsViewer.scrollHeight;
        }
        
    } catch (error) {
        console.error('加载日志失败:', error);
        elements.logsViewer.innerHTML = '<code class="error">加载失败</code>';
    }
}

/**
 * 下载日志
 */
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

/**
 * 清理日志
 */
async function cleanLogs() {
    if (!confirm('确定要清理超过 7 天的日志文件吗？')) {
        return;
    }
    
    try {
        elements.btnClean.disabled = true;
        elements.btnClean.innerHTML = '<span class="btn-icon">⏳</span> 清理中...';
        
        const response = await fetch('/api/clean', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showToast('日志清理完成', 'success');
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

/**
 * 打开模态框
 */
function openModal(type) {
    const modal = document.getElementById(`${type}-modal`);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

/**
 * 关闭模态框
 */
function closeModal(type) {
    const modal = document.getElementById(`${type}-modal`);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

/**
 * 关闭所有模态框
 */
function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('active');
    });
    document.body.style.overflow = '';
}

/**
 * 显示 Toast 通知
 */
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
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    
    elements.toastContainer.appendChild(toast);
    
    // 自动关闭
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = 'toastOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }
    }, duration);
}

/**
 * 转义 HTML 特殊字符
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 启动应用
document.addEventListener('DOMContentLoaded', init);
