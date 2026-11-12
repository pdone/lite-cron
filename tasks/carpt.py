#!/usr/bin/env python3
"""
CarPT（carpt.net）自动签到任务

CarPT 是 NexusPHP 站点，签到入口为 /attendance.php。不同时期/改版的签到页
存在两种形态，脚本自动兼容：
  1. 直接 GET /attendance.php 即完成签到，页面返回「签到获得 X」「已连续签到 X 天」
  2. GET 只返回签到表单，需提取 formhash 后 POST
     action=attendance&formhash=xxx 才真正完成签到
若页面提供带签到参数的链接（如 attendance.php?action=sign），也会自动跟随一次。
无法识别页面结构时不会误报成功，而是把响应原文落盘到 logs/responses/ 便于排查。

环境变量：
- CARPT_COOKIE: 登录 Cookie（必需；NexusPHP 需含 c_secure_uid / c_secure_pass 等登录态字段）
- CARPT_PROXY: 代理地址（可选，如 http://127.0.0.1:7890）
- CARPT_BASE_URL: 站点根地址（可选，默认 https://carpt.net）
- CARPT_SIGN_QUERY: 签到页额外查询串（可选，如 action=sign；站点改版时无需改代码即可适配）

依赖：
- requests
"""

import html as html_lib
import os
import re
import sys
from typing import Optional
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import (
    log_info,
    log_success,
    log_error,
    log_warning,
    log_debug,
    log_response_detail,
)

import requests


DEFAULT_BASE_URL = "https://carpt.net"
SIGN_PATH = "/attendance.php"
# 站点响应偶发较慢（实测 3~15 秒，个别请求更长），留出充足超时
TIMEOUT = 45

# 已签到文案（视为成功，保证任务幂等）
ALREADY_HINTS = (
    "今日已签到",
    "今天已签到",
    "已经签到",
    "签到已得",
    "请勿重复",
    "重复签到",
    "already signed",
)
# 签到成功文案
SUCCESS_HINTS = (
    "签到成功",
    "签到获得",
    "本次签到获得",
    "获得魔力值",
    "签到完成",
)


def get_config() -> tuple:
    """
    从环境变量读取配置

    Returns:
        tuple: (cookie, base_url, sign_query, proxy)
    """
    cookie = (os.environ.get("CARPT_COOKIE") or "").strip()
    base_url = (os.environ.get("CARPT_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    sign_query = (os.environ.get("CARPT_SIGN_QUERY") or "").strip().lstrip("?&")
    proxy = (os.environ.get("CARPT_PROXY") or "").strip()
    return cookie, base_url, sign_query, proxy


def parse_proxy(proxy_url: Optional[str]) -> Optional[str]:
    """规范化代理地址，缺少协议时补 http://"""
    if not proxy_url:
        return None
    try:
        if "://" not in proxy_url:
            proxy_url = f"http://{proxy_url}"
        parsed = urlparse(proxy_url)
        log_info(f"使用代理: {parsed.hostname}:{parsed.port}")
        return proxy_url
    except Exception as e:
        log_warning(f"代理解析失败，将直连: {e}")
        return None


def build_headers(cookie: str, base_url: str, referer: Optional[str] = None) -> dict:
    """构造浏览器请求头"""
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "max-age=0",
        "Cookie": cookie,
        "Referer": referer or f"{base_url}/index.php",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    }


def response_html(response) -> str:
    """取响应原文，统一按 UTF-8 解码（CarPT 声明 charset=utf-8）"""
    content = getattr(response, "content", b"") or b""
    if content:
        return content.decode("utf-8", errors="replace")
    return getattr(response, "text", "") or ""


def visible_text(html: str) -> str:
    """去除脚本、样式与标签，提取可见文本，便于中文文案匹配"""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def is_login_page(response, text: str) -> bool:
    """判断是否被重定向到登录页（Cookie 失效）"""
    final_url = str(getattr(response, "url", "") or "")
    if re.search(r"(login|takelogin)\.php", final_url, re.I):
        return True
    return "您需要先登录" in text or "请先登录" in text


def parse_result(text: str) -> tuple:
    """
    解析签到结果文案

    Returns:
        tuple: (state, message)；state 为 already / success / unknown
    """
    if any(hint in text for hint in ALREADY_HINTS):
        return "already", "今日已签到，无需重复签到"

    if any(hint in text for hint in SUCCESS_HINTS):
        earned = re.search(r"签到获得\D{0,12}(\d+)", text) or re.search(
            r"(?:获得|得到)\D{0,8}(\d+)\D{0,8}魔力", text
        )
        consecutive = re.search(r"已连续签到\D{0,8}(\d+)", text) or re.search(
            r"连续签到\D{0,8}(\d+)\D{0,4}天", text
        )
        parts = ["签到成功"]
        if earned:
            parts.append(f"本次获得 {earned.group(1)} 魔力值")
        if consecutive:
            parts.append(f"连续签到 {consecutive.group(1)} 天")
        return "success", "，".join(parts)

    return "unknown", ""


def extract_formhash(html: str) -> Optional[str]:
    """从签到表单中提取 formhash（兼容属性顺序变化）"""
    input_tag = re.search(r"<input[^>]*name=[\"']formhash[\"'][^>]*>", html, re.I)
    if not input_tag:
        return None
    value = re.search(r"value=[\"']([^\"']+)[\"']", input_tag.group(0), re.I)
    return value.group(1) if value else None


def extract_sign_link(html: str, base_url: str) -> Optional[str]:
    """提取页面中带签到参数的链接（部分改版需要二次 GET 才完成签到）"""
    for match in re.finditer(r"href=[\"']([^\"']*attendance\.php\?[^\"']+)[\"']", html, re.I):
        href = html_lib.unescape(match.group(1))
        if re.search(r"sign", href, re.I):
            return urljoin(base_url + "/", href)
    return None


def report(state: str, message: str) -> bool:
    """按解析结果输出日志"""
    if state in ("already", "success"):
        log_success(message)
        return True
    return False


def sign(cookie: str, base_url: str, sign_query: str, proxies: Optional[dict]) -> bool:
    """
    执行签到

    流程：
    1. GET /attendance.php，先排除 Cookie 失效
    2. 页面已含签到结果 → 直接结束（GET 即签到模式）
    3. 否则按页面提供的 formhash 表单 / 签到链接补一次请求
    4. 二次响应仍无法识别 → 落盘原文并判失败

    Args:
        cookie: 登录 Cookie
        base_url: 站点根地址
        sign_query: 签到页额外查询串
        proxies: requests 代理配置

    Returns:
        bool: 签到是否成功（含今日已签到）
    """
    sign_url = f"{base_url}{SIGN_PATH}"
    if sign_query:
        sign_url = f"{sign_url}?{sign_query}"

    try:
        session = requests.Session()
        headers = build_headers(cookie, base_url)

        log_info(f"正在访问签到页: {sign_url}")
        response = session.get(
            sign_url, headers=headers, proxies=proxies, timeout=TIMEOUT, allow_redirects=True
        )
        html = response_html(response)
        text = visible_text(html)

        if response.status_code != 200:
            log_error(f"签到页返回 HTTP {response.status_code}")
            log_response_detail(response, keyword="签到")
            return False

        if is_login_page(response, text):
            log_error("Cookie 失效或未登录，站点重定向到登录页")
            log_response_detail(response, keyword="签到")
            return False

        state, message = parse_result(text)
        if state != "unknown":
            log_debug(f"GET 已返回签到结果: {state}")
            return report(state, message)

        # GET 未给出结果，尝试按页面结构补一次签到动作
        formhash = extract_formhash(html)
        sign_link = extract_sign_link(html, base_url)

        if formhash:
            log_info("检测到签到表单，提交 formhash 完成签到")
            post_headers = build_headers(cookie, base_url, referer=sign_url)
            post_headers["Content-Type"] = "application/x-www-form-urlencoded"
            response = session.post(
                sign_url,
                headers=post_headers,
                data={"action": "attendance", "formhash": formhash},
                proxies=proxies,
                timeout=TIMEOUT,
                allow_redirects=True,
            )
        elif sign_link:
            log_info(f"检测到签到链接，跟随请求: {sign_link}")
            response = session.get(
                sign_link,
                headers=build_headers(cookie, base_url, referer=sign_url),
                proxies=proxies,
                timeout=TIMEOUT,
                allow_redirects=True,
            )
        else:
            log_warning("未能识别签到结果或签到表单，可能页面结构已变更")
            log_response_detail(response, keyword="签到")
            return False

        html = response_html(response)
        text = visible_text(html)
        if response.status_code != 200 or is_login_page(response, text):
            log_error(f"签到请求异常: HTTP {response.status_code}")
            log_response_detail(response, keyword="签到")
            return False

        state, message = parse_result(text)
        if not report(state, message):
            log_warning("签到请求后仍未解析到结果，可能页面文案已变更")
            log_response_detail(response, keyword="签到")
            return False
        return True

    except requests.exceptions.ProxyError as e:
        log_error(f"代理连接失败: {e}")
        return False
    except requests.exceptions.Timeout:
        log_error("请求超时")
        return False
    except requests.exceptions.RequestException as e:
        status = e.response.status_code if e.response is not None else "N/A"
        log_error(f"请求失败: {e} | HTTP {status}")
        log_response_detail(getattr(e, "response", None), keyword="签到")
        return False
    except Exception as e:
        log_error(f"未知错误: {e}")
        return False


def main() -> int:
    """
    主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info("CarPT 签到任务开始")

    cookie, base_url, sign_query, proxy_url = get_config()
    if not cookie:
        log_error("错误: 未配置 CARPT_COOKIE，任务终止")
        return 1
    if "c_secure_uid" not in cookie and "c_secure_pass" not in cookie:
        log_warning("Cookie 中未检测到 c_secure_uid / c_secure_pass，请确认复制的是完整登录态 Cookie")

    proxy = parse_proxy(proxy_url)
    proxies = {"http": proxy, "https": proxy} if proxy else None

    success = sign(cookie, base_url, sign_query, proxies)

    if success:
        log_success("任务完成")
    else:
        log_error("任务失败")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
