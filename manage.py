#!/usr/bin/env python3
"""
LiteCron 容器管理脚本（Python 实现 - 交互式版本）
提供交互式菜单和命令行两种使用方式

用法:
    python manage.py              # 启动交互式菜单
    python manage.py [命令]       # 直接执行命令（兼容原方式）
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============ 配置 ============
CONTAINER_NAME = "lite-cron"
COMPOSE_FILE = "compose.yml"
PROJECT_ROOT = Path(__file__).parent.absolute()

# 颜色定义
COLORS = {
    "RED": "\033[0;31m",
    "GREEN": "\033[0;32m",
    "YELLOW": "\033[1;33m",
    "BLUE": "\033[0;34m",
    "CYAN": "\033[0;36m",
    "WHITE": "\033[1;37m",
    "NC": "\033[0m",  # No Color
}

# 菜单配置 - 按功能分组
MENU_GROUPS = [
    ("容器相关", [
        ("start", "启动容器"),
        ("restart", "重启容器"),
        ("stop", "停止容器"),
        ("status", "查看容器状态"),
        ("logs", "监听容器日志"),
        ("shell", "进入容器 Shell"),
        ("build", "构建镜像"),
        ("update", "更新项目"),
    ]),
    ("任务相关", [
        ("run", "执行指定任务"),
        ("run-local", "本地执行任务"),
        ("tasklogs", "查看任务日志"),
        ("list", "查看定时任务列表"),
        ("clean", "清理日志"),
    ]),
    ("通用", [
        ("validate", "验证配置文件"),
        ("notify", "发送测试通知"),
        ("help", "显示帮助信息"),
        ("exit", "退出"),
    ]),
]

# 扁平化的菜单项列表（用于命令映射）
MENU_ITEMS = []
for group_name, items in MENU_GROUPS:
    MENU_ITEMS.extend(items)


# ============ 工具函数 ============
def clear_screen():
    """清屏"""
    os.system("cls" if os.name == "nt" else "clear")


def log_prefix() -> str:
    """获取带时间戳的前缀"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def print_info(message: str) -> None:
    """打印信息消息"""
    print(f"{COLORS['GREEN']}{log_prefix()} [INF] {message}{COLORS['NC']}")


def print_success(message: str) -> None:
    """打印成功消息"""
    print(f"{COLORS['GREEN']}{log_prefix()} [INF] {message}{COLORS['NC']}")


def print_warning(message: str) -> None:
    """打印警告消息"""
    print(f"{COLORS['YELLOW']}{log_prefix()} [WAR] {message}{COLORS['NC']}")


def print_error(message: str) -> None:
    """打印错误消息"""
    print(f"{COLORS['RED']}{log_prefix()} [ERR] {message}{COLORS['NC']}")


def print_header(title: str) -> None:
    """打印标题头"""
    width = 60
    print(f"{COLORS['GREEN']}{'-' * width}{COLORS['NC']}")
    print(f"{COLORS['GREEN']}{' ' * 24}{title}{COLORS['NC']}")
    print(f"{COLORS['GREEN']}{'-' * width}{COLORS['NC']}")


def print_menu() -> None:
    """打印主菜单 - 按功能分组水平排列显示"""
    clear_screen()
    print_header("LiteCron 管理")

    # 计算中文字符宽度（一个中文算2个字符宽度）
    def calc_width(text: str) -> int:
        width = 0
        for char in text:
            if ord(char) > 127:  # 非ASCII字符（中文、emoji等）
                width += 2
            else:
                width += 1
        return width

    def pad_to_width(text: str, target_width: int) -> str:
        current_width = calc_width(text)
        padding = target_width - current_width
        return text + " " * max(0, padding)

    # 计算每列的宽度
    col_widths = []
    for group_name, items in MENU_GROUPS:
        max_width = calc_width(f"[{group_name}]")  # 标题宽度
        for cmd_name, display_text in items:
            item_width = calc_width(f"[00] {display_text}")
            max_width = max(max_width, item_width)
        col_widths.append(max_width + 2)  # 加一些间距

    # 打印分组标题行
    header_line = "  "
    for i, (group_name, _) in enumerate(MENU_GROUPS):
        title = f"[{group_name}]"
        padded_title = pad_to_width(title, col_widths[i])
        header_line += f"{COLORS['YELLOW']}{padded_title}{COLORS['NC']}"
    print(header_line)

    # 找到最长的组的项数
    max_items = max(len(items) for _, items in MENU_GROUPS)

    # 计算每列的起始序号（垂直递增）
    col_start_indices = [1]
    for i in range(len(MENU_GROUPS) - 1):
        prev_count = len(MENU_GROUPS[i][1])
        col_start_indices.append(col_start_indices[-1] + prev_count)

    # 打印每行（水平排列，但序号垂直递增）
    for row in range(max_items):
        line = "  "
        for col, (_, items) in enumerate(MENU_GROUPS):
            if row < len(items):
                cmd_name, display_text = items[row]
                idx = col_start_indices[col] + row
                item_text = f"[{idx:2d}] {display_text}"
                padded_item = pad_to_width(item_text, col_widths[col])
                line += f"{COLORS['CYAN']}{padded_item}{COLORS['NC']}"
            else:
                # 该组没有这一项，填充空格
                line += " " * col_widths[col]
        print(line)

    print()  # 底部空行


def get_input(prompt: str = "请输入选项") -> str:
    """获取用户输入"""
    try:
        return input(f"{COLORS['CYAN']}{prompt}: {COLORS['NC']}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "exit"


def wait_for_key() -> None:
    """等待用户按 Enter 键继续，然后清屏返回主菜单"""
    try:
        input(f"\n{COLORS['CYAN']}按 Enter 键返回主菜单...{COLORS['NC']}")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        clear_screen()  # 确保无论如何都清屏


def confirm(message: str) -> bool:
    """确认操作"""
    try:
        response = input(f"{COLORS['YELLOW']}{message} (y/n): {COLORS['NC']}").strip().lower()
        return response in ('y', 'yes', '是', '确认')
    except (EOFError, KeyboardInterrupt):
        return False


def run_command(cmd: List[str], capture_output: bool = False, shell: bool = False) -> Tuple[int, str, str]:
    """运行 shell 命令"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            shell=shell,
            encoding="utf-8"
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception as e:
        return 1, "", str(e)


def check_compose_file() -> bool:
    """检查 docker-compose 文件是否存在"""
    compose_path = PROJECT_ROOT / COMPOSE_FILE
    if not compose_path.exists():
        print_error(f"未找到 {COMPOSE_FILE} 文件")
        return False
    return True


def is_running() -> bool:
    """检查容器是否正在运行"""
    returncode, stdout, _ = run_command(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True
    )
    if returncode == 0:
        return CONTAINER_NAME in stdout.splitlines()
    return False


def container_exists() -> bool:
    """检查容器是否存在（包括停止的）"""
    returncode, stdout, _ = run_command(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True
    )
    if returncode == 0:
        return CONTAINER_NAME in stdout.splitlines()
    return False


def load_config() -> Optional[Dict]:
    """加载配置文件"""
    config_path = PROJECT_ROOT / "config.yml"
    if not config_path.exists():
        return None
    
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


# ============ 命令实现 ============
def cmd_start() -> int:
    """启动容器"""
    print_info("启动 LiteCron 容器...")
    
    if not check_compose_file():
        return 1
    
    if is_running():
        print_warning("容器已经在运行中")
        return 0
    
    returncode, _, stderr = run_command(
        ["docker", "compose", "up", "-d"],
        capture_output=True
    )
    
    if returncode != 0:
        print_error(f"启动失败: {stderr}")
        return 1
    
    print_success("容器已启动")
    
    # 等待几秒让容器初始化
    import time
    time.sleep(2)
    return cmd_status()


def cmd_stop(confirm_stop: bool = True) -> int:
    """停止容器
    
    Args:
        confirm_stop: 是否需要确认，默认为 True。从 restart 调用时设为 False
    """
    print_info("停止 LiteCron 容器...")
    
    if not check_compose_file():
        return 1
    
    if not is_running():
        print_warning("容器未在运行")
        return 0
    
    if confirm_stop and not confirm("确定要停止容器吗？"):
        print_info("操作已取消")
        return 0
    
    returncode, _, stderr = run_command(
        ["docker", "compose", "down"],
        capture_output=True
    )
    
    if returncode != 0:
        print_error(f"停止失败: {stderr}")
        return 1
    
    print_success("容器已停止")
    return 0


def cmd_restart(confirm_restart: bool = True) -> int:
    """重启容器
    
    Args:
        confirm_restart: 是否需要确认，默认为 True。从 reload 调用时设为 False
    """
    print_info("重启 LiteCron 容器...")
    if confirm_restart and not confirm("确定要重启容器吗？"):
        print_info("操作已取消")
        return 0
    
    # 跳过确认，因为已经在这里确认过了
    cmd_stop(confirm_stop=False)
    import time
    time.sleep(1)
    return cmd_start()


def cmd_status() -> int:
    """查看容器状态"""
    print_info("容器状态:")
    
    if is_running():
        print_success("容器正在运行")
        print()
        
        # 显示容器详细信息
        run_command([
            "docker", "ps",
            "--filter", f"name={CONTAINER_NAME}",
            "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        ])
        print()
        
        print_info("最近日志:")
        returncode, stdout, _ = run_command(
            ["docker", "logs", "--tail", "10", CONTAINER_NAME],
            capture_output=True
        )
        if returncode == 0:
            print(stdout)
        return 0
    else:
        print_error("容器未运行")
        if container_exists():
            print_info("容器存在但未运行，使用 'start' 启动")
        else:
            print_info("容器不存在，使用 'start' 创建并启动")
        return 1


def cmd_logs() -> int:
    """查看容器日志"""
    if not is_running():
        print_error("容器未运行，无法查看日志")
        return 1

    print_info("查看容器日志 (按 Ctrl+C 退出)...")
    try:
        subprocess.run(["docker", "logs", "-f", "--tail", "50", CONTAINER_NAME])
    except KeyboardInterrupt:
        print()
    finally:
        # 确保退出后清屏
        clear_screen()
    return 0


def cmd_task_logs() -> int:
    """查看任务日志"""
    if not is_running():
        print_error("容器未运行")
        return 1

    print_info("可用的任务日志文件:")
    returncode, stdout, _ = run_command(
        ["docker", "exec", CONTAINER_NAME, "ls", "-lh", "/app/logs/"],
        capture_output=True
    )

    if returncode != 0:
        print_error("无法访问日志目录")
        return 1

    print(stdout)
    print()
    print_info("查看最新日志 (按 Ctrl+C 退出)...")

    try:
        subprocess.run([
            "docker", "exec", CONTAINER_NAME, "sh", "-c",
            "tail -f /app/logs/*.log"
        ])
    except KeyboardInterrupt:
        print()
    except Exception:
        print_warning("没有可读取的日志文件")
    finally:
        # 确保退出后清屏
        clear_screen()

    return 0


def cmd_shell() -> int:
    """进入容器 shell"""
    if not is_running():
        print_error("容器未运行")
        return 1

    print_info("进入容器 shell (输入 'exit' 退出)...")
    try:
        subprocess.run(["docker", "exec", "-it", CONTAINER_NAME, "/bin/bash"])
    finally:
        # 确保退出后清屏
        clear_screen()
    return 0


def cmd_reload() -> int:
    """重新加载配置（重启容器）"""
    print_info("重新加载配置...")
    if not confirm("确定要重启容器吗？"):
        print_info("操作已取消")
        return 0
    
    # 跳过确认，因为已经在这里确认过了
    result = cmd_restart(confirm_restart=False)
    if result == 0:
        print_success("配置已重新加载")
    return result


def cmd_list() -> int:
    """查看定时任务计划列表"""
    print_info("定时任务计划列表:")
    
    config = load_config()
    if config is None:
        print_error("未找到 config.yml 文件")
        return 1
    
    try:
        import yaml
        
        # 尝试导入 croniter
        try:
            from croniter import croniter
            CRONITER_AVAILABLE = True
        except ImportError:
            CRONITER_AVAILABLE = False
        
        tasks = config.get("tasks", [])
        if not tasks:
            print("未配置任何任务")
            return 0
        
        print(f"\n任务总数: {len(tasks)}\n")
        print("-" * 80)
        
        for i, task in enumerate(tasks, 1):
            name = task.get("name", "未命名")
            schedule = task.get("schedule", "无调度")
            script = task.get("script", "无脚本")
            enabled = task.get("enabled", True)
            description = task.get("description", "")
            
            status_icon = "[启用]" if enabled else "[禁用]"
            
            print(f"\n{i}. {status_icon} {name}")
            print(f"   调度: {schedule}")
            
            # 显示人类可读的说明
            readable = parse_cron(schedule)
            if readable != schedule:
                print(f"   说明: {readable}")
            
            # 显示下次执行时间
            if enabled and CRONITER_AVAILABLE:
                try:
                    itr = croniter(schedule, datetime.now())
                    next_run = itr.get_next(datetime)
                    print(f"   下次: {next_run.strftime('%Y-%m-%d %H:%M')}")
                except Exception:
                    pass
            
            print(f"   脚本: {script}")
            if description:
                print(f"   描述: {description}")
        
        print(f"\n{'-' * 80}")
        
        # 统计
        enabled_count = sum(1 for t in tasks if t.get("enabled", True))
        disabled_count = len(tasks) - enabled_count
        print(f"\n统计: {enabled_count} 个启用, {disabled_count} 个禁用")
        
        if not CRONITER_AVAILABLE:
            print("\n提示: 安装 croniter (pip install croniter) 可显示下次执行时间")
        
    except Exception as e:
        print_error(f"解析错误: {e}")
        return 1
    
    return 0


def parse_cron(cron_expr: str) -> str:
    """解析 cron 表达式为人类可读格式"""
    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr
    
    minute, hour, day, month, weekday = parts
    desc = []
    
    # 分钟
    if minute == "*":
        desc.append("每分钟")
    elif minute.startswith("*/"):
        desc.append(f"每{minute[2:]}分钟")
    else:
        desc.append(f"{minute}分")
    
    # 小时
    if hour == "*":
        if "每" in desc[0]:
            desc.append("每小时")
    elif hour.startswith("*/"):
        desc.append(f"每{hour[2:]}小时")
    else:
        desc.append(f"{hour}时")
    
    # 日期/月份/星期组合
    if day != "*" or month != "*" or weekday != "*":
        if day == "*" and month == "*" and weekday == "*":
            pass  # 每天
        elif weekday != "*":
            weekdays = {
                "0": "周日", "1": "周一", "2": "周二",
                "3": "周三", "4": "周四", "5": "周五", "6": "周六", "7": "周日"
            }
            if weekday in weekdays:
                desc.append(f"每{weekdays[weekday]}")
        else:
            desc.append(f"日期: {cron_expr}")
    
    return " ".join(desc) if len(desc) <= 3 else cron_expr


def cmd_validate() -> int:
    """验证配置文件"""
    print_info("验证配置文件...")
    
    config = load_config()
    if config is None:
        print_error("未找到 config.yml 文件")
        return 1
    
    print_success("YAML 格式有效")
    
    # 显示配置概览
    print()
    print_info("配置概览:")
    
    if "tasks" in config:
        tasks = config["tasks"]
        print(f"任务数量: {len(tasks)}")
        print()
        for task in tasks:
            status = "[启用]" if task.get("enabled", True) else "[禁用]"
            print(f"  - {task.get('name', '未命名')}: {task.get('schedule', '无调度')} ({status})")
    else:
        print("未定义任务列表")
    
    if "global_env" in config:
        print(f"\n全局环境变量: {len(config['global_env'])} 个")
    
    return 0


def cmd_build(custom_tag: Optional[str] = None, no_cache: bool = False) -> int:
    """构建 Docker 镜像"""
    print_info("构建 Docker 镜像...")
    
    if not check_compose_file():
        return 1
    
    image_name = "lite-cron"
    
    # 获取版本标签
    if custom_tag and custom_tag != "--no-cache":
        version_tag = custom_tag
        print_info(f"使用自定义标签: {version_tag}")
    else:
        version_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
        print_info(f"自动生成标签: {version_tag}")
    
    print_info(f"镜像名称: {image_name}")
    
    # 构建参数
    build_args = []
    if no_cache or custom_tag == "--no-cache":
        print_info("使用 --no-cache 模式（强制重新安装依赖）")
        build_args.append("--no-cache")
    else:
        print_info("使用缓存（依赖未变更时会跳过 apt-get/pip 安装）")
    
    # 构建镜像
    cmd = ["docker", "compose", "build"] + build_args
    returncode = subprocess.run(cmd).returncode
    
    if returncode != 0:
        print_error("镜像构建失败")
        return 1
    
    # 清理悬空镜像
    run_command(["docker", "image", "prune", "-f"], capture_output=True)
    
    # 添加额外的标签
    run_command(
        ["docker", "tag", f"{image_name}:latest", f"{image_name}:{version_tag}"],
        capture_output=True
    )
    
    print_success("镜像构建完成")
    print_info("可用标签:")
    print(f"  - {image_name}:latest")
    print(f"  - {image_name}:{version_tag}")
    
    return 0


def cmd_update() -> int:
    """更新（拉取最新代码并重启）"""
    print_info("更新 LiteCronPy...")
    
    if not confirm("确定要更新项目吗？这将停止容器并重新构建镜像。"):
        print_info("操作已取消")
        return 0
    
    # 跳过确认，因为已经在这里确认过了
    cmd_stop(confirm_stop=False)
    cmd_build()
    return cmd_start()


def cmd_clean() -> int:
    """清理日志"""
    print_info("清理日志文件...")
    
    logs_dir = PROJECT_ROOT / "logs"
    if logs_dir.exists():
        # 清理超过 7 天的日志文件
        returncode, _, _ = run_command(
            ["find", str(logs_dir), "-type", "f", "-name", "*.log", "-mtime", "+7", "-delete"],
            capture_output=True
        )
        # 清理任务失败时落盘的响应原文（logs/responses/<日期>/）
        run_command(
            ["find", str(logs_dir / "responses"), "-type", "f", "-mtime", "+7", "-delete"],
            capture_output=True
        )
        print_success("已清理超过 7 天的日志文件")
    
    # 清理容器内的日志
    if is_running():
        run_command([
            "docker", "exec", CONTAINER_NAME, "sh", "-c",
            "find /app/logs -type f -name '*.log' -mtime +7 -delete 2>/dev/null || true"
        ], capture_output=True)
        run_command([
            "docker", "exec", CONTAINER_NAME, "sh", "-c",
            "find /app/logs/responses -type f -mtime +7 -delete 2>/dev/null || true"
        ], capture_output=True)
        print_success("已清理容器内的旧日志")
    
    return 0


def select_task_interactive() -> Optional[str]:
    """交互式选择任务"""
    config = load_config()
    if not config or "tasks" not in config:
        print_error("未找到任务配置")
        return None
    
    tasks = config["tasks"]
    if not tasks:
        print_warning("没有配置任何任务")
        return None
    
    print(f"\n可用任务:")
    print("-" * 60)
    
    enabled_tasks = [t for t in tasks if t.get("enabled", True)]
    
    for i, task in enumerate(enabled_tasks, 1):
        name = task.get("name", "未命名")
        schedule = task.get("schedule", "无调度")
        print(f"  [{i:2d}] {name:<20} ({schedule})")
    
    print(f"  [ 0] 返回上级菜单")
    print()
    
    while True:
        choice = get_input("请选择任务编号")
        
        if choice == "0":
            return None
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(enabled_tasks):
                return enabled_tasks[idx].get("name")
            else:
                print_error("无效的选择")
        except ValueError:
            print_error("请输入数字")


def cmd_run(task_name: Optional[str] = None, run_all: bool = False, interactive: bool = True) -> int:
    """立即执行任务"""
    
    # 交互式选择任务
    if interactive and not task_name and not run_all:
        task_name = select_task_interactive()
        if task_name is None:
            return 0
    
    if not task_name and not run_all:
        print_error("请指定任务名称或使用 --all 运行所有任务")
        return 1
    
    if not is_running():
        print_error("容器未运行，请先启动容器")
        print_info("使用: start 命令启动")
        return 1
    
    config = load_config()
    if config is None:
        print_error("未找到 config.yml 文件")
        return 1
    
    try:
        if run_all:
            print_info("执行所有已启用任务...")
            
            tasks_to_run = [t for t in config.get("tasks", []) if t.get("enabled", True)]
            
            if not tasks_to_run:
                print("没有已启用的任务")
                return 1
            
            print(f"\n将执行 {len(tasks_to_run)} 个任务\n{'-' * 50}")
            
            failed_count = 0
            success_count = 0
            
            for task in tasks_to_run:
                task_name = task.get("name", "未命名")
                script = task.get("script", "")
                
                print(f"\n执行任务: {task_name}")
                
                # 设置环境变量
                env_vars = []
                if "env" in task:
                    for key, value in task["env"].items():
                        env_vars.append(f"{key}='{value}'")
                
                if "global_env" in config:
                    for key, value in config["global_env"].items():
                        env_vars.append(f"{key}='{value}'")
                
                env_args = " ".join([f"-e {var}" for var in env_vars])
                
                # 使用 task_wrapper.py 执行
                cmd = (
                    f"docker exec -e LITECRON_EXEC_MODE=cli {env_args} {CONTAINER_NAME} "
                    f"python3 /app/task_wrapper.py '{task_name}' '{script}'"
                )
                
                result = subprocess.run(cmd, shell=True)
                
                if result.returncode == 0:
                    print(f"{task_name} 执行成功")
                    success_count += 1
                else:
                    print(f"{task_name} 执行失败 (退出码: {result.returncode})")
                    failed_count += 1
            
            print(f"\n{'-' * 50}")
            print(f"\n执行完成: {success_count} 个成功, {failed_count} 个失败")
            
            return 1 if failed_count > 0 else 0
        
        else:
            # 运行单个任务
            print_info(f"立即执行任务: {task_name}")
            
            task = None
            task_name_lower = task_name.lower()
            for t in config.get("tasks", []):
                if t.get("name", "").lower() == task_name_lower:
                    task = t
                    break
            
            if not task:
                print_error(f"未找到任务: {task_name}")
                return 1
            
            if not task.get("enabled", True):
                print_warning(f"任务已禁用: {task_name}")
                return 1
            
            script = task.get("script", "")
            if not script:
                print_error(f"任务未配置脚本: {task_name}")
                return 1
            
            # 设置环境变量
            env_vars = []
            if "env" in task:
                for key, value in task["env"].items():
                    env_vars.append(f"{key}='{value}'")
            
            if "global_env" in config:
                for key, value in config["global_env"].items():
                    env_vars.append(f"{key}='{value}'")
            
            env_args = " ".join([f"-e {var}" for var in env_vars])
            
            # 使用 task_wrapper.py 执行
            cmd = (
                f"docker exec -e LITECRON_EXEC_MODE=cli {env_args} {CONTAINER_NAME} "
                f"python3 /app/task_wrapper.py '{task_name}' '{script}'"
            )
            
            result = subprocess.run(cmd, shell=True)
            
            if result.returncode == 0:
                print_success("任务执行完成")
                return 0
            else:
                print_error("任务执行失败")
                return 1
                
    except Exception as e:
        print_error(f"执行失败: {e}")
        return 1


def cmd_run_local(task_name: Optional[str] = None, run_all: bool = False, interactive: bool = True) -> int:
    """本地直接执行任务（不依赖 Docker）

    直接解析 config.yml，将 global_env 与 task.env 以原始键名注入本机进程环境，
    再用本机 Python 运行 tasks/xxx.py。绕开 Docker 与 task_wrapper 的前缀机制。
    """
    config = load_config()
    if config is None:
        print_error("未找到 config.yml 文件，请先 cp config.example.yml config.yml")
        return 1

    tasks = config.get("tasks", [])
    if not tasks:
        print_warning("没有配置任何任务")
        return 1

    # 交互式选择任务
    if interactive and not task_name and not run_all:
        task_name = select_task_interactive()
        if task_name is None:
            return 0

    if not task_name and not run_all:
        print_error("请指定任务名称或使用 --all 运行所有任务")
        return 1

    # 确定要执行的任务列表
    if run_all:
        targets = [t for t in tasks if t.get("enabled", True)]
        if not targets:
            print_warning("没有已启用的任务")
            return 1
    else:
        task_name_lower = task_name.lower()
        target = next(
            (t for t in tasks if t.get("name", "").lower() == task_name_lower),
            None,
        )
        if not target:
            print_error(f"未找到任务: {task_name}")
            return 1
        targets = [target]

    # 预先构建基础环境：本机环境 + global_env，日志落到项目 logs 目录
    base_env = os.environ.copy()
    for key, value in (config.get("global_env") or {}).items():
        base_env[str(key)] = str(value)
    base_env.setdefault("LOG_DIR", str(PROJECT_ROOT / "logs"))
    base_env.setdefault("LITECRON_EXEC_MODE", "cli")

    failed_count = 0
    success_count = 0

    if run_all:
        print_info(f"本地执行 {len(targets)} 个已启用任务...")
        print("-" * 50)

    for task in targets:
        name = task.get("name", "未命名")
        script = task.get("script", "")

        if not script:
            print_error(f"任务未配置脚本: {name}")
            failed_count += 1
            continue

        if not run_all and not task.get("enabled", True):
            print_warning(f"任务已禁用: {name}（本地仍将执行）")

        script_path = PROJECT_ROOT / script
        if not script_path.exists():
            print_error(f"脚本不存在: {script_path}")
            failed_count += 1
            continue

        # 逐任务注入 env（原始键名，无前缀）
        env = base_env.copy()
        for key, value in (task.get("env") or {}).items():
            env[str(key)] = str(value)
        # 注入任务名，使 logger 输出的日志行携带 [TASK:xxx] 标签
        env["LITECRON_TASK_NAME"] = name

        print_info(f"本地执行任务: {name} ({script})")
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                env=env,
                cwd=str(PROJECT_ROOT),
            )
            rc = result.returncode
        except Exception as e:
            print_error(f"执行异常: {e}")
            rc = 1

        if rc == 0:
            print_success(f"{name} 执行成功")
            success_count += 1
        else:
            print_error(f"{name} 执行失败 (退出码: {rc})")
            failed_count += 1

    if run_all:
        print("-" * 50)
        print(f"执行完成: {success_count} 个成功, {failed_count} 个失败")

    return 1 if failed_count > 0 else 0


def cmd_notify(message: Optional[str] = None, include_log: bool = False, log_lines: int = 15) -> int:
    """发送测试通知"""
    
    # 交互式输入消息
    if message is None:
        print(f"\n发送测试通知")
        message = get_input("请输入通知消息（默认: 测试消息）")
        if not message:
            message = "测试消息"
        
        include_log = confirm("是否附带最近日志？")
        if include_log:
            try:
                lines_input = get_input("日志行数（默认: 15）")
                if lines_input:
                    log_lines = int(lines_input)
            except ValueError:
                log_lines = 15
    
    log_content = ""
    
    if include_log:
        current_date = datetime.now().strftime("%Y%m%d")
        log_file = PROJECT_ROOT / "logs" / f"{current_date}.log"
        
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    log_content = "".join(lines[-log_lines:])
                print_info(f"已加载日志内容 (最后 {log_lines} 行)")
            except Exception as e:
                print_warning(f"无法读取日志文件: {e}")
        else:
            print_warning(f"日志文件不存在: {log_file}")
    
    print_info(f"发送测试通知: {message}")
    
    # 检查容器是否在运行
    if is_running():
        # 在容器中执行通知
        if log_content:
            cmd = [
                "docker", "exec", CONTAINER_NAME,
                "python3", "/app/notify.py", message,
                "--log-content", log_content,
                "--log-lines", str(log_lines)
            ]
        else:
            cmd = [
                "docker", "exec", CONTAINER_NAME,
                "python3", "/app/notify.py", message
            ]
        
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print_error("容器内通知执行失败")
            return 1
    else:
        # 在宿主机直接执行
        notify_path = PROJECT_ROOT / "src" / "notify.py"
        config_path = PROJECT_ROOT / "config.yml"
        
        if not notify_path.exists():
            print_error("未找到 notify.py 文件")
            return 1
        
        if not config_path.exists():
            print_error("未找到 config.yml 文件")
            return 1
        
        # 使用 Python 直接调用 notify 函数
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "src"))
            from notify import notify as notify_func
            
            notify_func("测试通知", message, log_content=log_content, log_lines=log_lines)
        except Exception as e:
            print_error(f"通知失败: {e}")
            return 1
    
    return 0


def cmd_help() -> int:
    """显示帮助信息"""
    help_text = """
LiteCron 容器管理脚本 (Python 实现)

用法:
    python manage.py              # 启动交互式菜单
    python manage.py [命令]       # 直接执行命令

容器相关:
  start              启动容器
  restart            重启容器
  stop               停止容器
  status             查看容器状态
  logs               监听容器日志
  shell              进入容器 shell
  build [tag]        构建 Docker 镜像
  update             更新项目

任务相关:
  run <任务名>       执行指定任务（容器内，需先启动容器）
  run --all          运行所有已启用任务（容器内）
  run-local <任务名> 本地直接执行任务（不依赖 Docker）
  run-local --all    本地执行所有已启用任务
  tasklogs           查看任务日志
  list               查看定时任务列表
  clean              清理日志

通用:
  validate           验证配置文件
  notify             发送测试通知
  help               显示帮助信息
  reload             重新加载配置

示例:
  python manage.py              # 交互式菜单
  python manage.py start        # 启动容器
  python manage.py list         # 查看定时任务
  python manage.py run ikuuu    # 执行 ikuuu 任务（容器内）
  python manage.py run-local ikuuu  # 本地直接测试 ikuuu 任务
  python manage.py notify       # 发送测试通知
"""
    print(help_text)
    return 0


# ============ 交互式菜单 ============
def run_interactive() -> int:
    """运行交互式菜单"""
    
    command_map = {
        # 垂直递增排列（从上到下，从左到右）
        # 容器相关（第1列，从上到下 1-8）
        "1": ("start", cmd_start),
        "2": ("restart", cmd_restart),
        "3": ("stop", cmd_stop),
        "4": ("status", cmd_status),
        "5": ("logs", cmd_logs),
        "6": ("shell", cmd_shell),
        "7": ("build", cmd_build),
        "8": ("update", cmd_update),
        # 任务相关（第2列，从上到下 9-13）
        "9": ("run", lambda: cmd_run(interactive=True)),
        "10": ("run-local", lambda: cmd_run_local(interactive=True)),
        "11": ("tasklogs", cmd_task_logs),
        "12": ("list", cmd_list),
        "13": ("clean", cmd_clean),
        # 通用（第3列，从上到下 14-17）
        "14": ("validate", cmd_validate),
        "15": ("notify", cmd_notify),
        "16": ("help", cmd_help),
        "17": ("exit", None),
    }
    
    last_choice = None  # 记住上一次执行的命令，供直接回车重跑

    while True:
        # 提示中显示回车默认重跑的上次命令
        prompt = "请选择操作"
        if last_choice:
            last_name = command_map[last_choice][0]
            prompt = f"请选择操作 (回车重跑 [{last_choice}] {last_name})"

        print_menu()
        choice = get_input(prompt)

        # 直接按 Enter：若之前执行过命令，则再次进入该命令；否则清屏重显菜单
        if not choice:
            if last_choice:
                choice = last_choice
            else:
                clear_screen()
                continue

        if choice in ("17", "exit", "quit", "q"):
            print(f"Exit")
            return 0

        if choice not in command_map:
            print_error("Invalid selection")
            wait_for_key()
            continue
        
        cmd_name, cmd_func = command_map[choice]
        
        if cmd_func is None:
            print(f"Exit")
            return 0
        
        # 记录本次执行的命令，供后续直接回车重跑
        last_choice = choice
        
        print()
        try:
            result = cmd_func()
        except KeyboardInterrupt:
            print(f"Canceled")
            result = 1
        except Exception as e:
            print_error(f"Error in execution: {e}")
            result = 1
        
        # 某些命令不需要等待（如 logs, shell）
        if cmd_name not in ("logs", "tasklogs", "shell"):
            wait_for_key()
        else:
            # 对于 logs, shell 等命令，退出后清屏
            clear_screen()

    return 0


# ============ 命令行模式 ============
def run_cli(command: str, args: List[str]) -> int:
    """运行命令行模式"""
    
    if command == "start":
        return cmd_start()
    
    elif command == "stop":
        return cmd_stop()
    
    elif command == "restart":
        return cmd_restart()
    
    elif command == "status":
        return cmd_status()
    
    elif command == "logs":
        return cmd_logs()
    
    elif command == "tasklogs":
        return cmd_task_logs()
    
    elif command == "list":
        return cmd_list()
    
    elif command == "shell":
        return cmd_shell()
    
    elif command == "reload":
        return cmd_reload()
    
    elif command == "validate":
        return cmd_validate()
    
    elif command == "build":
        # 解析 build 命令的参数
        build_parser = argparse.ArgumentParser(add_help=False)
        build_parser.add_argument("tag", nargs="?", help="自定义标签")
        build_parser.add_argument("--no-cache", action="store_true", help="强制重新安装依赖")
        build_args, _ = build_parser.parse_known_args(args)
        return cmd_build(build_args.tag, build_args.no_cache)
    
    elif command == "update":
        return cmd_update()
    
    elif command == "clean":
        return cmd_clean()
    
    elif command == "run":
        # 解析 run 命令的参数
        run_parser = argparse.ArgumentParser(add_help=False)
        run_parser.add_argument("task", nargs="?", help="任务名称")
        run_parser.add_argument("--all", action="store_true", dest="run_all", help="运行所有已启用任务")
        run_args, _ = run_parser.parse_known_args(args)
        return cmd_run(run_args.task, run_args.run_all, interactive=False)
    
    elif command == "run-local":
        # 解析 run-local 命令的参数
        run_local_parser = argparse.ArgumentParser(add_help=False)
        run_local_parser.add_argument("task", nargs="?", help="任务名称")
        run_local_parser.add_argument("--all", action="store_true", dest="run_all", help="运行所有已启用任务")
        run_local_args, _ = run_local_parser.parse_known_args(args)
        return cmd_run_local(run_local_args.task, run_local_args.run_all, interactive=False)
    
    elif command == "notify":
        # 解析 notify 命令的参数
        notify_parser = argparse.ArgumentParser(add_help=False)
        notify_parser.add_argument("message", nargs="?", help="通知消息")
        notify_parser.add_argument("-l", "--include-log", action="store_true", help="附带最近日志")
        notify_parser.add_argument("-n", "--log-lines", type=int, default=15, help="日志行数")
        notify_args, _ = notify_parser.parse_known_args(args)
        return cmd_notify(notify_args.message, notify_args.include_log, notify_args.log_lines)
    
    elif command in ("help", "--help", "-h"):
        return cmd_help()
    
    else:
        print_error(f"Unknown command: {command}")
        return cmd_help()


# ============ 主函数 ============
def main():
    """主函数入口"""
    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        # 命令行模式
        command = sys.argv[1]
        args = sys.argv[2:]
        return run_cli(command, args)
    else:
        # 交互式菜单模式
        try:
            return run_interactive()
        except KeyboardInterrupt:
            print(f"Exit")
            return 0


if __name__ == "__main__":
    sys.exit(main())
