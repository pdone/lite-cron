#!/usr/bin/env python3
"""
什么值得买 (SMZDM) 自动签到任务

功能：
- 自动签到获取奖励
- 显示金币、碎银、等级信息（网页登录态不可用时自动跳过，不影响签到）

环境变量：
- SMZDM_COOKIE: 登录 cookie（必需）
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

import re
import hashlib
import time
import requests


# 配置常量
BASE_URL = "https://user-api.smzdm.com"
CHECKIN_URL = f"{BASE_URL}/checkin"
TOKEN_URL = f"{BASE_URL}/robot/token"
# 用户中心网页的登录数据接口：页面 SSR 恒为游客态，登录信息由该接口在客户端拉取
USER_INFO_URL = "https://zhiyou.smzdm.com/web/user/ajax_get_my_info"

HEADERS = {
    "Host": "user-api.smzdm.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "smzdm_android_V10.4.1 rv:841 (22021211RC;Android12;zh)smzdmapp",
}

SIGN_KEY = "apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"


def get_cookie() -> str:
    """从环境变量获取 cookie"""
    cookie = os.environ.get("SMZDM_COOKIE")
    if not cookie:
        log_error("错误: 未配置环境变量 SMZDM_COOKIE")
        return None
    return cookie


def robot_token(cookie: str) -> str:
    """获取机器人 token"""
    ts = round(time.time() * 1000)
    headers = HEADERS.copy()
    headers["Cookie"] = cookie

    data = {
        "f": "android",
        "v": "10.4.1",
        "weixin": 1,
        "time": ts,
        "sign": hashlib.md5(
            f"f=android&time={ts}&v=10.4.1&weixin=1&key={SIGN_KEY}".encode("utf-8")
        )
        .hexdigest()
        .upper(),
    }

    resp = None
    try:
        resp = requests.post(url=TOKEN_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result["data"]["token"]
    except Exception as e:
        log_warning(f"获取 token 失败: {e}")
        # 记录接口返回的完整内容，便于排查签名失效/风控等原因
        log_response_detail(resp)
        return None


def sign(cookie: str, token: str) -> tuple:
    """执行签到

    返回 (error_code, error_msg, data, result)
    - error_code: 0=成功, 其他=失败/已签到
    - data: 本次请求参数（/checkin/all_reward 需要复用同一套 token/sk/sign）
    - result: 接口原始返回，用于奖励缺失时输出原文排查
    """
    time_stamp = round(time.time() * 1000)
    headers = HEADERS.copy()
    headers["Cookie"] = cookie

    data = {
        "f": "android",
        "v": "10.4.1",
        "sk": "ierkM0OZZbsuBKLoAgQ6OJneLMXBQXmzX+LXkNTuKch8Ui2jGlahuFyWIzBiDq/L",
        "weixin": 1,
        "time": time_stamp,
        "token": token,
        "sign": hashlib.md5(
            f"f=android&sk=ierkM0OZZbsuBKLoAgQ6OJneLMXBQXmzX+LXkNTuKch8Ui2jGlahuFyWIzBiDq/L&time={time_stamp}&token={token}&v=10.4.1&weixin=1&key={SIGN_KEY}".encode(
                "utf-8"
            )
        )
        .hexdigest()
        .upper(),
    }

    resp = None
    try:
        resp = requests.post(url=CHECKIN_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        # 站点以字符串返回 error_code（如 "0"），必须归一化后再判断成功
        try:
            error_code = int(result.get("error_code", -1))
        except (TypeError, ValueError):
            error_code = -1
        return (
            error_code,
            result.get("error_msg", "未知响应"),
            data,
            result,
        )
    except Exception as e:
        # 记录接口返回的完整内容，便于排查签到失败原因
        log_response_detail(resp)
        return -1, f"签到请求失败: {e}", None, None


def get_all_reward(cookie: str, data: dict) -> list:
    """获取签到奖励信息"""
    headers = HEADERS.copy()
    headers["Cookie"] = cookie

    resp = None
    try:
        resp = requests.post(
            url=f"{BASE_URL}/checkin/all_reward", headers=headers, data=data, timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        log_warning(f"获取奖励信息失败: {e}")
        log_response_detail(resp)
        return []

    normal_reward = (result.get("data") or {}).get("normal_reward") or {}
    if not normal_reward:
        log_debug("无 normal_reward 字段，跳过奖励解析")
        return []

    # reward_add 仅在首次签到时存在；已签到时只有 sub_title
    reward_add = normal_reward.get("reward_add") or {}
    msgs = []
    if reward_add.get("content"):
        msgs.append({"name": "签到奖励", "value": reward_add["content"]})
    elif reward_add:
        log_debug(f"reward_add 结构异常: {reward_add}")
    if normal_reward.get("sub_title"):
        msgs.append({"name": "连续签到", "value": normal_reward["sub_title"]})
    return msgs


def get_user_info(cookie: str):
    """获取用户信息（昵称、等级、金币、碎银）

    调用用户中心网页使用的 JSON 接口；返回 None 表示不可用，调用方不得用
    占位值冒充，用户信息失败不影响签到与退出码。
    """
    headers = {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.smzdm.com/user/",
    }

    resp = None
    try:
        resp = requests.get(
            url=USER_INFO_URL, headers=headers, timeout=30, allow_redirects=False
        )
        if resp.is_redirect or 300 <= resp.status_code < 400:
            location = resp.headers.get("Location", "")
            log_warning(f"获取用户信息失败: 接口重定向 -> {location}")
            log_response_detail(f"HTTP {resp.status_code} redirect -> {location}")
            return None
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        log_warning(f"获取用户信息失败: {e}")
        log_response_detail(resp)
        return None

    try:
        error_code = int(payload.get("error_code", -1))
    except (TypeError, ValueError):
        error_code = -1

    data = payload.get("data") or {}
    user = data.get("user") or {}
    wallet = data.get("wallet") or {}
    level_match = re.search(r"/level/(\d+)\.png", str(user.get("level_icon") or ""))
    user_info = {
        "name": "" if user.get("nickname") is None else str(user.get("nickname")).strip(),
        "level": level_match.group(1) if level_match else "",
        "gold": "" if wallet.get("gold") is None else str(wallet.get("gold")).strip(),
        "silver": "" if wallet.get("silver") is None else str(wallet.get("silver")).strip(),
    }

    if error_code == 0 and all(user_info.values()):
        return user_info

    log_warning(f"用户信息不可用: {payload.get('error_msg') or '接口未返回完整用户数据'}")
    log_response_detail(resp)
    return None


def main() -> int:
    """主函数"""
    log_info("什么值得买签到任务开始")

    cookie = get_cookie()
    if not cookie:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    # 获取用户信息（不可用时如实标注，不用占位值冒充）
    log_info("获取用户信息...")
    user_info = get_user_info(cookie)
    if user_info:
        log_info(
            "用户信息:\n"
            f"  昵称: {user_info['name']}\n"
            f"  等级: {user_info['level']}\n"
            f"  金币: {user_info['gold']}\n"
            f"  碎银: {user_info['silver']}"
        )
    else:
        log_warning("用户信息不可用：已跳过金币/碎银展示与签到后复核")

    # 获取 token
    log_info("获取签到 token...")
    token = robot_token(cookie)
    if not token:
        log_error("无法获取 token，签到失败")
        return 1

    # 执行签到
    log_info("执行签到...")
    error_code, error_msg, data, result = sign(cookie, token)

    # error_msg 是站点原文（如「签到成功，+0积分」），附上 error_code 才能区分成功与已签到
    if error_code == 0:
        log_info(f"{error_msg} (error_code={error_code})")
    else:
        log_warning(f"{error_msg} (error_code={error_code})")

    # error_code == 0 表示签到成功；其他情况（已签到、重复签到等）跳过奖励查询
    if error_code == 0 and data:
        reward_msgs = get_all_reward(cookie, data)
        if reward_msgs:
            for msg in reward_msgs:
                log_info(f"{msg['name']}: {msg['value']}")
        else:
            # 奖励为空时输出签到接口原文，用于确认「+0积分」是站点文案还是解析失效
            log_response_detail(result, keyword="reward")

    # 签到后复核资产：仅在签到前拿到用户信息时才请求，且只在两次都成功时输出对比
    if user_info:
        after_info = get_user_info(cookie)
        if after_info:
            log_info(
                "资产变动: "
                f"金币 {user_info['gold']} -> {after_info['gold']}，"
                f"碎银 {user_info['silver']} -> {after_info['silver']}"
            )
        else:
            log_warning("资产变动: 不可用（签到后用户信息获取失败）")
    else:
        log_warning("资产变动: 不可用（签到前用户信息获取失败，已跳过复核）")

    log_success("任务完成")
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
