#!/usr/bin/env python3
"""
iKuuu 自动签到任务

功能：
- 自动登录 ikuuu.win Cookie 和账号密码两种方式）
- 执行每日签到
- 获取剩余流量信息

环境变量：
- IKUUU_COOKIE: 登录 Cookie（优先使用，格式: key1=value1; key2=value2）
- IKUUU_EMAIL: 登录邮箱（Cookie 失效时回退使用）
- IKUUU_PWD: 登录密码（Cookie 失效时回退使用）
- IKUUU_DOMAIN: 站点域名（可选，未配置时使用脚本内置默认域名 ikuuu.win）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import (
    log_info,
    log_success,
    log_error,
    log_warning,
    log_debug,
    log_response_detail,
)

import json
import re
import requests
import base64
from datetime import datetime

# 配置常量
# 默认域名（ikuuu 官方域名经常变化，可通过环境变量 IKUUU_DOMAIN 覆盖）
DEFAULT_DOMAIN = "ikuuu.win"

# 从环境变量获取域名，未配置则使用默认域名
DOMAIN = os.environ.get("IKUUU_DOMAIN") or DEFAULT_DOMAIN

LOGIN_URL = f"https://{DOMAIN}/auth/login"
CHECK_URL = f"https://{DOMAIN}/user/checkin"
INFO_URL = f"https://{DOMAIN}/user"

HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": f"https://{DOMAIN}",
    "referer": f"https://{DOMAIN}/auth/login",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
}


def get_credentials() -> tuple:
    """
    从环境变量获取登录凭据

    Returns:
        tuple: (cookie列表, 邮箱列表, 密码列表)
    """
    cookie = os.environ.get("IKUUU_COOKIE")
    email = os.environ.get("IKUUU_EMAIL")
    password = os.environ.get("IKUUU_PWD")

    cookies = [cookie] if cookie else []
    emails = [email] if email else []
    passwords = [password] if password else []

    if not cookies and not (emails and passwords):
        log_error("错误: 请配置环境变量 IKUUU_COOKIE，或同时配置 IKUUU_EMAIL 和 IKUUU_PWD")
        return [], [], []

    return cookies, emails, passwords


def verify_cookie(session: requests.Session, cookie: str) -> bool:
    """
    验证 Cookie 是否有效

    Args:
        session: requests 会话对象
        cookie: 登录 Cookie

    Returns:
        bool: Cookie 是否有效
    """
    try:
        log_info("正在验证 Cookie 有效性...")
        headers = HEADERS.copy()
        headers["Cookie"] = cookie

        response = session.get(url=INFO_URL, headers=headers, timeout=30, allow_redirects=False)

        if response.status_code == 200:
            if "登录" in response.text and "auth/login" in response.text:
                log_warning("Cookie 已失效，需要重新登录")
                return False
            log_success("Cookie 验证通过")
            return True
        elif response.status_code in (301, 302):
            redirect_url = response.headers.get("Location", "")
            if "auth/login" in redirect_url:
                log_warning("Cookie 已失效，跳转到登录页")
                return False
            log_success("Cookie 验证通过")
            return True
        else:
            log_warning(f"Cookie 验证返回状态码: {response.status_code}，尝试继续使用")
            return True

    except requests.exceptions.RequestException as e:
        log_warning(f"Cookie 验证请求失败: {e}，尝试继续使用")
        return True


def login_with_cookie(session: requests.Session, cookie: str) -> bool:
    """
    使用 Cookie 登录

    Args:
        session: requests 会话对象
        cookie: 登录 Cookie

    Returns:
        bool: 登录是否成功
    """
    try:
        log_info("使用 Cookie 方式登录...")
        headers = HEADERS.copy()
        headers["Cookie"] = cookie
        session.headers.update(headers)

        if verify_cookie(session, cookie):
            return True
        return False

    except Exception as e:
        log_error(f"Cookie 登录异常: {e}")
        return False


def login(session: requests.Session, email: str, password: str) -> bool:
    """
    使用账号密码登录 ikuuu

    Args:
        session: requests 会话对象
        email: 邮箱
        password: 密码

         Returns:
         bool: 登录是否成功
    """
    try:
        log_info(f"[{email}] 使用账号密码登录...")
        data = {"email": email, "passwd": password}
        response = session.post(url=LOGIN_URL, headers=HEADERS, data=data, timeout=30)
        response.raise_for_status()

        result = response.json()
        msg = result.get("msg", "未知响应")
        log_info(f"{msg}")

        if "成功" in msg or "success" in msg.lower():
            log_success("账号密码登录成功")
            return True
        return True

    except requests.exceptions.RequestException as e:
        log_error(f"登录请求失败: {e}")
        log_response_detail(getattr(e, "response", None))
        return False
    except json.JSONDecodeError as e:
        log_error(f"登录响应解析失败: {e}")
        log_response_detail(response)
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
        log_response_detail(getattr(e, "response", None))
        raise requests.exceptions.RequestException(error_msg)
    except json.JSONDecodeError as e:
        error_msg = f"签到响应解析失败: {e}"
        log_error(f"{error_msg}")
        log_response_detail(response)
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
                log_response_detail(response)
        else:
            log_warning("未能解析流量信息")
            log_response_detail(response)
            return "流量信息获取失败"

    except requests.exceptions.RequestException as e:
        error_msg = f"流量信息获取失败: {e}"
        log_error(f"{error_msg}")
        log_response_detail(getattr(e, "response", None))
        return error_msg
    except re.error as e:
        error_msg = f"正则解析错误: {e}"
        log_error(f"{error_msg}")
        return error_msg


def process_account(cookie: str = None, email: str = None, password: str = None) -> bool:
    """
    处理单个账号的签到流程，优先使用 Cookie 登录，失败时回退到账号密码

    Args:
        cookie: 登录 Cookie（可选）
        email: 邮箱（可选，Cookie 失效时回退使用）
        password: 密码（可选，Cookie 失效时回退使用）

    Returns:
        bool: 是否成功
    """
    session = requests.Session()
    account_label = email if email else "cookie账号"

    try:
        logged_in = False

        if cookie:
            log_info(f"[{account_label}] 尝试使用 Cookie 登录...")
            if login_with_cookie(session, cookie):
                try:
                    checkin(session)
                    get_traffic_info(session)
                    log_success(f"[{account_label}] Cookie 登录并签到成功")
                    return True
                except Exception as e:
                    log_warning(f"[{account_label}] Cookie 签到失败: {e}，尝试回退到账号密码登录")
                    session = requests.Session()

        if email and password:
            log_info(f"[{account_label}] 使用账号密码登录...")
            if login(session, email, password):
                checkin(session)
                get_traffic_info(session)
                log_success(f"[{account_label}] 账号密码登录并签到成功")
                return True
            else:
                log_error(f"[{account_label}] 账号密码登录失败")
                return False

        log_error(f"[{account_label}] 没有可用的登录方式")
        return False

    except Exception as e:
        log_error(f"[{account_label}] 处理账号时发生错误: {e}")
        return False


def main() -> int:
    """
    主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info(f"iKuuu 签到任务开始 (域名: {DOMAIN})")

    cookies, emails, passwords = get_credentials()

    if not cookies and not emails:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    success_count = 0
    fail_count = 0

    max_accounts = max(len(cookies), len(emails))

    for i in range(max_accounts):
        cookie = cookies[i] if i < len(cookies) else None
        email = emails[i] if i < len(emails) else None
        password = passwords[i] if i < len(passwords) else None

        if process_account(cookie=cookie, email=email, password=password):
            success_count += 1
        else:
            fail_count += 1

    log_info(f"任务完成: 成功 {success_count} 个, 失败 {fail_count} 个")

    if fail_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
