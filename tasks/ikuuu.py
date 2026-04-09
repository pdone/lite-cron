#!/usr/bin/env python3
"""
iKuuu 自动签到任务

功能：
- 自动登录 ikuuu.org
- 执行每日签到
- 获取剩余流量信息

环境变量：
- MY_EMAIL: 登录邮箱
- MY_PWD: 登录密码
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

import json
import re
import requests
import base64
from datetime import datetime

# 配置常量
LOGIN_URL = "https://ikuuu.org/auth/login"
CHECK_URL = "https://ikuuu.org/user/checkin"
INFO_URL = "https://ikuuu.org/user"

HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://ikuuu.org",
    "referer": "https://ikuuu.org/auth/login",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
}


def get_credentials() -> tuple:
    """
    从环境变量获取登录凭据

    Returns:
        tuple: (邮箱列表, 密码列表)
    """
    email = os.environ.get("MY_EMAIL")
    password = os.environ.get("MY_PWD")

    if not email or not password:
        log_error("错误: 未配置环境变量 MY_EMAIL 或 MY_PWD")
        return [], []

    return [email], [password]


def login(session: requests.Session, email: str, password: str) -> bool:
    """
    登录 ikuuu

    Args:
        session: requests 会话对象
        email: 邮箱
        password: 密码

         Returns:
         bool: 登录是否成功
    """
    try:
        log_info(f"[{email}] 正在登录...")
        data = {"email": email, "passwd": password}
        response = session.post(url=LOGIN_URL, headers=HEADERS, data=data, timeout=30)
        response.raise_for_status()

        result = response.json()
        msg = result.get("msg", "未知响应")
        log_info(f"{msg}")

        # 检查登录是否成功（根据响应判断）
        if "成功" in msg or "success" in msg.lower():
            return True
        return True  # 即使msg不包含成功字样，也尝试继续

    except requests.exceptions.RequestException as e:
        log_error(f"登录请求失败: {e}")
        return False
    except json.JSONDecodeError as e:
        log_error(f"登录响应解析失败: {e}")
        return False


def checkin(session: requests.Session) -> str:
    """
    执行签到

    Args:
        session: 已登录的 requests 会话

         Returns:
         str: 签到结果消息

    Raises:
        requests.exceptions.RequestException: 网络请求失败
        json.JSONDecodeError: JSON 解析失败
    """
    try:
        log_info("正在签到...")
        response = session.post(url=CHECK_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()

        result = response.json()
        msg = result.get("msg", "未知响应")
        log_success(f"{msg}")
        return msg

    except requests.exceptions.RequestException as e:
        error_msg = f"签到请求失败: {e}"
        log_error(f"{error_msg}")
        raise requests.exceptions.RequestException(error_msg)
    except json.JSONDecodeError as e:
        error_msg = f"签到响应解析失败: {e}"
        log_error(f"{error_msg}")
        raise json.JSONDecodeError(error_msg, e.doc, e.pos)


def get_traffic_info(session: requests.Session) -> str:
    """
    获取流量信息

    Args:
        session: 已登录的 requests 会话

    Returns:
        str: 流量信息文本
    """
    try:
        response = session.get(url=INFO_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()

        raw_html = response.text

        b64_pattern = r'var\s+originBody\s*=\s*"(.*?)"'
        b64_match = re.search(b64_pattern, raw_html)

        if b64_match:
            encoded_str = b64_match.group(1)

            # --- 第二步：Base64 解码 ---
            # 解码为 bytes，再根据页面通常的编码（UTF-8）转成字符串
            decoded_html = base64.b64decode(encoded_str).decode("utf-8")

            # --- 第三步：在解码后的 HTML 中匹配流量数据 ---
            # 结合之前写的正则
            data_pattern = r'<h4>剩余流量</h4>.*?<span class="counter">(.*?)</span>\s*(.*?)\s*</div>'
            data_match = re.search(data_pattern, decoded_html, re.S)

            if data_match:
                value = data_match.group(1)
                unit = data_match.group(2)
                log_info(f"剩余流量：{value}{unit}")
            else:
                # 如果格式有微调，可以尝试更宽泛的匹配
                log_warning("未能解析流量信息")
        else:
            log_warning("未能解析流量信息")
            return "流量信息获取失败"

    except requests.exceptions.RequestException as e:
        error_msg = f"流量信息获取失败: {e}"
        log_error(f"{error_msg}")
        return error_msg
    except re.error as e:
        error_msg = f"正则解析错误: {e}"
        log_error(f"{error_msg}")
        return error_msg


def process_account(email: str, password: str) -> bool:
    """
    处理单个账号的签到流程

    Args:
        email: 邮箱
        password: 密码

    Returns:
        bool: 是否成功
    """
    session = requests.Session()

    try:
        # 登录
        if not login(session, email, password):
            return False

        # 签到
        checkin_msg = checkin(session)

        # 获取流量信息
        traffic_info = get_traffic_info(session)

        return True

    except Exception as e:
        log_error(f"处理账号时发生错误: {e}")
        return False


def main() -> int:
    """
    主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    # start_time = datetime.now()
    # start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')

    log_info("iKuuu 签到任务开始")

    # 获取凭据
    emails, passwords = get_credentials()

    if not emails:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    # 处理每个账号
    success_count = 0
    fail_count = 0

    for email, password in zip(emails, passwords):
        if process_account(email, password):
            success_count += 1
        else:
            fail_count += 1

    # 记录结束时间
    # end_time = datetime.now()
    # end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    # duration = (end_time - start_time).total_seconds()

    # 汇总结果
    # print(f'✅ 任务完成: 成功 {success_count} 个, 失败 {fail_count} 个')

    if fail_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
