#!/usr/bin/env python3
"""
生成环境变量配置文件
从 config.yml 读取任务配置，生成 /app/.env 文件
"""
import os
import sys
import yaml

# 导入日志模块
sys.path.insert(0, os.path.dirname(__file__))
from logger import log_info, log_success, log_error, log_warning


def generate_env(config_path='config.yml', env_file='/app/.env'):
    """
    根据 config.yml 生成环境变量文件

    Args:
        config_path: 配置文件路径
        env_file: 输出的环境变量文件路径

    Returns:
        bool: 是否成功
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        log_error(f"错误: 未找到配置文件 {config_path}")
        return False
    except yaml.YAMLError as e:
        log_error(f"错误: 解析 YAML 失败: {e}")
        return False

    with open(env_file, 'w', encoding='utf-8') as f:
        f.write("# 自动生成的环境变量文件\n")
        f.write(f"# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("# 不要手动编辑此文件\n\n")

        # 全局环境变量
        if 'global_env' in config:
            f.write("# 全局环境变量\n")
            for key, value in config['global_env'].items():
                escaped_value = str(value).replace('"', '\\"')
                f.write(f'export {key}="{escaped_value}"\n')
            f.write("\n")

        # 任务专属环境变量（添加任务名前缀避免冲突）
        if 'tasks' in config and config['tasks']:
            f.write("# 任务专属环境变量\n")
            for task in config['tasks']:
                task_name = task.get('name', '')
                if not task_name:
                    continue

                is_enabled = task.get('enabled', True)
                status = "启用" if is_enabled else "禁用"
                f.write(f"# 任务: {task_name} ({status})\n")

                if 'env' in task:
                    for key, value in task['env'].items():
                        # 格式：TaskName_KEY=value
                        env_key = f"{task_name}_{key}"
                        escaped_value = str(value).replace('"', '\\"')
                        f.write(f'export {env_key}="{escaped_value}"\n')

                f.write("\n")

    log_success(f"[WebUI] 环境变量文件已生成: {env_file}")
    return True


def main():
    """主函数"""
    # 默认路径
    config_path = 'config.yml'
    env_file = '/app/.env'

    # 支持命令行参数
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    if len(sys.argv) > 2:
        env_file = sys.argv[2]

    success = generate_env(config_path, env_file)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
