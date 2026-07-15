#!/usr/bin/env python3
"""
NodeSeek 论坛自动签到任务

功能：
- 自动签到 NodeSeek 论坛
- 获取鸡腿奖励信息
- 支持随机/固定鸡腿模式
- 已签到时自动识别并跳过

环境变量：
- NODESEEK_COOKIE: 登录 cookie（必需）
- NODESEEK_RANDOM: 是否随机鸡腿，true/false（可选，默认 true）
- NODESEEK_PROXY: 代理地址，格式为 host:port 或 user:pass@host:port（可选）

依赖：
- curl_cffi: 用于模拟浏览器请求，绕过反爬虫
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

from urllib.parse import urlparse

# 配置常量
BASE_URL = "https://www.nodeseek.com"
SIGN_URL = f"{BASE_URL}/api/attendance"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Origin": "https://www.nodeseek.com",
    "Referer": "https://www.nodeseek.com/board",
    "Content-Type": "application/json",
}

# 已签到特征关键词（message 中包含任一即判定为已签到）
SIGNED_KEYWORDS = ["已签到", "已完成签到", "already"]


def get_credentials() -> tuple:
    """
    从环境变量获取配置

    Returns:
        tuple: (cookie, random_mode, proxy_url)
    """
    cookie = os.environ.get("NODESEEK_COOKIE")
    random_mode = os.environ.get("NODESEEK_RANDOM", "true").lower()
    proxy_url = os.environ.get("NODESEEK_PROXY")

    if not cookie:
        log_error("❌ 错误: 未配置环境变量 NODESEEK_COOKIE")
        return None, None, None

    # 验证 random_mode 值
    if random_mode not in ("true", "false"):
        log_warning(f"⚠️ 无效的 NODESEEK_RANDOM 值: {random_mode}，使用默认值 true")
        random_mode = "true"

    return cookie, random_mode, proxy_url


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
        # 如果缺少协议前缀，添加 http://
        if "://" not in proxy_url:
            proxy_url = f"http://{proxy_url}"

        parsed = urlparse(proxy_url)
        log_info(f"🔗 使用代理: {parsed.hostname}:{parsed.port}")
        return proxy_url

    except Exception as e:
        log_warning(f"⚠️ 代理解析失败: {e}")
        return None


def is_already_signed(message: str) -> bool:
    """
    判断 message 是否表示今日已签到

    Args:
        message: API 返回的 message 字段

    Returns:
        bool: True 表示已签到
    """
    message_lower = message.lower()
    return any(kw in message or kw in message_lower for kw in SIGNED_KEYWORDS)


def sign(cookie: str, random_mode: str, proxy: Optional[str] = None) -> bool:
    """
    执行签到

    NodeSeek 签到 API 特性：
    - 签到成功: 200 + {"success": true, "gain": N, "current": N}
    - 今日已签到: 500 + {"success": false, "message": "今天已完成签到，请勿重复操作"}
    - 其他失败: 非 200 状态码

    Args:
        cookie: 登录 cookie
        random_mode: 是否随机鸡腿，'true' 或 'false'
        proxy: 代理地址（可选）

    Returns:
        bool: 签到是否成功（已签到视为成功）
    """
    try:
        from curl_cffi import requests as curl_requests

        headers = HEADERS.copy()
        headers["Cookie"] = cookie

        url = f"{SIGN_URL}?random={random_mode}"

        log_info(f"🚀 正在签到... (随机模式: {random_mode})")

        proxies = {"http": proxy, "https": proxy} if proxy else None

        response = curl_requests.post(
            url, headers=headers, impersonate="chrome110", timeout=15, proxies=proxies
        )

        status_code = response.status_code
        log_info(f"响应状态码: {status_code}")

        # 尝试解析 JSON 响应体（无论状态码如何，NodeSeek 可能在 500 时也返回 JSON）
        res_data = None
        try:
            res_data = response.json()
            log_info(f"响应 JSON: {res_data}")
        except Exception:
            log_warning(f"⚠️ 响应非 JSON 格式: {response.text[:200]}")

        # 处理已签到的情况（状态码 500 但 message 包含已签到关键词）
        if res_data and is_already_signed(res_data.get("message", "")):
            log_success(f"✅ 今日已签到，跳过: {res_data.get('message', '')}")
            return True

        # 正常签到成功
        if status_code == 200 and res_data:
            if res_data.get("success", False):
                gain = res_data.get("gain", 0)
                current = res_data.get("current", 0)
                log_success(f"✅ 签到成功！获得 {gain} 鸡腿，当前共有 {current} 鸡腿")
                return True
            else:
                message = res_data.get("message", "")
                log_warning(f"⚠️ 签到未成功: {message}")
                return False

        # 其他错误
        message = res_data.get("message", "") if res_data else response.text[:200]
        log_error(f"❌ 签到失败，状态码: {status_code}, 响应: {message}")
        return False

    except ImportError:
        log_error("❌ 缺少依赖: curl_cffi，请执行 pip install curl_cffi")
        return False
    except Exception as e:
        log_error(f"❌ 签到异常: {str(e)}")
        return False


def main() -> int:
    """
    主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info("🚀 NodeSeek 签到任务开始")

    # 获取配置
    cookie, random_mode, proxy_url = get_credentials()

    if not cookie:
        log_warning("⚠️ 任务终止: 未配置有效凭据")
        return 1

    # 解析代理
    proxy = parse_proxy(proxy_url) if proxy_url else None

    # 执行签到（API 不支持 GET 查询，直接 POST，已签到会返回特定 message）
    success = sign(cookie, random_mode, proxy)

    # 汇总结果
    if success:
        log_success("🏁 任务完成")
    else:
        log_error("🏁 任务失败")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
