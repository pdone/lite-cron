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
- NODESEEK_UA: 覆盖 User-Agent（可选，建议填与导出 cookie 的浏览器完全一致的 UA）
- NODESEEK_IMPERSONATE: 强制指定 curl_cffi 指纹（可选，默认按 chrome146→chrome145→... 自动降级）

依赖：
- curl_cffi: 用于模拟浏览器请求，绕过反爬虫

注意（Cloudflare）：
- NodeSeek 由 Cloudflare 托管挑战保护，cf_clearance 与「出口 IP + User-Agent + TLS 指纹」绑定。
- 导出 cookie 的浏览器必须走与 NODESEEK_PROXY 相同的出口 IP。
- 指纹版本同样关键：实测 chrome124 被判定不匹配（403 挑战），chrome145/146 可通过，
  因此脚本按版本从新到旧自动切换重试，无需手工调整。
- UA 若与浏览器不一致，可用 NODESEEK_UA 显式覆盖。
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import (
    log_info,
    log_success,
    log_error,
    log_warning,
    log_debug,
    log_response_detail,
)

from urllib.parse import urlparse

# 配置常量
BASE_URL = "https://www.nodeseek.com"
SIGN_URL = f"{BASE_URL}/api/attendance"

# 浏览器请求头：不写死 User-Agent，由 curl_cffi 按 impersonate 生成
# （UA 与 TLS 指纹必须出自同一浏览器版本，否则 Cloudflare 会判定为伪造并下发挑战）
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.nodeseek.com",
    "Referer": "https://www.nodeseek.com/board",
    "Content-Type": "application/json",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

# curl_cffi 指纹候选（从新到旧）：Cloudflare 的 cf_clearance 与客户端 TLS/HTTP2
# 指纹版本绑定，旧版本指纹会被判定不匹配并重新下发挑战，因此新版优先、逐级降级重试
IMPERSONATE_CANDIDATES = (
    "chrome146",
    "chrome145",
    "chrome142",
    "chrome131",
    "chrome124",
    "chrome120",
)

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


def parse_cookie_string(cookie: str) -> dict:
    """
    将 cookie 字符串解析为字典

    Args:
        cookie: 形如 "a=1; b=2" 的 cookie 字符串

    Returns:
        dict: cookie 键值对
    """
    cookies = {}
    for item in cookie.split(";"):
        item = item.strip()
        if "=" in item:
            key, value = item.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def get_supported_impersonations() -> set:
    """
    获取当前 curl_cffi 支持的指纹名称集合

    Returns:
        set: 支持的指纹名（小写）；老版本 curl_cffi 无法查询时返回空集合
    """
    try:
        from curl_cffi.requests.impersonate import BrowserType

        return {item.value.lower() for item in BrowserType}
    except Exception:
        return set()


def get_impersonate_candidates() -> list:
    """
    计算本次要尝试的指纹顺序（新版本优先，自动过滤当前 curl_cffi 不支持的指纹）

    Cloudflare 的 cf_clearance 与客户端 TLS/HTTP2 指纹版本绑定，
    老版本指纹（如 chrome124）会被判定不匹配并重新下发挑战。

    Returns:
        list: 指纹名称列表；无可用指纹时返回 [None]（走 curl_cffi 默认指纹）
    """
    preferred = os.environ.get("NODESEEK_IMPERSONATE", "").strip().lower()
    candidates = [preferred] if preferred else []
    candidates += [c for c in IMPERSONATE_CANDIDATES if c not in candidates]

    supported = get_supported_impersonations()
    if not supported:
        return candidates

    usable = [c for c in candidates if c in supported]
    skipped = [c for c in candidates if c not in supported]
    if skipped:
        log_debug(f"当前 curl_cffi 不支持指纹: {', '.join(skipped)}")

    if usable:
        return usable

    if preferred:
        log_warning(f"⚠️ 指定的指纹 {preferred} 不受支持，改用 curl_cffi 默认指纹")
    return [None]


def build_session(cookie: str, proxy: Optional[str] = None, impersonate: Optional[str] = None):
    """
    创建 curl_cffi 会话（UA 与 TLS 指纹保持一致）

    Args:
        cookie: 登录 cookie
        proxy: 代理地址（可选）
        impersonate: 指纹目标（可选，为空则使用 curl_cffi 默认指纹）

    Returns:
        curl_cffi.requests.Session: 已配置好的会话对象
    """
    from curl_cffi import requests as curl_requests

    headers = HEADERS.copy()
    ua = os.environ.get("NODESEEK_UA")
    if ua:
        # 显式覆盖 UA 时必须与导出 cookie 的浏览器一致，cf_clearance 与 UA 绑定
        headers["User-Agent"] = ua

    kwargs = {
        "headers": headers,
        "cookies": parse_cookie_string(cookie),
        "proxies": {"http": proxy, "https": proxy} if proxy else None,
        "timeout": 20,
    }
    if impersonate:
        kwargs["impersonate"] = impersonate

    session = curl_requests.Session(**kwargs)
    log_debug(f"curl_cffi 指纹: {impersonate or '默认'}" + (f", 自定义 UA: {ua}" if ua else ""))
    return session


def warmup(session):
    """
    会话预热：先访问首页，让 Cloudflare 下发 __cf_bm 等会话 cookie

    Args:
        session: curl_cffi 会话对象

    Returns:
        响应对象；预热失败时返回 None
    """
    try:
        response = session.get(f"{BASE_URL}/", timeout=20)
        log_debug(f"会话预热状态码: {response.status_code}")
        return response
    except Exception as e:
        log_warning(f"⚠️ 会话预热失败（不影响后续签到）: {e}")
        return None


def is_cloudflare_challenge(response) -> bool:
    """
    判断响应是否为 Cloudflare 挑战页

    Args:
        response: curl_cffi 响应对象

    Returns:
        bool: True 表示被 Cloudflare 拦截
    """
    try:
        text = response.text or ""
    except Exception:
        return False
    return "Just a moment" in text or "_cf_chl_opt" in text


def handle_response(response) -> bool:
    """
    解析签到接口响应

    NodeSeek 签到 API 特性：
    - 签到成功: 200 + {"success": true, "gain": N, "current": N}
    - 今日已签到: 500 + {"success": false, "message": "今天已完成签到，请勿重复操作"}
    - 其他失败: 非 200 状态码

    Args:
        response: curl_cffi 响应对象

    Returns:
        bool: 签到是否成功（已签到视为成功）
    """
    status_code = response.status_code
    log_info(f"响应状态码: {status_code}")

    # 尝试解析 JSON 响应体（无论状态码如何，NodeSeek 可能在 500 时也返回 JSON）
    res_data = None
    try:
        res_data = response.json()
        log_info(f"响应 JSON: {res_data}")
    except Exception:
        log_warning(f"⚠️ 响应非 JSON 格式: {response.text[:200]}")
        # 记录站点返回的完整内容，便于排查风控页/错误页
        log_response_detail(response)

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

        message = res_data.get("message", "")
        log_warning(f"⚠️ 签到未成功: {message}")
        log_response_detail(response)
        return False

    # 其他错误
    message = res_data.get("message", "") if res_data else response.text[:200]
    log_error(f"❌ 签到失败，状态码: {status_code}, 响应: {message}")
    log_response_detail(response)
    return False


def sign(cookie: str, random_mode: str, proxy: Optional[str] = None) -> bool:
    """
    执行签到（Cloudflare 挑战时自动切换指纹重试）

    Args:
        cookie: 登录 cookie
        random_mode: 是否随机鸡腿，'true' 或 'false'
        proxy: 代理地址（可选）

    Returns:
        bool: 签到是否成功（已签到视为成功）
    """
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        log_error("❌ 缺少依赖: curl_cffi，请执行 pip install curl_cffi")
        return False

    url = f"{SIGN_URL}?random={random_mode}"
    candidates = get_impersonate_candidates()

    log_info(f"🚀 正在签到... (随机模式: {random_mode})")

    challenged = None
    last_error = None

    for target in candidates:
        session = None
        try:
            session = build_session(cookie, proxy, target)

            # 预热：先访问首页，让 Cloudflare 下发 __cf_bm 等会话 cookie
            warm_response = warmup(session)
            if warm_response is not None and is_cloudflare_challenge(warm_response):
                challenged = warm_response
                log_info(f"⚠️ 指纹 {target or '默认'} 首页即被挑战，尝试下一个指纹")
                continue

            # 带空 JSON body，避免「Content-Type: application/json 却零长度 body」的特征异常
            response = session.post(url, data="{}", timeout=20)

            if is_cloudflare_challenge(response):
                challenged = response
                log_info(f"⚠️ 指纹 {target or '默认'} 签到请求被挑战，尝试下一个指纹")
                continue

            return handle_response(response)

        except Exception as e:
            last_error = e
            log_debug(f"指纹 {target or '默认'} 请求异常: {e}")
            continue
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    if challenged is not None:
        log_error(
            "❌ 所有指纹均被 Cloudflare 托管挑战拦截（HTTP {}），请求未到达签到接口。"
            "常见原因：cf_clearance 已失效、导出 cookie 的出口 IP 与代理不一致、"
            "User-Agent 与导出 cookie 的浏览器差异过大".format(challenged.status_code)
        )
        log_response_detail(challenged)
        return False

    log_error(f"❌ 签到请求全部失败: {last_error}")
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
