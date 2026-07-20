#!/usr/bin/env python3
"""
V2EX 论坛自动签到任务

功能：
- 自动登录 V2EX 论坛
- 执行每日签到获取金币
- 获取用户信息（用户名、余额）

环境变量：
- V2EX_COOKIE: V2EX 登录 Cookie（必需，格式: key1=value1; key2=value2）
- V2EX_PROXY: 代理服务器地址（可选，如 http://127.0.0.1:7890）
- V2EX_SSL_VERIFY: 是否验证 SSL 证书（可选，true/false，默认false）

依赖：
- curl_cffi: 用于模拟浏览器请求，绕过 Cloudflare 反爬虫
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

import re
from datetime import datetime
from typing import Dict, List, Optional

# 配置常量
BASE_URL = "https://www.v2ex.com"
DAILY_URL = f"{BASE_URL}/mission/daily"
BALANCE_URL = f"{BASE_URL}/balance"

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
    ),
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class V2ex:
    """V2EX 签到任务类"""

    name = "V2EX 论坛"

    def __init__(self, check_item: dict):
        """初始化

        Args:
            check_item: 配置字典，包含 cookie、proxy 等参数
        """
        self.check_item = check_item
        self.session = None

    def _init_session(self):
        """初始化请求会话（使用 curl_cffi 模拟 Chrome 浏览器）

        Returns:
            curl_cffi.Session: 配置好的会话对象；Cookie 未配置时返回 None
        """
        try:
            from curl_cffi import requests as curl_requests
        except ImportError:
            log_error("缺少依赖: curl_cffi，请执行 pip install curl_cffi")
            return None

        # 解析 Cookie
        cookie_str = self.check_item.get("cookie", "")
        if not cookie_str:
            return None

        cookies = {}
        for item in cookie_str.split("; "):
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key] = value

        # 配置代理
        proxy = self.check_item.get("proxy", "")
        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}
            log_info(f"使用代理: {proxy}")

        # 创建 curl_cffi 会话，模拟 Chrome 浏览器以绕过 Cloudflare
        session = curl_requests.Session(
            headers=HEADERS,
            cookies=cookies,
            proxies=proxies,
            impersonate="chrome120",
        )

        return session

    def _parse_once_token(self, html: str) -> Optional[str]:
        """从 HTML 中提取签到 token

        Args:
            html: 页面 HTML 内容

        Returns:
            Optional[str]: 签到 URL 或 None
        """
        pattern = (
            r"<input type=\"button\" class=\"super normal button\""
            r" value=\".*?\" onclick=\"location\.href = '(.*?)';\" />"
        )
        urls = re.findall(pattern=pattern, string=html)
        return urls[0] if urls else None

    def _is_already_signed(self, html: str) -> bool:
        """检测页面是否表示今日已签到

        V2EX 已签到时页面会显示"每日登录奖励已领取"提示。
        注意：不能使用"查看我的账户余额"或"已连续登录"作为判断依据，
        这两个文字在未签到状态下也会出现在页面其他位置（账户链接、历史统计），
        会导致误判已签到而跳过签到。

        Args:
            html: 签到页面 HTML 内容

        Returns:
            bool: True 表示今日已签到
        """
        return "每日登录奖励已领取" in html

    def _parse_user_info(self, html: str) -> Dict[str, str]:
        """从页面解析用户信息

        Args:
            html: 页面 HTML 内容

        Returns:
            Dict[str, str]: 用户信息字典
        """
        info = {}

        # 解析用户名
        username_match = re.findall(
            pattern=r'<a href="/member/.*?" class="top">(.*?)</a>',
            string=html,
        )
        info["username"] = username_match[0] if username_match else "获取失败"

        # 解析余额
        total_match = re.findall(
            pattern=r'<td class="d" style="text-align: right;">(\d+\.\d+)</td>',
            string=html,
        )
        info["balance"] = total_match[0] if total_match else "0.00"

        # 解析今日签到奖励
        today_match = re.findall(
            pattern=r'<td class="d"><span class="gray">(.*?)</span></td>',
            string=html,
        )
        info["today_reward"] = today_match[0] if today_match else "签到失败"

        return info

    def sign(self) -> List[Dict[str, str]]:
        """执行签到

        Returns:
            List[Dict[str, str]]: 签到结果列表
        """
        msg = []
        ssl_verify = self.check_item.get("ssl_verify", False)

        try:
            # 访问签到页面
            log_info("访问签到页面...")
            response = self.session.get(url=DAILY_URL, verify=ssl_verify, timeout=20)
            response.raise_for_status()

            # 优先检测是否已签到（无论按钮是否存在，只要页面含已签到标记就跳过）
            if self._is_already_signed(response.text):
                log_info("今日已签到，跳过签到步骤")
                already_signed = True
            else:
                # 未签到，获取签到 URL
                once_url = self._parse_once_token(response.text)
                if once_url is None:
                    log_warning("无法获取签到链接，Cookie 可能已过期")
                    msg.append({"name": "签到状态", "value": "Cookie 可能已过期"})
                    return msg
                already_signed = False

            # 执行签到（已签到则跳过）
            if not already_signed:
                log_info("执行签到...")
                once_token = once_url.split("=")[-1]
                sign_headers = {"Referer": DAILY_URL}
                sign_response = self.session.get(
                    url=f"{BASE_URL}{once_url}",
                    verify=ssl_verify,
                    headers=sign_headers,
                    params={"once": once_token},
                    timeout=20,
                )
                sign_response.raise_for_status()
                log_success("签到请求已发送")

            # 获取用户信息
            log_info("获取用户信息...")
            balance_response = self.session.get(url=BALANCE_URL, verify=ssl_verify, timeout=20)
            balance_response.raise_for_status()
            user_info = self._parse_user_info(balance_response.text)

            # 构建结果
            msg.append({"name": "帐号信息", "value": user_info["username"]})
            msg.append({"name": "今日签到", "value": user_info["today_reward"]})
            msg.append({"name": "帐号余额", "value": user_info["balance"]})

            log_success("签到完成")
            return msg

        except Exception as e:
            err_str = str(e)
            log_error(f"签到异常: {err_str}")
            if "proxy" in err_str.lower() or "connect" in err_str.lower():
                msg.append({"name": "签到状态", "value": f"代理错误: {err_str}"})
            elif "timeout" in err_str.lower() or "timed out" in err_str.lower():
                msg.append({"name": "签到状态", "value": "请求超时"})
            else:
                msg.append({"name": "签到状态", "value": f"请求失败: {err_str}"})
            return msg

    def main(self) -> str:
        """主执行函数

        Returns:
            str: 执行结果消息
        """
        # 初始化会话
        self.session = self._init_session()
        if not self.session:
            log_error("初始化失败: Cookie 未配置")
            return "初始化失败: Cookie 未配置"

        # 执行签到
        result_list = self.sign()
        result_msg = "\n".join([f"{item['name']}: {item['value']}" for item in result_list])

        return result_msg


def get_config() -> dict:
    """从环境变量获取配置

    Returns:
        dict: 配置字典
    """
    cookie = os.environ.get("V2EX_COOKIE", "")
    if not cookie:
        log_error("错误: 未配置环境变量 V2EX_COOKIE")
        return {}

    ssl_verify_str = os.environ.get("V2EX_SSL_VERIFY", "false").lower()

    return {
        "cookie": cookie,
        "proxy": os.environ.get("V2EX_PROXY", ""),
        "ssl_verify": ssl_verify_str == "true",
    }


def main() -> int:
    """主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info("V2EX 签到任务开始")

    # 获取配置
    config = get_config()
    if not config:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    # 执行任务
    try:
        v2ex = V2ex(check_item=config)
        result = v2ex.main()
        log_info("任务结果:\n" + result)
        return 0
    except Exception as e:
        log_error(f"任务执行异常: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
