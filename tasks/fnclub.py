#!/usr/bin/env python3
"""
飞牛Nas论坛自动签到任务

功能：
- 自动签到飞牛论坛
- 获取打卡动态信息

环境变量：
- FNNAS_COOKIE: 登录 cookie（必需）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

import re
import requests
from datetime import datetime


# 配置常量
BASE_URL = "https://club.fnnas.com"
SIGN_URL = f"{BASE_URL}/plugin.php?id=zqlj_sign"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Referer": "https://club.fnnas.com/portal.php",
    "Content-Type": "text/html; charset=utf-8",
}


def get_cookie() -> str:
    """从环境变量获取 cookie"""
    cookie = os.environ.get("FNNAS_COOKIE")
    if not cookie:
        log_error("错误: 未配置环境变量 FNNAS_COOKIE")
        return None
    return cookie


def get_sign_param(session: requests.Session) -> str:
    """GET 签到页面并提取 sign 参数"""
    try:
        response = session.get(SIGN_URL, timeout=15)
        response.raise_for_status()
        html = response.text

        # 匹配签到按钮，抓取 sign 参数
        r_sign_btn = re.compile(
            r'<a href="plugin.php\?id=zqlj_sign&sign=([0-9a-fA-F]+)" class="btna">点击打卡</a>'
        )
        r_signed_btn = re.compile(
            r'<a href="plugin.php\?id=zqlj_sign&sign=([0-9a-fA-F]+)" class="btna">今日已打卡</a>'
        )

        match = r_sign_btn.search(html)
        match_signed = r_signed_btn.search(html)

        if match:
            return match.group(1)
        elif match_signed:
            return match_signed.group(1)

        return None

    except Exception as e:
        log_error(f"获取 sign 参数失败: {e}")
        return None


def do_sign(session: requests.Session, sign_param: str) -> dict:
    """执行签到"""
    if not sign_param:
        return {"name": "签到结果", "value": "签到失败，未能成功获取 sign 参数"}

    try:
        response = session.get(f"{SIGN_URL}&sign={sign_param}", timeout=15)
        response.raise_for_status()
        html = response.text

        if re.search(r"恭喜您，打卡成功！", html):
            return {"name": "签到结果", "value": "✅ 签到成功"}
        elif re.search(r"您今天已经打过卡了，请勿重复操作！", html):
            return {"name": "签到结果", "value": "ℹ️ 您已签到，请勿重复签到"}
        else:
            return {"name": "签到结果", "value": "⚠️ 未知签到异常"}

    except Exception as e:
        return {"name": "签到结果", "value": f"❌ 签到异常: {e}"}


def get_sign_info(session: requests.Session) -> list:
    """获取打卡动态信息"""
    msg = []

    try:
        response = session.get(SIGN_URL, timeout=15)
        response.raise_for_status()
        html = response.text

        # 1. 匹配"我的打卡动态"这一整块 HTML
        pattern = re.compile(
            r"<strong>\s*我的打卡动态\s*</strong>"
            r".*?"
            r'<div[^>]*class="bm_c"[^>]*>.*?</div>',
            re.S,
        )

        m = pattern.search(html)
        if not m:
            raise RuntimeError("没匹配到 '我的打卡动态' 这一段 HTML")

        block_html = m.group(0)

        # 2. 保证每个 <li> 独立一行
        block_html = re.sub(r"</li\s*>", "</li>\n", block_html)

        # 3. 去掉所有 HTML 标签
        text = re.sub(r"<[^>]+>", "", block_html)

        # 4. 删除"我的打卡动态"文本
        text = text.replace("我的打卡动态", "")

        # 5. 按行切分并清理空白
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 6. 分割冒号并生成 msg 列表
        for line in lines:
            if "：" in line:
                sep = "："
            elif ":" in line:
                sep = ":"
            else:
                continue

            name, value = line.split(sep, 1)
            msg.append(
                {
                    "name": name.strip(),
                    "value": value.strip(),
                }
            )

    except Exception as e:
        msg.append(
            {
                "name": "获取打卡动态失败",
                "value": str(e),
            }
        )

    return msg


def main() -> int:
    """主函数"""
    # start_time = datetime.now()
    # start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')

    log_info("飞牛Nas论坛签到任务开始")

    cookie = get_cookie()
    if not cookie:
        log_info("任务终止: 未配置有效凭据")
        return 1

    # 创建会话
    session = requests.Session()
    headers = HEADERS.copy()
    headers["Cookie"] = cookie
    session.headers.update(headers)

    # 获取 sign 参数
    log_info("获取签到参数...")
    sign_param = get_sign_param(session)
    if sign_param:
        log_success("获取到 sign 参数")
    else:
        log_warning("未能获取 sign 参数（可能已签到或页面变更）")

    # 执行签到
    log_info("执行签到...")
    sign_result = do_sign(session, sign_param)
    log_info(f"{sign_result['name']}: {sign_result['value']}")

    # 获取打卡动态
    info_list = get_sign_info(session)
    if info_list:
        lines = [f"  {item['name']}: {item['value']}" for item in info_list]
        log_info(f"获取打卡动态..." + "\n".join(lines))

    # 记录结束时间
    # end_time = datetime.now()
    # end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    # duration = (end_time - start_time).total_seconds()

    if "成功" in sign_result["value"] or "已签到" in sign_result["value"]:
        log_success("任务完成")
    else:
        log_warning("任务可能未成功")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
