#!/usr/bin/env python3
"""
NodeSeek 论坛自动签到任务

功能：
- 自动签到 NodeSeek 论坛
- 获取鸡腿奖励信息
- 支持随机/固定鸡腿模式

环境变量：
- NODESEEK_COOKIE: 登录 cookie（必需）
- NODESEEK_RANDOM: 是否随机鸡腿，true/false（可选，默认 true）

依赖：
- curl_cffi: 用于模拟浏览器请求，绕过反爬虫
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

from datetime import datetime

# 配置常量
BASE_URL = "https://www.nodeseek.com"
SIGN_URL = f"{BASE_URL}/api/attendance"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Origin": "https://www.nodeseek.com",
    "Referer": "https://www.nodeseek.com/board",
    "Content-Type": "application/json",
}


def get_credentials() -> tuple:
    """
    从环境变量获取配置

    Returns:
        tuple: (cookie, random_mode)
    """
    cookie = os.environ.get("NODESEEK_COOKIE")
    random_mode = os.environ.get("NODESEEK_RANDOM", "true").lower()

    if not cookie:
        log_error("错误: 未配置环境变量 NODESEEK_COOKIE")
        return None, None

    # 验证 random_mode 值
    if random_mode not in ("true", "false"):
        log_warning(f"无效的 NODESEEK_RANDOM 值: {random_mode}，使用默认值 true")
        random_mode = "true"

    return cookie, random_mode


def sign(cookie: str, random_mode: str) -> bool:
    """
    执行签到

    Args:
        cookie: 登录 cookie
        random_mode: 是否随机鸡腿，'true' 或 'false'

    Returns:
        bool: 签到是否成功
    """
    try:
        # 导入 curl_cffi（延迟导入，避免未安装时影响其他任务）
        from curl_cffi import requests as curl_requests

        # 构建请求头
        headers = HEADERS.copy()
        headers["Cookie"] = cookie

        # 构建 URL
        url = f"{SIGN_URL}?random={random_mode}"

        log_info(f"正在签到... (随机模式: {random_mode})")

        # 使用 curl_cffi 模拟 Chrome 浏览器
        response = curl_requests.post(
            url, headers=headers, impersonate="chrome110", timeout=15
        )

        if response.status_code == 200:
            res_data = response.json()
            message = res_data.get("message", "")
            success = res_data.get("success", False)

            if success:
                gain = res_data.get("gain", 0)
                current = res_data.get("current", 0)
                log_success(f"签到成功！获得 {gain} 鸡腿，当前共有 {current} 鸡腿")
                return True
            else:
                log_info(f"签到提示: {message}")
                # 已签到也算成功
                if "已签到" in message or "already" in message.lower():
                    return True
                return False
        else:
            log_error(f"签到失败，服务器返回状态码: {response.status_code}")
            return False

    except ImportError:
        log_error("缺少依赖: curl_cffi，请执行 pip install curl_cffi")
        return False
    except Exception as e:
        log_error(f"签到异常: {str(e)}")
        return False


def main() -> int:
    """
    主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info("NodeSeek 签到任务开始")

    # 获取配置
    cookie, random_mode = get_credentials()

    if not cookie:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    # 执行签到
    success = sign(cookie, random_mode)

    # 汇总结果
    if success:
        log_success("任务完成")
    else:
        log_error("任务失败")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
