#!/usr/bin/env python3
"""
LiteCron Web 管理界面
基于 Flask 实现
提供任务管理、日志查看等功能
"""

import os
import sys
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    Response,
    send_from_directory,
    session,
    redirect,
    stream_with_context,
)

# 导入日志模块
from logger import log_info, log_success, log_error, log_warning

# 界面语言：t()/resolve_language()/install() 等，详见 i18n.py
import i18n

# 项目路径配置 - 文件位于 /app/ 下
PROJECT_ROOT = Path(__file__).parent.absolute()

# 动态检测任务脚本目录 - 优先使用 PROJECT_ROOT/tasks，不存在则使用父目录
TASKS_DIR = PROJECT_ROOT / "tasks"
if not TASKS_DIR.exists():
    TASKS_DIR = PROJECT_ROOT.parent / "tasks"

CONFIG_FILE = PROJECT_ROOT / "config.yml"
if not CONFIG_FILE.exists():
    CONFIG_FILE = PROJECT_ROOT.parent / "config.yml"
LOGS_DIR = PROJECT_ROOT / "logs"
TEMPLATE_DIR = PROJECT_ROOT / "template"
STATIC_DIR = PROJECT_ROOT / "static"
VERSION_FILE = PROJECT_ROOT / "VERSION"


def get_app_version() -> str:
    """从 VERSION 文件读取应用版本号"""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"


APP_VERSION = get_app_version()

app = Flask(__name__)
app.template_folder = str(TEMPLATE_DIR)

# 界面语言：注册 Jinja 全局 _() 与语言上下文（lang / lang_mode / i18n_catalog）
i18n.install(app)


@app.before_request
def resolve_ui_language():
    """解析界面语言，必须早于鉴权拦截注册：401 的提示语也要用请求语言。"""
    i18n.init_request_language()

# 鉴权配置（在 __main__ 启动时根据环境变量/config.yml 覆盖）
# AUTH_TOKEN 为空表示鉴权关闭（此时应仅绑定 127.0.0.1 本地访问）
AUTH_TOKEN: Optional[str] = None
WEBUI_HOST: str = "127.0.0.1"
# Session 有效期（天），默认 7；登录后浏览器 Cookie 保留指定天数
SESSION_DAYS: int = 7


def load_config() -> Optional[Dict[str, Any]]:
    """加载 YAML 配置文件"""
    try:
        import yaml

        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return None
    except Exception as e:
        log_error(f"加载配置失败: {e}")
        return None


def save_config(config: Dict[str, Any]) -> bool:
    """保存 YAML 配置文件，保留原始格式和注释"""
    try:
        from ruamel.yaml import YAML
        ry = YAML()
        ry.preserve_quotes = True

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            doc = ry.load(f)

        _deep_merge(doc, config)

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            ry.dump(doc, f)

        return True
    except Exception as e:
        log_error(f"保存配置失败: {e}")
        return False


def _deep_merge(base, update):
    """深度合并 update 到 base，保留 base 的 ruamel 格式对象"""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        elif key in base and isinstance(base[key], list) and isinstance(value, list):
            for i, item in enumerate(value):
                if i < len(base[key]):
                    if isinstance(base[key][i], dict) and isinstance(item, dict):
                        _deep_merge(base[key][i], item)
                    else:
                        base[key][i] = item
                else:
                    base[key].append(item)
        else:
            base[key] = value


def toggle_task_enabled(task_name: str) -> Optional[bool]:
    """切换任务启用状态，直接操作 ruamel doc 仅修改 enabled 字段。

    绕过 load_config + save_config 链路：safe_load 会把 YAML 别名（如 *proxy）
    展开为字面量，再经 _deep_merge 回灌会覆盖 ruamel doc 中的别名节点，导致
    顶部 proxy 锚点引用丢失。本函数仅改 enabled 字段后原样 dump，完整保留
    锚点、别名与注释。

    Returns:
        新的 enabled 状态；任务未找到或保存失败时返回 None
    """
    try:
        from ruamel.yaml import YAML

        ry = YAML()
        ry.preserve_quotes = True

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            doc = ry.load(f)

        if not doc or "tasks" not in doc:
            log_warning(f"切换任务状态失败: 配置未找到或无 tasks 段")
            return None

        found = False
        new_status = None
        for task in doc["tasks"]:
            name = task.get("name", "")
            if isinstance(name, str) and name.lower() == task_name.lower():
                current = bool(task.get("enabled", True))
                task["enabled"] = not current
                new_status = not current
                found = True
                break

        if not found:
            log_warning(f"切换任务状态失败: 任务 {task_name} 未找到")
            return None

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            ry.dump(doc, f)

        log_success(f"[WebUI] 任务 {task_name} 已{'启用' if new_status else '禁用'}")
        return new_status
    except Exception as e:
        log_error(f"切换任务状态失败: {e}")
        return None


# ============== 设置页：共享代理锚点与通知配置 ==============

# 通知配置中允许由设置页更新的字段（config.yml 的 notify 段）
NOTIFY_FIELDS = {
    "webhook": ("url", "method", "content_type", "body", "headers"),
    "ntfy": (
        "url", "topic", "priority", "token", "username", "password",
        "actions", "headers",
    ),
}
# 这些字段需保持 YAML 块标量（|）样式，避免多行文本被转义成单行
NOTIFY_BLOCK_FIELDS = {"headers"}
WEBHOOK_METHODS = ("GET", "POST", "PUT", "PATCH")
WEBHOOK_CONTENT_TYPES = (
    "application/json",
    "application/x-www-form-urlencoded",
    "text/plain",
    "text/markdown",
)


def _default_notify_settings() -> Dict[str, Any]:
    """设置页表单的默认值（与 notify.py 的默认值保持一致）"""
    return {
        "on_failure": True,
        "on_success": False,
        "webhook": {
            "url": "",
            "method": "POST",
            "content_type": "application/json",
            "body": "",
            "headers": "",
        },
        "ntfy": {
            "url": "",
            "topic": "",
            "priority": "3",
            "token": "",
            "username": "",
            "password": "",
            "actions": "",
            "headers": "",
        },
    }


def _ruamel_yaml():
    """创建保留引号/注释/锚点的 YAML 解析器"""
    from ruamel.yaml import YAML

    ry = YAML()
    ry.preserve_quotes = True
    return ry


def _find_shared_proxy(doc):
    """定位共享代理锚点，返回 (顶层键名, 锚点节点, 锚点名)

    优先使用顶层 `proxy: &proxy ...`；也兼容自定义锚点名或自定义顶层键名。
    若 proxy 键存在但没有锚点，返回锚点名为 None（保存时升级为锚点定义）。
    """
    if not doc:
        return None, None, None

    fallback = None
    for key, val in doc.items():
        if key in ("tasks", "notify", "webui", "global_env"):
            continue
        if not isinstance(val, str):
            continue
        anchor = getattr(val, "anchor", None)
        name = getattr(anchor, "value", None)
        if not name:
            continue
        if str(key) == "proxy":
            return str(key), val, name
        if fallback is None:
            fallback = (str(key), val, name)

    if fallback:
        return fallback
    if "proxy" in doc and isinstance(doc["proxy"], str):
        return "proxy", doc["proxy"], None
    return None, None, None


def _walk_anchor_refs(container, old_node, new_node=None) -> int:
    """统计或替换 YAML 中指向锚点节点的所有引用（含顶层定义处）

    new_node 为 None 时只统计；否则把每个引用原地替换为 new_node。
    ruamel 加载 `*proxy` 时返回的就是锚点节点本身（同一对象），因此必须
    同步替换所有引用，否则 dump 后别名仍指向旧值。
    """
    count = 0
    if isinstance(container, dict):
        for key in list(container.keys()):
            val = container[key]
            if val is old_node:
                count += 1
                if new_node is not None:
                    container[key] = new_node
            elif isinstance(val, (dict, list)):
                count += _walk_anchor_refs(val, old_node, new_node)
    elif isinstance(container, list):
        for i, val in enumerate(container):
            if val is old_node:
                count += 1
                if new_node is not None:
                    container[i] = new_node
            elif isinstance(val, (dict, list)):
                count += _walk_anchor_refs(val, old_node, new_node)
    return count


def get_settings() -> Dict[str, Any]:
    """读取设置页数据：共享代理锚点、引用数量与 notify 配置"""
    result = {
        "config_exists": CONFIG_FILE.exists(),
        "proxy": "",
        "proxy_exists": False,
        "proxy_key": None,
        "proxy_anchor": None,
        "proxy_refs": 0,
        "notify": _default_notify_settings(),
    }
    if not result["config_exists"]:
        return result

    ry = _ruamel_yaml()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        doc = ry.load(f)
    if not doc:
        return result

    key, node, anchor = _find_shared_proxy(doc)
    if node is not None:
        result["proxy"] = str(node)
        result["proxy_exists"] = True
        result["proxy_key"] = key
        result["proxy_anchor"] = anchor or "proxy"
        if anchor:
            result["proxy_refs"] = max(0, _walk_anchor_refs(doc, node) - 1)

    notify = doc.get("notify") or {}
    result["notify"]["on_failure"] = bool(notify.get("on_failure", True))
    result["notify"]["on_success"] = bool(notify.get("on_success", False))
    for section, fields in NOTIFY_FIELDS.items():
        cfg = notify.get(section) or {}
        for field in fields:
            value = cfg.get(field)
            if value is None:
                continue
            text = str(value)
            if field in NOTIFY_BLOCK_FIELDS:
                text = text.rstrip("\n")
            result["notify"][section][field] = text
    return result


def validate_settings_payload(data: Dict[str, Any]) -> List[str]:
    """校验设置页提交的数据，返回错误列表"""
    errors: List[str] = []
    if "proxy" in data and not isinstance(data["proxy"], str):
        errors.append(i18n.t("settings.err_proxy_format"))

    notify = data.get("notify")
    if notify is None:
        return errors
    if not isinstance(notify, dict):
        return [i18n.t("settings.err_notify_format")]

    webhook = notify.get("webhook") or {}
    ntfy = notify.get("ntfy") or {}
    if not isinstance(webhook, dict) or not isinstance(ntfy, dict):
        return [i18n.t("settings.err_notify_format")]

    for label, cfg in (("Webhook", webhook), ("NTFY", ntfy)):
        url = str(cfg.get("url") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            errors.append(i18n.t("settings.err_url_scheme", label=label))

    method = str(webhook.get("method") or "POST").upper()
    if method not in WEBHOOK_METHODS:
        errors.append(i18n.t("settings.err_webhook_method"))
    content_type = str(webhook.get("content_type") or "application/json")
    if content_type not in WEBHOOK_CONTENT_TYPES:
        errors.append(i18n.t("settings.err_webhook_content_type"))
    priority = str(ntfy.get("priority") or "3")
    if priority not in ("1", "2", "3", "4", "5"):
        errors.append(i18n.t("settings.err_ntfy_priority"))
    return errors


def save_settings(data: Dict[str, Any]) -> tuple[bool, str, int]:
    """保存共享代理与通知配置，保留 YAML 锚点、别名和注释

    Returns:
        (success, message, proxy_refs)  proxy_refs 为共享代理被引用的任务数
    """
    from ruamel.yaml.comments import CommentedMap
    from ruamel.yaml.scalarstring import (
        DoubleQuotedScalarString,
        LiteralScalarString,
        ScalarString,
    )

    try:
        ry = _ruamel_yaml()
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            doc = ry.load(f)
        if not doc:
            return False, i18n.t("settings.err_empty_config"), 0

        proxy_refs = 0
        if "proxy" in data:
            value = str(data["proxy"] or "").strip()
            key, old_node, anchor = _find_shared_proxy(doc)
            if old_node is not None and anchor:
                # 保留原标量样式与锚点名，并把所有别名引用一起换成新节点
                new_node = (
                    type(old_node)(value)
                    if isinstance(old_node, ScalarString)
                    else DoubleQuotedScalarString(value)
                )
                new_node.yaml_set_anchor(anchor, always_dump=True)
                proxy_refs = max(
                    0, _walk_anchor_refs(doc, old_node, new_node) - 1
                )
            else:
                # 配置中尚无锚点：新建 `proxy: &proxy ...` 定义
                new_node = DoubleQuotedScalarString(value)
                new_node.yaml_set_anchor(anchor or "proxy", always_dump=True)
                doc[key or "proxy"] = new_node

        notify_data = data.get("notify")
        if isinstance(notify_data, dict):
            notify = doc.get("notify")
            if notify is None:
                notify = CommentedMap()
                doc["notify"] = notify

            for flag in ("on_failure", "on_success"):
                if flag in notify_data:
                    notify[flag] = bool(notify_data[flag])

            for section, fields in NOTIFY_FIELDS.items():
                section_data = notify_data.get(section)
                if not isinstance(section_data, dict):
                    continue
                cfg = notify.get(section)
                if cfg is None:
                    cfg = CommentedMap()
                    notify[section] = cfg
                for field in fields:
                    if field not in section_data:
                        continue
                    text = str(section_data[field] or "")
                    if field in NOTIFY_BLOCK_FIELDS:
                        cfg[field] = LiteralScalarString(text.rstrip("\n") + "\n")
                    else:
                        cfg[field] = text

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            ry.dump(doc, f)
        return True, i18n.t("settings.saved"), proxy_refs
    except Exception as e:
        log_error(f"保存设置失败: {e}")
        return False, i18n.t("settings.err_save", message=str(e)), 0


def validate_cron_expression(expr: str) -> Dict[str, Any]:
    """验证 cron 表达式并返回下次执行时间和调度说明

    Returns:
        dict: {"valid": bool, "error"?: str, "next_run"?: str, "description"?: str}
    """
    try:
        from croniter import croniter

        expr = (expr or "").strip()
        if not expr:
            return {"valid": False, "error": i18n.t("cron.err_empty")}

        parts = expr.split()
        if len(parts) != 5:
            return {
                "valid": False,
                "error": i18n.t("cron.err_segments", n=len(parts)),
            }

        if not croniter.is_valid(expr):
            return {"valid": False, "error": i18n.t("cron.err_invalid")}

        itr = croniter(expr, datetime.now())
        next_time = itr.get_next(datetime)
        return {
            "valid": True,
            "next_run": next_time.strftime("%Y-%m-%d %H:%M"),
            "description": parse_cron(expr),
        }
    except Exception as e:
        return {"valid": False, "error": i18n.t("cron.err_failed", message=str(e))}


def script_path_exists(script_path: str) -> bool:
    """检查脚本文件是否存在（兼容容器和宿主机两种路径布局）"""
    if not script_path:
        return False
    p = PROJECT_ROOT / script_path
    if p.exists():
        return True
    p = PROJECT_ROOT.parent / script_path
    return p.exists()


def _collect_top_level_anchors(doc) -> Dict[int, str]:
    """收集顶层（非 tasks 段）所有带锚点的值，返回 {id(node): anchor_name}"""
    anchors: Dict[int, str] = {}
    if not doc:
        return anchors
    try:
        for key, val in doc.items():
            if key == "tasks":
                continue
            anc = getattr(val, "anchor", None)
            if anc is not None:
                anc_val = getattr(anc, "value", None)
                if anc_val:
                    anchors[id(val)] = anc_val
    except Exception:
        pass
    return anchors


def get_task_detail(task_name: str) -> Optional[Dict[str, Any]]:
    """获取任务详情（包含 env vars 和别名信息），用于编辑表单初始化

    使用 ruamel.yaml 加载以保留锚点信息，并通过 id 比对识别别名引用。
    """
    try:
        from ruamel.yaml import YAML

        ry = YAML()
        ry.preserve_quotes = True

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            doc = ry.load(f)

        if not doc or "tasks" not in doc:
            return None

        anchors = _collect_top_level_anchors(doc)

        target_task = None
        all_names: List[str] = []
        for task in doc["tasks"]:
            name = task.get("name", "")
            all_names.append(str(name))
            if (
                isinstance(name, str)
                and name.lower() == task_name.lower()
                and target_task is None
            ):
                target_task = task

        if target_task is None:
            return None

        # 构建 env 列表，标记别名引用
        env_list = []
        env = target_task.get("env") or {}
        for key, value in env.items():
            is_alias = id(value) in anchors
            alias_target = anchors.get(id(value))
            env_list.append(
                {
                    "key": str(key),
                    "value": "" if value is None else str(value),
                    "is_alias": is_alias,
                    "alias_target": alias_target,
                }
            )

        schedule = str(target_task.get("schedule", ""))
        return {
            "name": str(target_task.get("name", "")),
            "description": str(target_task.get("description", "")),
            "schedule": schedule,
            "script": str(target_task.get("script", "")),
            "enabled": bool(target_task.get("enabled", True)),
            "env": env_list,
            "script_exists": script_path_exists(str(target_task.get("script", ""))),
            "all_task_names": all_names,
            "original_name": task_name,
        }
    except Exception as e:
        log_error(f"获取任务详情失败: {e}")
        return None


def update_task_config(
    original_name: str, updates: Dict[str, Any]
) -> tuple[bool, str]:
    """更新任务配置，保留 YAML 锚点、别名与注释

    采用字段级更新策略：
    - 标量字段（name/schedule/script/description/enabled）直接覆写
    - env 段执行键级合并：值未变的键保留原节点（保留 *proxy 别名），
      值变更的键替换为字面量，新增键追加，删除键移除

    Returns:
        (success, message)
    """
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.comments import CommentedMap

        ry = YAML()
        ry.preserve_quotes = True

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            doc = ry.load(f)

        if not doc or "tasks" not in doc:
            return False, i18n.t("tasks.edit_no_tasks")

        # 定位目标任务
        target_task = None
        for task in doc["tasks"]:
            name = task.get("name", "")
            if isinstance(name, str) and name.lower() == original_name.lower():
                target_task = task
                break

        if target_task is None:
            return False, i18n.t("tasks.server_not_found", name=original_name)

        # 名称唯一性校验（若重命名）
        new_name = (updates.get("name") or "").strip()
        if not new_name:
            return False, i18n.t("tasks.err_name_required")
        if new_name.lower() != original_name.lower():
            for task in doc["tasks"]:
                if task is target_task:
                    continue
                n = task.get("name", "")
                if isinstance(n, str) and n.lower() == new_name.lower():
                    return False, i18n.t("tasks.edit_name_exists", name=new_name)

        # 更新标量字段
        target_task["name"] = new_name
        target_task["description"] = (updates.get("description") or "").strip()
        target_task["schedule"] = (updates.get("schedule") or "").strip()
        target_task["script"] = (updates.get("script") or "").strip()
        if "enabled" in updates:
            target_task["enabled"] = bool(updates["enabled"])

        # env 段键级合并，保留未变更键的原始节点（含别名）
        new_env_list = updates.get("env", []) or []
        existing_env = target_task.get("env", None)
        if existing_env is None:
            existing_env = CommentedMap()
            target_task["env"] = existing_env

        # 收集表单中的键（跳过空键）
        form_items: List[Dict[str, str]] = []
        for item in new_env_list:
            key = (item.get("key") or "").strip()
            if not key:
                continue
            form_items.append({"key": key, "value": item.get("value", "") or ""})

        new_keys = {it["key"] for it in form_items}

        # 移除表单中已删除的键
        for k in [k for k in list(existing_env.keys()) if k not in new_keys]:
            del existing_env[k]

        # 新增/更新键（值变化才覆写，未变化保留原节点）
        for it in form_items:
            key = it["key"]
            value = it["value"]
            if key in existing_env:
                current = existing_env[key]
                current_str = "" if current is None else str(current)
                if current_str != value:
                    existing_env[key] = value
            else:
                existing_env[key] = value

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            ry.dump(doc, f)

        # log_success(f"[WebUI] 任务 {new_name} 配置已更新")
        return True, i18n.t("tasks.edit_updated", name=new_name)
    except Exception as e:
        log_error(f"更新任务配置失败: {e}")
        return False, i18n.t("tasks.edit_failed", message=str(e))


def perform_reload() -> tuple[bool, str]:
    """重载配置：重新生成 .env 与 crontab，并加载 crontab（Linux）

    抽取自 api_reload，便于编辑任务后自动调用。
    Windows 环境跳过 crontab 更新。
    """
    try:
        # 1. 重新生成环境变量
        make_env_path = PROJECT_ROOT / "make_env.py"
        if make_env_path.exists():
            env_file = PROJECT_ROOT / ".env"
            result = subprocess.run(
                [sys.executable, str(make_env_path), str(CONFIG_FILE), str(env_file)],
                capture_output=True,
                text=True,
                cwd=str(PROJECT_ROOT),
            )
            if result.returncode != 0:
                return False, i18n.t("reload_env_failed", message=result.stderr)

        # Windows 环境跳过 crontab 相关操作（cron 是 Linux-only）
        if os.name == "nt":
            log_success("[WebUI] 配置重载完成（Windows 环境跳过 crontab 更新）")
            return True, i18n.t("reload_done_windows")

        # 2. 重新生成 crontab 文件
        cron_file = "/tmp/crontab"
        make_cron_path = PROJECT_ROOT / "make_cron.py"
        if not make_cron_path.exists():
            return False, i18n.t("reload_no_make_cron")

        with open(cron_file, "w", encoding="utf-8") as f:
            f.write("# 自动生成的crontab - 由 WebUI 重载\n")
            f.write("# 不要手动编辑此文件\n\n")
            f.write('# 禁用邮件通知，避免输出被邮件系统捕获\n')
            f.write('MAILTO=""\n\n')
            f.write("# 全局环境变量\n")
            f.write(f"APP_ENV={os.environ.get('APP_ENV', 'production')}\n")
            f.write(f"LOG_LEVEL={os.environ.get('LOG_LEVEL', 'INFO')}\n")
            f.write("PYTHONPATH=/app\n\n")
            f.write("PATH=/usr/local/bin:/usr/bin:/bin\n\n")

        result = subprocess.run(
            [sys.executable, str(make_cron_path), str(CONFIG_FILE), cron_file],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            return False, i18n.t("reload_cron_failed", message=result.stderr)

        # 3. 加载新的 crontab
        result = subprocess.run(
            ["crontab", cron_file],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, i18n.t("reload_load_failed", message=result.stderr)

        log_success("[WebUI] 配置重载完成")
        return True, i18n.t("reload_done")
    except Exception as e:
        log_error(f"重载配置失败: {e}")
        return False, i18n.t("reload_failed", message=str(e))


def get_container_status() -> Dict[str, Any]:
    """获取容器状态"""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "name=lite-cron",
                "--format",
                "{{.Names}}\t{{.Status}}\t{{.Ports}}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            if lines and lines[0]:
                parts = lines[0].split("\t")
                return {
                    "running": True,
                    "name": parts[0] if len(parts) > 0 else "lite-cron",
                    "status": parts[1] if len(parts) > 1 else "unknown",
                    "ports": parts[2] if len(parts) > 2 else "",
                }

        result2 = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=lite-cron",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result2.returncode == 0 and "lite-cron" in result2.stdout:
            return {
                "running": False,
                "exists": True,
                "message": i18n.t("container.stopped"),
            }

        return {
            "running": False,
            "exists": False,
            "message": i18n.t("container.missing"),
        }
    except Exception as e:
        return {
            "running": False,
            "error": str(e),
            "message": i18n.t("container.unknown"),
        }


def _cron_weekday_name(weekday: str) -> Optional[str]:
    """取星期名；不在 0-7 内（如 1-5）时返回 None，与旧实现的跳过行为一致。"""
    key = f"cron.day_{weekday}"
    name = i18n.t(key)
    return None if name == key else name


def parse_cron(cron_expr: str) -> str:
    """解析 cron 表达式为人类可读格式（跟随当前界面语言）"""
    parts = (cron_expr or "").split()
    if len(parts) != 5:
        return cron_expr

    minute, hour, day, month, weekday = parts
    if i18n.current_language() == i18n.LANG_EN:
        return _describe_cron_en(minute, hour, weekday, cron_expr)
    return _describe_cron_zh(minute, hour, weekday, cron_expr)


def _describe_cron_zh(minute: str, hour: str, weekday: str, cron_expr: str) -> str:
    """中文描述：措辞与改造前逐字一致（如「0分 2时」「每30分钟」）。"""
    desc = []

    if minute == "*":
        desc.append(i18n.t("cron.desc_every_minute"))
        repeat_minute = True
    elif minute.startswith("*/"):
        desc.append(i18n.t("cron.desc_every_n_minutes", n=minute[2:]))
        repeat_minute = True
    else:
        desc.append(i18n.t("cron.desc_at_minute", n=minute))
        repeat_minute = False

    if hour == "*":
        if repeat_minute:
            desc.append(i18n.t("cron.desc_every_hour"))
    elif hour.startswith("*/"):
        desc.append(i18n.t("cron.desc_every_n_hours", n=hour[2:]))
    else:
        desc.append(i18n.t("cron.desc_at_hour", n=hour))

    if weekday != "*":
        day_name = _cron_weekday_name(weekday)
        if day_name:
            desc.append(i18n.t("cron.desc_weekday", day=day_name))

    return " ".join(desc) if len(desc) <= 3 else cron_expr


def _describe_cron_en(minute: str, hour: str, weekday: str, cron_expr: str) -> str:
    """英文描述：分钟内与小时均为数字时合并成钟点（如「at 02:00」）。"""
    desc = []

    if minute == "*" and hour == "*":
        desc.append(i18n.t("cron.desc_every_minute"))
    elif minute.isdigit() and hour.isdigit():
        desc.append(
            i18n.t("cron.desc_at_time", time=f"{int(hour):02d}:{int(minute):02d}")
        )
    else:
        if minute == "*":
            desc.append(i18n.t("cron.desc_every_minute"))
        elif minute.startswith("*/"):
            desc.append(i18n.t("cron.desc_every_n_minutes", n=minute[2:]))
        else:
            desc.append(i18n.t("cron.desc_at_minute", n=minute))

        if hour == "*":
            # 「every N minutes」已隐含每小时，只有定点分钟才补上 every hour
            if minute.isdigit():
                desc.append(i18n.t("cron.desc_every_hour"))
        elif hour.startswith("*/"):
            desc.append(i18n.t("cron.desc_every_n_hours", n=hour[2:]))
        else:
            desc.append(i18n.t("cron.desc_at_hour", n=hour))

    if weekday != "*":
        day_name = _cron_weekday_name(weekday)
        if day_name:
            desc.append(i18n.t("cron.desc_weekday", day=day_name))

    return " ".join(desc) if len(desc) <= 3 else cron_expr


def get_next_run(cron_expr: str) -> Optional[str]:
    """获取下次执行时间"""
    try:
        from croniter import croniter
        from datetime import datetime

        itr = croniter(cron_expr, datetime.now())
        next_time = itr.get_next(datetime)
        return next_time.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


# ============== 路由 ==============


@app.before_request
def require_auth():
    """统一鉴权：有效 Session 或 Bearer Token 才放行，否则跳登录或 401

    鉴权关闭（AUTH_TOKEN 为空）时全部放行；此时应配合 WEBUI_HOST=127.0.0.1
    保证仅本地可访问。白名单：/login 与 /static/*。
    """
    if not AUTH_TOKEN:
        return None
    path = request.path
    if path == "/login" or path.startswith("/static/"):
        return None
    # 1) Session Cookie 已登录
    if session.get("logged_in"):
        return None
    # 2) Bearer Token（供脚本/curl 自动化调用）
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token and token == AUTH_TOKEN:
            return None
    # 未通过：API 返回 401，页面跳转登录
    if path.startswith("/api/"):
        return (
            jsonify({"error": "unauthorized", "message": i18n.t("auth.required")}),
            401,
        )
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    """登录页：POST 校验 token 并写入 Session"""
    # 鉴权关闭时直接回首页
    if not AUTH_TOKEN:
        return redirect("/")
    if request.method == "POST":
        token = (request.form.get("token") or "").strip()
        if token and token == AUTH_TOKEN:
            # 启用永久 Session，有效期由 app.permanent_session_lifetime 控制
            session.permanent = True
            session["logged_in"] = True
            log_info("[WebUI] 用户登录成功")
            return redirect("/")
        log_warning("[WebUI] 登录失败：令牌无效")
        return render_template("login.html", error_key="auth.invalid_token"), 401
    return render_template("login.html", error_key=None)


@app.route("/logout", methods=["POST"])
def logout():
    """退出登录：清空 Session 后跳登录页"""
    session.clear()
    return redirect("/login")


@app.route("/")
def index():
    """首页"""
    return render_template(
        "index.html",
        app_version=APP_VERSION,
        auth_enabled=bool(AUTH_TOKEN),
    )


@app.route("/settings")
def settings_page():
    """设置已改为首页弹窗，保留旧地址重定向避免书签失效"""
    return redirect("/")


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """读取 / 保存共享代理地址与通知配置"""
    if request.method == "GET":
        try:
            return jsonify({"success": True, "settings": get_settings()})
        except Exception as e:
            log_error(f"读取设置失败: {e}")
            return (
                jsonify(
                    {
                        "success": False,
                        "message": i18n.t("settings.err_read", message=str(e)),
                    }
                ),
                500,
            )

    data = request.get_json(silent=True) or {}
    errors = validate_settings_payload(data)
    if errors:
        return (
            jsonify(
                {
                    "success": False,
                    "message": i18n.t("common.error_sep").join(errors),
                }
            ),
            400,
        )

    ok, message, proxy_refs = save_settings(data)
    if not ok:
        return jsonify({"success": False, "message": message}), 500

    # 代理值写入后需重新生成 .env / crontab，让任务在下一次执行时使用新地址
    reloaded, reload_msg = perform_reload()
    if reloaded:
        log_success("[WebUI] 设置已保存并重载配置")
    else:
        log_warning(f"[WebUI] 设置已保存，但重载失败: {reload_msg}")

    return jsonify(
        {
            "success": True,
            "message": message,
            "proxy_refs": proxy_refs,
            "reloaded": reloaded,
            "reload_message": reload_msg,
        }
    )


@app.route("/static/<path:filename>")
def static_files(filename):
    """静态文件"""
    return send_from_directory(str(STATIC_DIR), filename)


@app.route("/api/status")
def api_status():
    """获取状态"""
    try:
        config = load_config()
        container_status = get_container_status()

        task_count = 0
        enabled_count = 0
        config_exists = CONFIG_FILE.exists()

        if config and "tasks" in config:
            task_count = len(config["tasks"])
            enabled_count = sum(1 for t in config["tasks"] if t.get("enabled", True))

        return jsonify(
            {
                "version": APP_VERSION,
                "container": container_status,
                "tasks": {
                    "total": task_count,
                    "enabled": enabled_count,
                    "disabled": task_count - enabled_count,
                },
                "config_exists": config_exists,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/debug")
def api_debug():
    """调试信息"""
    import os

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    return jsonify(
        {
            "cwd": str(PROJECT_ROOT),
            "config_exists": CONFIG_FILE.exists(),
            "logs_dir": str(LOGS_DIR),
            "logs_dir_exists": LOGS_DIR.exists(),
            "logs_files": (
                [f.name for f in LOGS_DIR.glob("*.log")] if LOGS_DIR.exists() else []
            ),
            "python_version": sys.version,
        }
    )


@app.route("/api/tasks")
def api_tasks():
    """获取任务列表"""
    try:
        config = load_config()
        config_exists = CONFIG_FILE.exists()

        if not config or "tasks" not in config:
            return jsonify({"tasks": [], "config_exists": config_exists})

        tasks = []
        for i, task in enumerate(config["tasks"], 1):
            cron_expr = task.get("schedule", "")
            tasks.append(
                {
                    "id": i,
                    "name": task.get("name", "未命名"),
                    "schedule": cron_expr,
                    "schedule_desc": parse_cron(cron_expr),
                    "script": task.get("script", ""),
                    "description": task.get("description", ""),
                    "enabled": task.get("enabled", True),
                    "next_run": (
                        get_next_run(cron_expr) if task.get("enabled", True) else None
                    ),
                }
            )

        return jsonify({"tasks": tasks, "config_exists": True})
    except Exception as e:
        return jsonify({"error": str(e), "tasks": []}), 500


@app.route("/api/tasks/<task_name>/run", methods=["POST"])
def api_run_task(task_name: str):
    """执行任务"""

    def generate():
        log_info(f"[WebUI] 开始执行任务: {task_name}")
        yield json.dumps(
            {
                "status": "started",
                "message": i18n.t("tasks.run_started", name=task_name),
            },
            ensure_ascii=False,
        ) + "\n"

        try:
            config = load_config()
            if not config or "tasks" not in config:
                log_error(f"[WebUI] 执行任务 {task_name} 失败: 配置未找到")
                yield json.dumps(
                    {"status": "error", "message": i18n.t("tasks.run_no_config")},
                    ensure_ascii=False,
                ) + "\n"
                return

            task = None
            for t in config["tasks"]:
                if t.get("name", "").lower() == task_name.lower():
                    task = t
                    break

            if not task:
                log_error(f"[WebUI] 执行任务 {task_name} 失败: 任务未找到")
                yield json.dumps(
                    {
                        "status": "error",
                        "message": i18n.t("tasks.server_not_found", name=task_name),
                    },
                    ensure_ascii=False,
                ) + "\n"
                return

            if not task.get("enabled", True):
                log_warning(f"[WebUI] 执行任务 {task_name} 失败: 任务已禁用")
                yield json.dumps(
                    {"status": "error", "message": i18n.t("tasks.run_disabled")},
                    ensure_ascii=False,
                ) + "\n"
                return

            script_path = task.get("script", "")
            if not script_path:
                log_error(f"[WebUI] 执行任务 {task_name} 失败: 任务未配置脚本")
                yield json.dumps(
                    {"status": "error", "message": i18n.t("tasks.run_no_script")},
                    ensure_ascii=False,
                ) + "\n"
                return

            full_script_path = PROJECT_ROOT / script_path
            if not full_script_path.exists():
                full_script_path = PROJECT_ROOT.parent / script_path
            if not full_script_path.exists():
                log_error(f"[WebUI] 执行任务 {task_name} 失败: 脚本文件不存在 {script_path}")
                yield json.dumps(
                    {
                        "status": "error",
                        "message": i18n.t(
                            "tasks.run_missing_script", path=script_path
                        ),
                    },
                    ensure_ascii=False,
                ) + "\n"
                return

            task_env = os.environ.copy()
            task_env["LITECRON_EXEC_MODE"] = "webui"
            task_env["LITECRON_TASK_NAME"] = task_name

            if "env" in task:
                for key, value in task["env"].items():
                    task_env[key] = str(value)
            if "global_env" in config:
                for key, value in config["global_env"].items():
                    task_env[key] = str(value)

            # 使用当前 Python 解释器执行
            wrapper_py_path = PROJECT_ROOT / "task_wrapper.py"
            if wrapper_py_path.exists():
                cmd = [sys.executable, str(wrapper_py_path), task_name, str(full_script_path)]
            else:
                cmd = [sys.executable, str(full_script_path)]

            yield json.dumps(
                {
                    "status": "running",
                    "output": i18n.t("tasks.run_command", command=" ".join(cmd)),
                },
                ensure_ascii=False,
            ) + "\n"

            # 父子进程统一按 UTF-8 交换输出。
            # 不能沿用 Windows 的 locale 编码（GBK）：子进程 sys.stdout 变成 GBK 后，
            # 任何带 emoji 的日志行都会抛 UnicodeEncodeError，直接把任务打死
            # （NodeSeek 的 🚀、FnClub 的 ✅ 就是这种情况）。PYTHONIOENCODING
            # 让子进程也写 UTF-8，这里按 UTF-8 解码，中文与 emoji 都能完整还原。
            task_env["PYTHONIOENCODING"] = "utf-8"

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(PROJECT_ROOT),
                env=task_env,
            )

            for line in process.stdout:
                line = line.strip()
                if line:
                    print(line, flush=True)
                    yield json.dumps(
                        {"status": "running", "output": line}, ensure_ascii=False
                    ) + "\n"

            process.wait()
            success = process.returncode == 0

            if success:
                log_success(f"[WebUI] 任务 {task_name} 执行成功")
            else:
                log_error(f"[WebUI] 任务 {task_name} 执行失败 (返回码: {process.returncode})")

            yield json.dumps(
                {
                    "status": "completed",
                    "success": success,
                    "returncode": process.returncode,
                    "message": i18n.t(
                        "tasks.run_done" if success else "tasks.run_done_failed"
                    ),
                },
                ensure_ascii=False,
            ) + "\n"

        except Exception as e:
            log_error(f"[WebUI] 执行任务 {task_name} 出错: {str(e)}")
            yield json.dumps(
                {
                    "status": "error",
                    "success": False,
                    "message": i18n.t("tasks.run_error", message=str(e)),
                },
                ensure_ascii=False,
            ) + "\n"

    # stream_with_context：生成器在视图返回之后才被消费，需显式保留请求上下文，
    # 否则内部 i18n.t() 取不到 g.lang，终端系统行会退回中文
    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


@app.route("/api/tasks/<task_name>/toggle", methods=["POST"])
def api_toggle_task(task_name: str):
    """切换任务状态

    通过 toggle_task_enabled 直接操作 ruamel doc，仅改 enabled 字段，
    避免 safe_load 展开别名后回灌覆盖 YAML 锚点（如顶部 proxy 锚点）。
    """
    new_status = toggle_task_enabled(task_name)
    if new_status is None:
        return jsonify(
            {"success": False, "message": i18n.t("tasks.server_not_found_save")}
        )

    return jsonify(
        {
            "success": True,
            "enabled": new_status,
            "message": i18n.t(
                "tasks.toggle_enabled" if new_status else "tasks.toggle_disabled"
            ),
        }
    )


def set_all_tasks_enabled(enabled: bool) -> tuple[bool, int, str]:
    """批量设置所有任务的启用状态

    Args:
        enabled: True 表示全部启用，False 表示全部禁用

    Returns:
        (success, count, message)
    """
    try:
        from ruamel.yaml import YAML

        ry = YAML()
        ry.preserve_quotes = True

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            doc = ry.load(f)

        if not doc or "tasks" not in doc:
            return False, 0, i18n.t("tasks.batch_no_config")

        count = 0
        for task in doc["tasks"]:
            current = bool(task.get("enabled", True))
            if current != enabled:
                task["enabled"] = enabled
                count += 1

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            ry.dump(doc, f)

        action = "启用" if enabled else "禁用"
        log_success(f"[WebUI] 批量操作：已{action} {count} 个任务")
        return (
            True,
            count,
            i18n.t("tasks.batch_enabled" if enabled else "tasks.batch_disabled", n=count),
        )
    except Exception as e:
        log_error(f"批量{enabled and '启用' or '禁用'}任务失败: {e}")
        return False, 0, i18n.t("tasks.batch_failed", message=str(e))


@app.route("/api/tasks/batch/toggle", methods=["POST"])
def api_batch_toggle_tasks():
    """批量启用/禁用所有任务"""
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))

    success, count, message = set_all_tasks_enabled(enabled)
    if success:
        return jsonify({"success": True, "count": count, "message": message})
    return jsonify({"success": False, "count": 0, "message": message}), 500


@app.route("/api/logs")
def api_logs():
    """获取日志文件列表"""
    log_files = []
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if LOGS_DIR.exists():
        for log_file in sorted(LOGS_DIR.glob("*.log"), reverse=True):
            try:
                stat = log_file.stat()
                log_files.append(
                    {
                        "name": log_file.name,
                        "size": stat.st_size,
                        "size_human": format_size(stat.st_size),
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    }
                )
            except Exception:
                continue

    return jsonify({"logs": log_files})


@app.route("/api/logs/<path:filename>")
def api_log_content(filename: str):
    """获取日志内容"""
    log_file = LOGS_DIR / filename

    try:
        log_file.resolve().relative_to(LOGS_DIR.resolve())
    except ValueError:
        return jsonify({"error": i18n.t("logs.err_invalid_path")}), 403

    if not log_file.exists():
        return jsonify({"content": "", "lines": 0})

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = content.split("\n")

        # 去除因文件末尾换行符产生的空字符串元素，避免日志页面出现空白行/空白分组
        while lines and not lines[-1].strip():
            lines.pop()

        limit = request.args.get("limit", type=int)
        if limit and len(lines) > limit:
            lines = lines[-limit:]
            content = "\n".join(lines)

        return jsonify({"content": content, "lines": len(lines), "filename": filename})
    except Exception as e:
        return (
            jsonify({"error": i18n.t("logs.err_read", message=str(e))}),
            500,
        )


@app.route("/api/reload", methods=["POST"])
def api_reload():
    """重载配置文件并刷新 cron 调度"""
    success, message = perform_reload()
    if success:
        return jsonify({"success": True, "message": message})
    return jsonify({"success": False, "message": message}), 500


@app.route("/api/tasks/<task_name>/detail")
def api_task_detail(task_name: str):
    """获取任务详情（包含 env 和别名信息），用于编辑表单初始化"""
    detail = get_task_detail(task_name)
    if detail is None:
        return (
            jsonify(
                {
                    "success": False,
                    "message": i18n.t("tasks.server_not_found", name=task_name),
                }
            ),
            404,
        )
    return jsonify({"success": True, "task": detail})


@app.route("/api/validate/cron", methods=["POST"])
def api_validate_cron():
    """验证 cron 表达式并返回下次执行时间和调度说明（用于实时预览）"""
    data = request.get_json(silent=True) or {}
    expr = data.get("schedule", "") or ""
    result = validate_cron_expression(expr)
    return jsonify(result)


@app.route("/api/validate/script", methods=["POST"])
def api_validate_script():
    """检查脚本文件路径是否存在"""
    data = request.get_json(silent=True) or {}
    script = (data.get("script") or "").strip()
    if not script:
        return jsonify({"valid": False, "error": i18n.t("tasks.validate_empty_script")})
    exists = script_path_exists(script)
    return jsonify(
        {
            "valid": exists,
            "error": ""
            if exists
            else i18n.t("tasks.validate_missing_script", path=script),
        }
    )


@app.route("/api/tasks/<task_name>/edit", methods=["POST"])
def api_edit_task(task_name: str):
    """编辑任务配置

    流程：服务端校验 → 字段级更新 config.yml（保留锚点/注释）→ 自动重载
    """
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    schedule = (data.get("schedule") or "").strip()
    script = (data.get("script") or "").strip()
    description = (data.get("description") or "").strip()
    enabled = data.get("enabled")
    env_list = data.get("env") or []

    # 1. 非空校验
    errors = []
    if not name:
        errors.append(i18n.t("tasks.err_name_required"))
    if not schedule:
        errors.append(i18n.t("tasks.err_schedule_required"))
    if not script:
        errors.append(i18n.t("tasks.err_script_required"))

    # 2. Cron 格式校验
    cron_result = validate_cron_expression(schedule) if schedule else None
    if cron_result and not cron_result.get("valid"):
        errors.append(
            i18n.t(
                "tasks.err_schedule_prefix",
                error=cron_result.get("error", i18n.t("cron.err_invalid")),
            )
        )

    # 3. 脚本路径存在性校验
    if script and not script_path_exists(script):
        errors.append(i18n.t("tasks.validate_missing_script", path=script))

    # 4. env 键名规范校验（仅校验非别名的键：键名不能为空、不能重复）
    seen_keys = set()
    for item in env_list:
        key = (item.get("key") or "").strip()
        if not key:
            continue
        if key in seen_keys:
            errors.append(i18n.t("tasks.err_dup_env", key=key))
        seen_keys.add(key)

    if errors:
        return (
            jsonify(
                {
                    "success": False,
                    "message": i18n.t("common.error_sep").join(errors),
                }
            ),
            400,
        )

    # 5. 更新 config.yml（保留锚点/注释）
    updates = {
        "name": name,
        "schedule": schedule,
        "script": script,
        "description": description,
        "env": env_list,
    }
    if enabled is not None:
        updates["enabled"] = bool(enabled)

    ok, msg = update_task_config(task_name, updates)
    if not ok:
        log_error(f"[WebUI] 编辑任务 {task_name} 失败: {msg}")
        return jsonify({"success": False, "message": msg}), 500

    # 6. 自动重载配置（生成 .env + crontab）
    reload_ok, reload_msg = perform_reload()
    if reload_ok:
        log_success(f"[WebUI] 任务 {name} 编辑完成并重载成功")
    else:
        log_warning(f"[WebUI] 任务 {name} 编辑完成，但重载失败: {reload_msg}")

    return jsonify(
        {
            "success": True,
            "message": msg,
            "reloaded": reload_ok,
            "reload_message": reload_msg,
        }
    )


@app.route("/api/clean", methods=["POST"])
def api_clean():
    """清理日志"""
    try:
        import time

        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        cleaned_count = 0
        current_time = time.time()
        seven_days_ago = current_time - (7 * 24 * 60 * 60)

        if LOGS_DIR.exists():
            for log_file in LOGS_DIR.glob("*.log"):
                try:
                    stat = log_file.stat()
                    if stat.st_mtime < seven_days_ago:
                        log_file.unlink()
                        cleaned_count += 1
                except Exception:
                    pass

        # 清理任务失败时落盘的响应原文（logs/responses/<日期>/），并移除空目录
        responses_dir = LOGS_DIR / "responses"
        if responses_dir.exists():
            for dump_file in responses_dir.rglob("*"):
                try:
                    if dump_file.is_file() and dump_file.stat().st_mtime < seven_days_ago:
                        dump_file.unlink()
                        cleaned_count += 1
                except Exception:
                    pass
            for sub_dir in sorted(responses_dir.glob("*"), reverse=True):
                try:
                    if sub_dir.is_dir() and not any(sub_dir.iterdir()):
                        sub_dir.rmdir()
                except Exception:
                    pass

        if cleaned_count > 0:
            log_success(f"[WebUI] 已清理 {cleaned_count} 个超过7天的日志文件")
        else:
            log_info("[WebUI] 无需清理，未找到超过7天的日志文件")

        return jsonify(
            {
                "success": True,
                "message": i18n.t("logs.cleaned_server", n=cleaned_count),
                "cleaned": cleaned_count,
            }
        )
    except Exception as e:
        log_error(f"[WebUI] 清理日志失败: {str(e)}")
        return (
            jsonify(
                {
                    "success": False,
                    "message": i18n.t("logs.clean_failed_server", message=str(e)),
                }
            ),
            500,
        )


if __name__ == "__main__":
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 从环境变量读取端口，默认 5000
    port = int(os.environ.get("WEBUI_PORT", 5000))

    # 从配置文件读取 webui 设置
    config = load_config()
    webui_cfg = {}
    if config and isinstance(config, dict) and "webui" in config:
        webui_cfg = config["webui"] or {}
    debug_mode = bool(webui_cfg.get("debug", False))

    # 鉴权与绑定配置：环境变量优先于 config.yml，默认 127.0.0.1 本地回环
    AUTH_TOKEN = os.environ.get("WEBUI_TOKEN") or (
        webui_cfg.get("token") if webui_cfg else None
    )
    WEBUI_HOST = (
        os.environ.get("WEBUI_HOST")
        or (webui_cfg.get("host") if webui_cfg else None)
        or "127.0.0.1"
    )

    # Session 有效期：环境变量 WEBUI_SESSION_DAYS 优先于 config.yml，默认 7 天
    # 仅在鉴权启用时生效；非法值（<=0 或非数字）回退为 7 天
    session_days_raw = os.environ.get("WEBUI_SESSION_DAYS") or (
        webui_cfg.get("session_days") if webui_cfg else None
    )
    try:
        session_days = int(session_days_raw) if session_days_raw else 7
        if session_days <= 0:
            raise ValueError("must be > 0")
    except (TypeError, ValueError):
        log_warning(
            f"[WebUI] 无效的 WEBUI_SESSION_DAYS={session_days_raw!r}，回退为默认 7 天"
        )
        session_days = 7
    SESSION_DAYS = session_days
    app.permanent_session_lifetime = timedelta(days=SESSION_DAYS)

    # 安全检查：绑定 0.0.0.0 但未配置 token => 拒绝启动，防止公网裸奔
    if WEBUI_HOST in ("0.0.0.0", "::") and not AUTH_TOKEN:
        log_error(
            "[WebUI] 安全检查失败：WEBUI_HOST=0.0.0.0 但未配置 WEBUI_TOKEN，"
            "拒绝启动以避免未授权公网访问"
        )
        log_error(
            "[WebUI] 请设置 WEBUI_TOKEN 环境变量（或 config.yml 的 webui.token），"
            "或保持 WEBUI_HOST=127.0.0.1（默认，仅本地可访问）"
        )
        sys.exit(1)

    # 设置 Session 密钥（派生自 token；token 变更则历史 session 失效）
    if AUTH_TOKEN:
        app.secret_key = AUTH_TOKEN
        log_info(
            f"[WebUI] 鉴权已启用（Token 模式，Session 有效期 {SESSION_DAYS} 天，"
            "支持 Session 与 Bearer 两种方式）"
        )
    else:
        log_warning(
            "[WebUI] 未配置 WEBUI_TOKEN，WebUI 无鉴权（仅本地回环 127.0.0.1 可访问）"
        )

    log_info(
        f"正在启动 LiteCron Web 管理界面 (绑定: {WEBUI_HOST}:{port}, 调试模式: {debug_mode})"
    )
    log_info(f"APP_DIR: {PROJECT_ROOT}")

    app.run(host=WEBUI_HOST, port=port, debug=debug_mode, threaded=True)
