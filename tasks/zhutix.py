#!/usr/bin/env python3
"""
致美化（zhutix.com）自动签到任务

功能：
- 自动签到致美化网站
- 获取锋币奖励信息
- 获取连续签到天数

环境变量：
- ZHUTIX_COOKIE: 登录 Cookie（必需，格式: key1=value1; key2=value2）
  注意：必须包含名为 b2_token 的字段，否则接口返回 403。建议在浏览器
  登录后从开发者工具复制「全部 Cookie」（含 b2_token），而非仅复制
  wordpress_logged_in 等字段。
- ZHUTIX_PROXY: 代理服务器地址（可选，如 http://127.0.0.1:7890）

依赖：
- curl_cffi: 用于模拟浏览器请求，绕过反爬虫
"""

import os
import sys
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

BASE_URL = "https://zhutix.com"
MISSION_URL = f"{BASE_URL}/mission/"
USER_MISSION_API = f"{BASE_URL}/wp-json/b2/v1/userMission"

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


def extract_b2_token(cookie: str) -> Optional[str]:
    """
    从 Cookie 字符串中提取 b2_token

    致美化 REST API 使用 b2_token 进行鉴权：前端会读取名为 b2_token 的
    Cookie，并将其作为 Bearer Token 放入 Authorization 请求头。页面中已不再
    提供 X-WP-Nonce，因此签到请求必须携带此 Bearer 令牌，否则返回 403。

    Args:
        cookie: 登录 Cookie 字符串（格式: key1=value1; key2=value2）

    Returns:
        Optional[str]: b2_token 值，未找到返回 None
    """
    if not cookie:
        return None

    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("b2_token="):
            token = part[len("b2_token="):].strip()
            return token or None

    return None


def build_auth_headers(cookie: str) -> dict:
    """
    构造请求头，自动附加 Bearer 鉴权令牌

    Args:
        cookie: 登录 Cookie 字符串

    Returns:
        dict: 包含 Cookie 及（若有）Authorization 的请求头
    """
    headers = HEADERS.copy()
    headers["Cookie"] = cookie

    token = extract_b2_token(cookie)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        log_warning("未从 Cookie 中检测到 b2_token，签到可能返回 403，请确认 Cookie 完整（需包含 b2_token）")

    return headers


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

        headers = build_auth_headers(cookie)

        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        log_info("正在签到...")

        response = curl_requests.post(
            USER_MISSION_API,
            headers=headers,
            impersonate="chrome110",
            timeout=15,
            proxies=proxies,
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

            # 响应不是预期的 dict 结构，可能是 B2 主题返回的简单状态码
            # 致美化 userMission 接口状态码含义：
            #   1 → 未到签到时间（签到周期未重置）
            #   3 → 今日已签到
            # 这两种状态都不算失败，只是无法获得新的签到奖励
            if res_data == 3:
                log_info("今日已签到，跳过")
                return True
            if res_data == 1:
                log_warning("未到签到时间（签到周期尚未重置），跳过")
                return True

            # 其他未知响应，按失败处理以便及时发现异常
            log_warning(f"签到响应格式异常，可能未真正签到: {str(res_data)[:200]}")
            return False

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

    # 直接调用签到接口，sign() 内部会处理已签到(3)/未到时间(1)等状态
    success = sign(cookie, proxy)

    if success:
        log_success("任务完成")
    else:
        log_error("任务失败")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
