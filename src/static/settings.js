/**
 * LiteCron Web UI - 设置弹窗交互逻辑
 * 与首页 app.js 共用同一页面：偏好开关、toast、401 拦截由 app.js 统一处理，
 * 本文件用 IIFE 隔离变量，仅暴露 loadSettingsModal 供打开弹窗时加载配置。
 */
(function () {
    const $ = (id) => document.getElementById(id);

    const elements = {
        proxy: $('proxy'),
        proxyRefs: $('proxy-refs'),
        form: $('settings-form'),
        btnSave: $('btn-save-settings'),
        btnReload: $('btn-reload-settings')
    };

    // 表单字段 <-> notify 配置路径
    const FIELD_MAP = [
        ['webhook.url', 'webhook-url'],
        ['webhook.method', 'webhook-method'],
        ['webhook.content_type', 'webhook-content-type'],
        ['webhook.headers', 'webhook-headers'],
        ['ntfy.url', 'ntfy-url'],
        ['ntfy.topic', 'ntfy-topic'],
        ['ntfy.priority', 'ntfy-priority'],
        ['ntfy.token', 'ntfy-token'],
        ['ntfy.username', 'ntfy-username'],
        ['ntfy.password', 'ntfy-password'],
        ['ntfy.actions', 'ntfy-actions'],
        ['ntfy.headers', 'ntfy-headers']
    ];

    const WEBHOOK_METHODS = ['GET', 'POST', 'PUT', 'PATCH'];
    const WEBHOOK_CONTENT_TYPES = [
        'application/json',
        'application/x-www-form-urlencoded',
        'text/plain',
        'text/markdown'
    ];

    let currentSettings = null;

    function setFieldValue(id, value) {
        const field = $(id);
        if (!field) return;
        const text = value === null || value === undefined ? '' : String(value);
        // 兼容配置中不在下拉选项内的历史值，避免保存时被静默清空
        if (field.tagName === 'SELECT' && text &&
            !Array.from(field.options).some(option => option.value === text)) {
            const option = document.createElement('option');
            option.value = text;
            option.textContent = text;
            field.appendChild(option);
        }
        field.value = text;
    }

    function updateProxyBadge(settings) {
        if (!settings.config_exists) {
            elements.proxyRefs.textContent = '未找到 config.yml';
            return;
        }
        elements.proxyRefs.textContent = settings.proxy_exists
            ? `${settings.proxy_refs} 处引用 · &${settings.proxy_anchor}`
            : '未定义锚点，保存后创建';
    }

    function fillForm(settings) {
        currentSettings = settings;
        const notify = settings.notify || {};
        elements.proxy.value = settings.proxy || '';
        $('notify-on-failure').checked = Boolean(notify.on_failure);
        $('notify-on-success').checked = Boolean(notify.on_success);

        for (const [path, id] of FIELD_MAP) {
            const [section, field] = path.split('.');
            setFieldValue(id, (notify[section] || {})[field]);
        }
        updateProxyBadge(settings);
    }

    function collectPayload() {
        const notify = {
            on_failure: $('notify-on-failure').checked,
            on_success: $('notify-on-success').checked,
            webhook: {},
            ntfy: {}
        };
        for (const [path, id] of FIELD_MAP) {
            const [section, field] = path.split('.');
            notify[section][field] = $(id).value;
        }
        return { proxy: elements.proxy.value.trim(), notify };
    }

    function validatePayload(payload) {
        const errors = [];
        const { webhook, ntfy } = payload.notify;
        for (const [label, url] of [['Webhook', webhook.url], ['NTFY', ntfy.url]]) {
            if (url.trim() && !/^https?:\/\//i.test(url.trim())) {
                errors.push(`${label} URL 必须以 http:// 或 https:// 开头`);
            }
        }
        if (!WEBHOOK_METHODS.includes(webhook.method)) errors.push('Webhook 请求方法无效');
        if (!WEBHOOK_CONTENT_TYPES.includes(webhook.content_type)) errors.push('Webhook Content-Type 无效');
        if (!['1', '2', '3', '4', '5'].includes(ntfy.priority)) errors.push('NTFY 优先级必须为 1-5');
        return errors;
    }

    async function loadSettings(notifySuccess = false) {
        try {
            const response = await fetch('/api/settings');
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || '读取设置失败');
            }
            fillForm(data.settings);
            elements.btnSave.disabled = !data.settings.config_exists;
            if (!data.settings.config_exists) {
                showToast('未找到 config.yml，无法读取或保存配置', 'warning', 5000);
            } else if (notifySuccess) {
                showToast('已重新读取配置', 'success');
            }
        } catch (error) {
            console.error('读取设置失败:', error);
            showToast(`读取设置失败: ${error.message}`, 'error', 5000);
        }
    }

    async function saveSettings() {
        if (!currentSettings || !currentSettings.config_exists) {
            showToast('未找到 config.yml，无法保存配置', 'error');
            return;
        }
        const payload = collectPayload();
        const errors = validatePayload(payload);
        if (errors.length > 0) {
            showToast(errors.join('；'), 'error', 5000);
            return;
        }

        const originalHtml = elements.btnSave.innerHTML;
        elements.btnSave.disabled = true;
        elements.btnSave.innerHTML = '<i data-lucide="loader-2" class="btn-icon"></i> 保存中...';
        if (window.lucide) lucide.createIcons({ root: elements.btnSave });

        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || '保存失败');
            }

            showToast(
                data.reloaded
                    ? '设置已保存，配置已重载'
                    : `设置已保存（重载失败: ${data.reload_message || '未知原因'}）`,
                data.reloaded ? 'success' : 'warning',
                4500
            );
            if (currentSettings && typeof data.proxy_refs === 'number') {
                currentSettings.proxy_refs = data.proxy_refs;
                currentSettings.proxy_exists = true;
                updateProxyBadge(currentSettings);
            }
        } catch (error) {
            console.error('保存设置失败:', error);
            showToast(`保存设置失败: ${error.message}`, 'error', 5000);
        } finally {
            elements.btnSave.disabled = false;
            elements.btnSave.innerHTML = originalHtml;
            if (window.lucide) lucide.createIcons({ root: elements.btnSave });
        }
    }

    // 首页点击「设置」按钮打开弹窗时调用
    window.loadSettingsModal = loadSettings;

    document.addEventListener('DOMContentLoaded', () => {
        elements.btnSave.addEventListener('click', saveSettings);
        elements.btnReload.addEventListener('click', () => loadSettings(true));
        elements.form.addEventListener('submit', (e) => {
            e.preventDefault();
            saveSettings();
        });
    });
})();
