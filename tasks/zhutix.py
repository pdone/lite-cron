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
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import (
    log_info,
    log_success,
    log_error,
    log_warning,
    log_debug,
    log_response_detail,
)

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


def _to_int(value, default: int = 0) -> int:
    """
    安全地将（可能为字符串的）值转换为整数

    接口返回的 credit / always / my_credit 均为字符串（如 "2"、"13"），
    统一转换为 int 以便日志展示与后续处理。

    Args:
        value: 待转换的值（可能为 str / int / None）
        default: 转换失败时的默认值

    Returns:
        int: 转换后的整数
    """
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _is_today(date_str: str) -> bool:
    """
    判断日期字符串是否为今天

    date 字段格式示例："2026-07-16 10:26:44"

    Args:
        date_str: 日期时间字符串

    Returns:
        bool: 是否为今天
    """
    if not date_str:
        return False
    try:
        date_part = str(date_str).split(" ", 1)[0]
        return datetime.strptime(date_part, "%Y-%m-%d").date() == datetime.now().date()
    except ValueError:
        return False


def get_user_mission(cookie: str, proxy: Optional[str] = None) -> Optional[dict]:
    """
    调用 getUserMission 接口获取当前签到状态

    该接口为 POST 请求（非 GET），需以 application/x-www-form-urlencoded
    提交表单参数 count/paged；鉴权方式与签到一致（Cookie + Bearer）。

    只返回 mission 子对象，其中字段：
    - date: 上次签到时间
    - credit: 今日签到获取的锋币
    - always: 连续签到天数
    - my_credit: 账户锋币总数

    Args:
        cookie: 登录 Cookie
        proxy: 代理地址（可选）

    Returns:
        Optional[dict]: mission 子对象，失败返回 None
    """
    try:
        from curl_cffi import requests as curl_requests

        headers = build_auth_headers(cookie)
        # 该接口要求表单提交，而非 JSON
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        proxies = {"http": proxy, "https": proxy} if proxy else None

        response = curl_requests.post(
            GET_USER_MISSION_API,
            headers=headers,
            data="count=1&paged=1",
            timeout=15,
            proxies=proxies,
        )

        if response.status_code != 200:
            log_error(f"获取签到状态失败，服务器返回状态码: {response.status_code}")
            # 记录接口返回的完整内容，便于排查 403/风控/登录失效等问题
            log_response_detail(response)
            return None

        try:
            res_data = response.json()
        except ValueError:
            log_warning(f"签到状态响应非 JSON 格式: {response.text[:200]}")
            log_response_detail(response)
            return None

        if not isinstance(res_data, dict):
            log_warning(f"签到状态响应格式异常: {response.text[:200]}")
            log_response_detail(response)
            return None

        mission = res_data.get("mission")
        if not isinstance(mission, dict):
            log_warning("签到状态响应中缺少 mission 字段")
            log_response_detail(response)
            return None

        return mission

    except ImportError:
        log_error("缺少依赖: curl_cffi，请执行 pip install curl_cffi")
        return None
    except Exception as e:
        log_error(f"获取签到状态异常: {str(e)}")
        return None


def sign(cookie: str, proxy: Optional[str] = None) -> bool:
    """
    执行签到

    流程：
    1. 调用 getUserMission 获取当前签到状态（只解析 mission 字段）
    2. 若今日已签到，直接跳过
    3. 调用 userMission 接口；只要响应值大于 0，即本次签到成功，
       该值就是本次签到获取的锋币数量

    Args:
        cookie: 登录 cookie
        proxy: 代理地址（可选）

    Returns:
        bool: 签到是否成功
    """
    try:
        from curl_cffi import requests as curl_requests

        headers = build_auth_headers(cookie)
        proxies = {"http": proxy, "https": proxy} if proxy else None

        # 1. 获取当前签到状态
        mission = get_user_mission(cookie, proxy)
        if mission:
            last_date = str(mission.get("date", ""))
            today_gain = _to_int(mission.get("credit", 0))
            days = _to_int(mission.get("always", 0))
            total = _to_int(mission.get("my_credit", 0))
            log_info(
                f"当前签到状态：上次签到 {last_date}，今日已获 {today_gain} 锋币，"
                f"连续 {days} 天，账户共 {total} 锋币"
            )

            if _is_today(last_date) and today_gain > 0:
                log_info("今日已签到，跳过")
                return True

        # 2. 调用签到接口
        log_info("正在签到...")
        response = curl_requests.post(
            USER_MISSION_API,
            headers=headers,
            timeout=15,
            proxies=proxies,
        )

        if response.status_code != 200:
            log_error(f"签到失败，服务器返回状态码: {response.status_code}")
            # 记录接口返回的完整内容，便于排查 403/风控/登录失效等问题
            log_response_detail(response)
            return False

        try:
            res_data = response.json()
        except ValueError:
            log_warning(f"签到响应非 JSON 格式: {response.text[:200]}")
            log_response_detail(response)
            return False

        # 兼容两种响应格式：
        # - 数字（旧版/简化）：直接表示本次签到获得的锋币数
        # - dict（新版）：顶层 credit 为本次锋币，mission 子对象含完整签到信息
        if isinstance(res_data, dict):
            gain = _to_int(res_data.get("credit"), 0)
            if gain == 0:
                mission = res_data.get("mission") or {}
                gain = _to_int(mission.get("credit"), 0)
        else:
            gain = _to_int(res_data, 0)

        if gain > 0:
            log_success(f"签到成功！获得 {gain} 锋币")
            return True

        log_warning(f"签到未获得锋币，可能今日已签到或失败: {res_data}")
        log_response_detail(response)
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

    # sign() 内部会先获取签到状态，再调用 userMission 接口
    success = sign(cookie, proxy)


    if success:
        log_success("任务完成")
    else:
        log_error("任务失败")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
