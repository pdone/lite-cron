#!/usr/bin/env python3
"""
PTTime 自动签到任务

功能：
- 自动签到 PTTime 站点
- 获取签到天数和魔力值信息
- 支持代理配置

环境变量：
- PTTIME_COOKIE: 登录 cookie（必需）
- PTTIME_UID: 用户 ID（必需）
- PTTIME_PROXY: 代理地址，格式为 host:port 或 user:pass@host:port（可选）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

import re
import requests
from datetime import datetime
from urllib.parse import urlparse


# 配置常量
BASE_URL = "https://www.pttime.org"
SIGN_URL = f"{BASE_URL}/attendance.php"

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "dnt": "1",
    "pragma": "no-cache",
    "priority": "u=0, i",
    "referer": "https://www.pttime.org/",
    "sec-ch-ua": '"Chromium";v="127", "Not)A;Brand";v="99"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
}


def get_credentials() -> tuple:
    """
    从环境变量获取配置

    Returns:
        tuple: (cookie, uid, proxy_url)
    """
    cookie = os.environ.get("PTTIME_COOKIE")
    uid = os.environ.get("PTTIME_UID")
    proxy_url = os.environ.get("PTTIME_PROXY")

    if not cookie or not uid:
        log_error("错误: 未配置环境变量 PTTIME_COOKIE 或 PTTIME_UID")
        return None, None, None

    return cookie, uid, proxy_url


def parse_proxy(proxy_url: str) -> dict:
    """
    解析代理地址

    Args:
        proxy_url: 代理地址，格式为 host:port 或 user:pass@host:port

    Returns:
        dict: requests 可用的 proxies 配置
    """
    if not proxy_url:
        return None

    try:
        # 如果缺少协议前缀，添加 http://
        if "://" not in proxy_url:
            proxy_url = f"http://{proxy_url}"

        parsed = urlparse(proxy_url)

        proxies = {"http": proxy_url, "https": proxy_url}

        log_info(f"使用代理: {parsed.hostname}:{parsed.port}")
        return proxies

    except Exception as e:
        log_warning(f"代理解析失败: {e}")
        return None


def sign(cookie: str, uid: str, proxies: dict = None) -> bool:
    """
    执行签到

    Args:
        cookie: 登录 cookie
        uid: 用户 ID
        proxies: 代理配置

    Returns:
        bool: 签到是否成功
    """
    try:
        # 设置请求头
        headers = HEADERS.copy()
        headers["cookie"] = cookie

        # 构建 URL
        url = f"{SIGN_URL}?type=sign&uid={uid}"

        log_info("正在签到...")

        response = requests.get(
            url, headers=headers, proxies=proxies, timeout=30, allow_redirects=True
        )
        response.raise_for_status()

        html = response.text

        # 解析签到结果（参考原 JS 正则）
        # 总签到天数
        total_sign_match = re.search(r"总签到：(\d+)天", html)
        # 魔力值
        magic_match = re.search(r"\]: (\d+\.?\d*)\[", html)
        # 详细签到信息
        detail_match = re.search(
            r"这是你的第 <b>(\d+)</b> 次签到，已连续签到 <b>(\d+)</b> 天，本次签到获得 <b>(\d+)</b> 个魔力值。",
            html,
        )

        if total_sign_match and magic_match:
            total_sign = total_sign_match.group(1)
            total_magic = magic_match.group(1)

            if detail_match:
                total_count = detail_match.group(1)
                consecutive = detail_match.group(2)
                earned = detail_match.group(3)
                final_magic = float(total_magic) + int(earned)

                sign_msg = (
                    f"签到成功！\n"
                    f"  总签到: {total_count} 天\n"
                    f"  连续签到: {consecutive} 天\n"
                    f"  本次获得: {earned} 魔力值\n"
                    f"  总魔力值: {final_magic:.1f}"
                )
                log_success(sign_msg)
            else:
                sign_msg = (
                    f"签到成功！\n"
                    f"  总签到: {total_sign} 天\n"
                    f"  总魔力值: {total_magic}"
                )
                log_success(sign_msg)

            return True
        else:
            log_warning("未能解析签到结果，可能已签到或页面结构变更")
            # 尝试检测已签到提示
            if "已经签到" in html or "今日已签" in html:
                log_info("今日已签到")
                return True
            return False

    except requests.exceptions.ProxyError as e:
        log_error(f"代理连接失败: {e}")
        return False
    except requests.exceptions.Timeout:
        log_error("请求超时")
        return False
    except requests.exceptions.RequestException as e:
        log_error(f"请求失败: {e}")
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
    # 记录开始时间
    # start_time = datetime.now()
    # start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')

    log_info("PTTime 签到任务开始")

    # 获取配置
    cookie, uid, proxy_url = get_credentials()

    if not cookie or not uid:
        log_info("任务终止: 未配置有效凭据")
        return 1

    # 解析代理
    proxies = parse_proxy(proxy_url) if proxy_url else None

    # 执行签到
    success = sign(cookie, uid, proxies)

    # 记录结束时间
    # end_time = datetime.now()
    # end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    # duration = (end_time - start_time).total_seconds()

    # 汇总结果
    if success:
        log_success("任务完成")
    else:
        log_error("任务失败")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
