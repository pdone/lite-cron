#!/usr/bin/env python3
"""
致美化（zhutix.com）自动签到任务

功能：
- 自动签到致美化网站
- 获取锋币奖励信息
- 获取连续签到天数

环境变量：
- ZHUTIX_COOKIE: 登录 Cookie（必需，格式: key1=value1; key2=value2）
- ZHUTIX_PROXY: 代理服务器地址（可选，如 http://127.0.0.1:7890）

依赖：
- curl_cffi: 用于模拟浏览器请求，绕过反爬虫
"""

import os
import sys
import re
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

BASE_URL = "https://zhutix.com"
MISSION_URL = f"{BASE_URL}/mission/"
USER_MISSION_API = f"{BASE_URL}/wp-json/b2/v1/userMission"
GET_USER_MISSION_API = f"{BASE_URL}/wp-json/b2/v1/getUserMission"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Origin": BASE_URL,
    "Referer": MISSION_URL,
    "Content-Type": "application/json",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def get_credentials() -> tuple:
    """
    从环境变量获取配置

    Returns:
        tuple: (cookie, proxy_url)
    """
    cookie = os.environ.get("ZHUTIX_COOKIE")
    proxy_url = os.environ.get("ZHUTIX_PROXY")

    if not cookie:
        log_error("错误: 未配置环境变量 ZHUTIX_COOKIE")
        return None, None

    return cookie, proxy_url


def parse_proxy(proxy_url: Optional[str]) -> Optional[str]:
    """
    解析代理地址

    Args:
        proxy_url: 代理地址，格式为 host:port 或 user:pass@host:port

    Returns:
        Optional[str]: 格式化后的代理地址，解析失败返回 None
    """
    if not proxy_url:
        return None

    try:
        if "://" not in proxy_url:
            proxy_url = f"http://{proxy_url}"

        parsed = urlparse(proxy_url)
        log_info(f"使用代理: {parsed.hostname}:{parsed.port}")
        return proxy_url

    except Exception as e:
        log_warning(f"代理解析失败: {e}")
        return None


def get_nonce(session, cookie: str, proxy: Optional[str] = None) -> Optional[str]:
    """
    从签到页面获取 nonce

    Args:
        session: requests 会话
        cookie: 登录 cookie
        proxy: 代理地址（可选）

    Returns:
        Optional[str]: nonce 值，获取失败返回 None
    """
    try:
        log_info("正在获取 nonce...")

        headers = HEADERS.copy()
        headers["Cookie"] = cookie

        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        from curl_cffi import requests as curl_requests
        response = curl_requests.get(
            MISSION_URL,
            headers=headers,
            impersonate="chrome110",
            timeout=15,
            proxies=proxies,
        )

        if response.status_code != 200:
            log_error(f"获取签到页面失败，状态码: {response.status_code}")
            return None

        html = response.text

        nonce_pattern = r'"nonce"\s*:\s*"([a-zA-Z0-9]+)"'
        match = re.search(nonce_pattern, html)
        if match:
            nonce = match.group(1)
            log_debug(f"获取到 nonce: {nonce[:8]}...")
            return nonce

        wp_nonce_pattern = r'name="b2_nonce"\s+value="([a-zA-Z0-9]+)"'
        match = re.search(wp_nonce_pattern, html)
        if match:
            nonce = match.group(1)
            log_debug(f"获取到 nonce: {nonce[:8]}...")
            return nonce

        script_pattern = r'b2_global\s*=\s*\{[^}]*"nonce"\s*:\s*"([a-zA-Z0-9]+)"'
        match = re.search(script_pattern, html)
        if match:
            nonce = match.group(1)
            log_debug(f"获取到 nonce: {nonce[:8]}...")
            return nonce

        log_warning("未能从页面提取 nonce，尝试直接调用 API")
        return None

    except ImportError:
        log_error("缺少依赖: curl_cffi，请执行 pip install curl_cffi")
        return None
    except Exception as e:
        log_error(f"获取 nonce 异常: {str(e)}")
        return None


def sign(cookie: str, proxy: Optional[str] = None) -> bool:
    """
    执行签到

    Args:
        cookie: 登录 cookie
        proxy: 代理地址（可选）

    Returns:
        bool: 签到是否成功
    """
    try:
        from curl_cffi import requests as curl_requests

        headers = HEADERS.copy()
        headers["Cookie"] = cookie

        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        nonce = get_nonce(curl_requests, cookie, proxy)
        if nonce:
            headers["X-WP-Nonce"] = nonce

        log_info("正在签到...")

        response = curl_requests.post(
            USER_MISSION_API,
            headers=headers,
            impersonate="chrome110",
            timeout=15,
            proxies=proxies,
            json={},
        )

        if response.status_code == 200:
            res_data = response.json()

            if isinstance(res_data, dict):
                if res_data.get("success") is False:
                    msg = res_data.get("msg", res_data.get("message", "签到失败"))
                    log_info(f"签到提示: {msg}")
                    if "已签到" in msg or "already" in msg.lower():
                        return True
                    return False

                if res_data.get("success") is True or "mission" in res_data:
                    mission_data = res_data.get("mission", res_data.get("data", {}))
                    if isinstance(mission_data, dict):
                        gain = mission_data.get("credit", mission_data.get("gain", 0))
                        current = mission_data.get("my_credit", mission_data.get("current", 0))
                        days = mission_data.get("always", mission_data.get("continuous", 0))
                        log_success(f"签到成功！获得 {gain} 锋币，当前共有 {current} 锋币，连续签到 {days} 天")
                    else:
                        log_success("签到成功！")
                    return True

            log_info(f"签到响应: {str(res_data)[:200]}")
            return True

        else:
            log_error(f"签到失败，服务器返回状态码: {response.status_code}")
            log_debug(f"响应内容: {response.text[:500]}")
            return False

    except ImportError:
        log_error("缺少依赖: curl_cffi，请执行 pip install curl_cffi")
        return False
    except Exception as e:
        log_error(f"签到异常: {str(e)}")
        return False


def get_user_mission(cookie: str, proxy: Optional[str] = None) -> dict:
    """
    获取用户签到信息

    Args:
        cookie: 登录 cookie
        proxy: 代理地址（可选）

    Returns:
        dict: 用户签到信息
    """
    try:
        from curl_cffi import requests as curl_requests

        headers = HEADERS.copy()
        headers["Cookie"] = cookie

        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        log_info("获取签到信息...")

        response = curl_requests.post(
            GET_USER_MISSION_API,
            headers=headers,
            impersonate="chrome110",
            timeout=15,
            proxies=proxies,
            json={},
        )

        if response.status_code == 200:
            res_data = response.json()
            return res_data if isinstance(res_data, dict) else {}
        return {}

    except Exception as e:
        log_warning(f"获取签到信息失败: {str(e)}")
        return {}


def main() -> int:
    """
    主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info("致美化签到任务开始")

    cookie, proxy_url = get_credentials()

    if not cookie:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    proxy = parse_proxy(proxy_url) if proxy_url else None

    success = sign(cookie, proxy)

    if success:
        log_success("任务完成")
    else:
        log_error("任务失败")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
