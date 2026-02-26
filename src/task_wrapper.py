#!/usr/bin/env python3
"""
任务执行包装器（Python 版本）
用于包装实际任务脚本，捕获执行结果并发送通知
"""
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# 导入日志模块
sys.path.insert(0, "/app")
from logger import log_info, log_debug, log_error, log_warning


def setup_task_env(task_name: str) -> dict:
    """
    设置任务专属环境变量
    将 TaskName_KEY 格式转换为 KEY 格式

    Args:
        task_name: 任务名称

    Returns:
        dict: 需要设置的环境变量字典
    """
    task_env = {}
    prefix = f"{task_name}_"

    for key, value in os.environ.items():
        if key.startswith(prefix):
            # 移除前缀，得到原始变量名
            original_key = key[len(prefix) :]
            task_env[original_key] = value

    return task_env


def load_env_file(env_file="/app/.env"):
    """
    从 .env 文件加载环境变量

    Args:
        env_file: 环境变量文件路径
    """
    if not os.path.exists(env_file):
        log_warning(f"环境变量文件不存在: {env_file}")
        return

    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith("#"):
                    continue

                # 解析 export KEY="value" 格式
                if line.startswith("export "):
                    line = line[7:]  # 移除 'export '

                # 分割键值
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    # 移除可能的引号
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    # 处理转义的引号
                    value = value.replace('\\"', '"')

                    os.environ[key] = value
                    log_debug(f"从 .env 加载: {key}")
    except Exception as e:
        log_error(f"加载环境变量文件失败: {e}")


def main():
    if len(sys.argv) < 3:
        print("用法: task_wrapper.py <任务名称> <脚本路径> [参数...]", file=sys.stderr)
        sys.exit(1)

    task_name = sys.argv[1]
    script_path = sys.argv[2]
    script_args = sys.argv[3:]

    # 从 .env 文件加载环境变量
    load_env_file("/app/.env")

    # 判断执行来源
    exec_mode = os.environ.get("LITECRON_EXEC_MODE", "cron")
    if exec_mode == "webui":
        source_info = "[WebUI 手动执行]"
    elif exec_mode == "cli":
        source_info = "[CLI 手动执行]"
    else:
        source_info = "[定时任务]"

    # 记录开始时间
    start_time = datetime.now()
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

    log_info(f"任务: {task_name} {source_info}")

    # 设置任务专属环境变量（去除前缀）
    task_env = setup_task_env(task_name)
    for key, value in task_env.items():
        os.environ[key] = value
    if task_env:
        env_keys = ", ".join(task_env.keys())
        log_info(f"设置环境变量: {env_keys}")

    log_info(f"开始时间: {start_time_str}")

    # 执行实际脚本
    cmd = ["python3", script_path] + script_args

    # 使用 Popen 实时捕获输出，并同时输出到 stdout 和日志文件
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # 行缓冲
        cwd="/app",
    )

    # 实时读取并输出
    output_lines = []
    if process.stdout:
        for line in process.stdout:
            line = line.rstrip("\n")
            output_lines.append(line)
            # 输出到 stdout（Docker 日志）
            print(line, flush=True)

    # 等待进程结束
    exit_code = process.wait()

    # 记录结束时间
    end_time = datetime.now()
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    duration = (end_time - start_time).total_seconds()

    # 计算耗时
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    seconds = int(duration % 60)

    if hours > 0:
        duration_str = f"{hours}时{minutes}分{seconds}秒"
    elif minutes > 0:
        duration_str = f"{minutes}分{seconds}秒"
    else:
        duration_str = f"{seconds}秒"

    log_info(f"结束时间: {end_time_str} 总耗时: {duration_str}")

    # 发送通知
    if exit_code != 0:
        notify_path = Path("/app/notify.py")
        if notify_path.exists():
            log_warning(f"任务 {task_name} 失败，发送通知...")
            try:
                log_lines = int(os.environ.get("LOG_LINES", 15))
                task_log_content = (
                    "\n".join(output_lines[-log_lines:]) if output_lines else "无输出"
                )

                notify_cmd = [
                    "python3",
                    "/app/notify.py",
                    f"{task_name} 执行失败",
                    "详情见日志",
                    "--log-content",
                    task_log_content,
                    "--log-lines",
                    str(log_lines),
                ]
                subprocess.run(notify_cmd, capture_output=True)
            except Exception:
                pass  # 通知失败不阻断主流程

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
