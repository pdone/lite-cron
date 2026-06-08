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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    Response,
    send_from_directory,
)

# 导入日志模块
from logger import log_info, log_success, log_error, log_warning

# 项目路径配置 - 文件位于 /app/ 下
PROJECT_ROOT = Path(__file__).parent.absolute()
CONFIG_FILE = PROJECT_ROOT / "config.yml"
LOGS_DIR = PROJECT_ROOT / "logs"
TASKS_DIR = PROJECT_ROOT / "tasks"
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
            return {"running": False, "exists": True, "message": "容器已停止"}

        return {"running": False, "exists": False, "message": "容器不存在"}
    except Exception as e:
        return {"running": False, "error": str(e), "message": "无法获取状态"}


def parse_cron(cron_expr: str) -> str:
    """解析 cron 表达式为人类可读格式"""
    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr

    minute, hour, day, month, weekday = parts
    desc = []

    if minute == "*":
        desc.append("每分钟")
    elif minute.startswith("*/"):
        desc.append(f"每{minute[2:]}分钟")
    else:
        desc.append(f"{minute}分")

    if hour == "*":
        if "每" in desc[0]:
            desc.append("每小时")
    elif hour.startswith("*/"):
        desc.append(f"每{hour[2:]}小时")
    else:
        desc.append(f"{hour}时")

    if weekday != "*":
        weekdays = {
            "0": "周日",
            "1": "周一",
            "2": "周二",
            "3": "周三",
            "4": "周四",
            "5": "周五",
            "6": "周六",
            "7": "周日",
        }
        if weekday in weekdays:
            desc.append(f"每{weekdays[weekday]}")

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


@app.route("/")
def index():
    """首页"""
    return render_template("index.html", app_version=APP_VERSION)


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
        yield json.dumps(
            {"status": "started", "message": f"开始执行任务: {task_name}"},
            ensure_ascii=False,
        ) + "\n"

        try:
            config = load_config()
            if not config or "tasks" not in config:
                yield json.dumps(
                    {"status": "error", "message": "配置未找到"}, ensure_ascii=False
                ) + "\n"
                return

            task = None
            for t in config["tasks"]:
                if t.get("name", "").lower() == task_name.lower():
                    task = t
                    break

            if not task:
                yield json.dumps(
                    {"status": "error", "message": f"未找到任务: {task_name}"},
                    ensure_ascii=False,
                ) + "\n"
                return

            if not task.get("enabled", True):
                yield json.dumps(
                    {"status": "error", "message": "任务已禁用"}, ensure_ascii=False
                ) + "\n"
                return

            script_path = task.get("script", "")
            if not script_path:
                yield json.dumps(
                    {"status": "error", "message": "任务未配置脚本"}, ensure_ascii=False
                ) + "\n"
                return

            full_script_path = PROJECT_ROOT / script_path
            if not full_script_path.exists():
                yield json.dumps(
                    {"status": "error", "message": f"脚本文件不存在: {script_path}"},
                    ensure_ascii=False,
                ) + "\n"
                return

            task_env = os.environ.copy()
            task_env["LITECRON_EXEC_MODE"] = "webui"

            if "env" in task:
                for key, value in task["env"].items():
                    task_env[key] = str(value)
            if "global_env" in config:
                for key, value in config["global_env"].items():
                    task_env[key] = str(value)

            # 使用 Python 版本的包装器
            wrapper_py_path = PROJECT_ROOT / "task_wrapper.py"
            if wrapper_py_path.exists():
                cmd = ["python3", str(wrapper_py_path), task_name, str(full_script_path)]
            else:
                cmd = ["python3", str(full_script_path)]

            yield json.dumps(
                {"status": "running", "output": f"执行命令: {' '.join(cmd)}"},
                ensure_ascii=False,
            ) + "\n"

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
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

            yield json.dumps(
                {
                    "status": "completed",
                    "success": success,
                    "returncode": process.returncode,
                    "message": (
                        "✅ 任务执行成功，日志已记录到 /app/logs/"
                        if success
                        else "❌ 任务执行失败，日志已记录到 /app/logs/"
                    ),
                },
                ensure_ascii=False,
            ) + "\n"

        except Exception as e:
            yield json.dumps(
                {"status": "error", "success": False, "message": f"执行出错: {str(e)}"},
                ensure_ascii=False,
            ) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@app.route("/api/tasks/<task_name>/toggle", methods=["POST"])
def api_toggle_task(task_name: str):
    """切换任务状态"""
    config = load_config()
    if not config or "tasks" not in config:
        return jsonify({"success": False, "message": "配置未找到"})

    task_found = False
    for task in config["tasks"]:
        if task.get("name", "").lower() == task_name.lower():
            task["enabled"] = not task.get("enabled", True)
            new_status = task["enabled"]
            task_found = True
            break

    if not task_found:
        return jsonify({"success": False, "message": "任务未找到"})

    if save_config(config):
        return jsonify(
            {
                "success": True,
                "enabled": new_status,
                "message": f"任务已{'启用' if new_status else '禁用'}",
            }
        )
    else:
        return jsonify({"success": False, "message": "保存配置失败"})


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
        return jsonify({"error": "非法路径"}), 403

    if not log_file.exists():
        return jsonify({"content": "", "lines": 0})

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = content.split("\n")

        limit = request.args.get("limit", type=int)
        if limit and len(lines) > limit:
            lines = lines[-limit:]
            content = "\n".join(lines)

        return jsonify({"content": content, "lines": len(lines), "filename": filename})
    except Exception as e:
        return jsonify({"error": f"读取日志失败: {str(e)}"}), 500


@app.route("/api/reload", methods=["POST"])
def api_reload():
    """重载配置文件并刷新 cron 调度"""
    try:
        # 1. 重新生成环境变量
        make_env_path = PROJECT_ROOT / "make_env.py"
        if make_env_path.exists():
            result = subprocess.run(
                ["python3", str(make_env_path)],
                capture_output=True,
                text=True,
                cwd=str(PROJECT_ROOT),
            )
            if result.returncode != 0:
                return jsonify({
                    "success": False,
                    "message": f"生成环境变量失败: {result.stderr}"
                }), 500

        # 2. 重新生成 crontab 文件
        cron_file = "/tmp/crontab"
        make_cron_path = PROJECT_ROOT / "make_cron.py"

        if not make_cron_path.exists():
            return jsonify({
                "success": False,
                "message": "未找到 make_cron.py"
            }), 500

        # 清空并重建 crontab 文件头
        with open(cron_file, "w", encoding="utf-8") as f:
            f.write("# 自动生成的crontab - 由 WebUI 重载\n")
            f.write("# 不要手动编辑此文件\n\n")
            f.write('# 禁用邮件通知，避免输出被邮件系统捕获\n')
            f.write('MAILTO=""\n\n')

            # 写入全局环境变量
            f.write("# 全局环境变量\n")
            f.write(f"APP_ENV={os.environ.get('APP_ENV', 'production')}\n")
            f.write(f"LOG_LEVEL={os.environ.get('LOG_LEVEL', 'INFO')}\n")
            f.write("PYTHONPATH=/app\n\n")
            f.write("PATH=/usr/local/bin:/usr/bin:/bin\n\n")

        # 执行 make_cron.py 生成任务
        result = subprocess.run(
            ["python3", str(make_cron_path), "config.yml", cron_file],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

        if result.returncode != 0:
            return jsonify({
                "success": False,
                "message": f"生成 crontab 失败: {result.stderr}"
            }), 500

        # 3. 加载新的 crontab
        result = subprocess.run(
            ["crontab", cron_file],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return jsonify({
                "success": False,
                "message": f"加载 crontab 失败: {result.stderr}"
            }), 500

        log_success("配置重载完成")
        return jsonify({
            "success": True,
            "message": "配置重载完成，cron 调度已更新"
        })

    except Exception as e:
        log_error(f"重载配置失败: {e}")
        return jsonify({
            "success": False,
            "message": f"重载失败: {str(e)}"
        }), 500


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

        return jsonify(
            {
                "success": True,
                "message": f"✅ 已清理 {cleaned_count} 个超过7天的日志文件",
                "cleaned": cleaned_count,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"清理失败: {str(e)}"}), 500


if __name__ == "__main__":
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 从环境变量读取端口，默认 5000
    port = int(os.environ.get("WEBUI_PORT", 5000))

    # 从配置文件读取 debug 设置，默认 False
    config = load_config()
    debug_mode = False
    if config and "webui" in config:
        debug_mode = config["webui"].get("debug", False)

    log_info(f"正在启动 LiteCron Web 管理界面 (端口: {port}, 调试模式: {debug_mode})")

    app.run(host="0.0.0.0", port=port, debug=debug_mode, threaded=True)
