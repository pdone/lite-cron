#!/usr/bin/env python3
"""
什么值得买 (SMZDM) 自动签到任务

功能：
- 自动签到获取奖励
- 显示金币、碎银、等级信息

环境变量：
- SMZDM_COOKIE: 登录 cookie（必需）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

import re
import hashlib
import time
import requests


# 配置常量
BASE_URL = "https://user-api.smzdm.com"
CHECKIN_URL = f"{BASE_URL}/checkin"
TOKEN_URL = f"{BASE_URL}/robot/token"
USER_URL = "https://zhiyou.smzdm.com/user/"

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

    try:
        resp = requests.post(url=TOKEN_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result["data"]["token"]
    except Exception as e:
        log_warning(f"获取 token 失败: {e}")
        return None


def sign(cookie: str, token: str) -> tuple:
    """执行签到

    返回 (error_code, error_msg, data)
    - error_code: 0=成功, 其他=失败/已签到
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

    try:
        resp = requests.post(url=CHECKIN_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return (
            result.get("error_code", -1),
            result.get("error_msg", "未知响应"),
            data,
        )
    except Exception as e:
        return -1, f"签到请求失败: {e}", None


def get_all_reward(cookie: str, data: dict) -> list:
    """获取签到奖励信息"""
    headers = HEADERS.copy()
    headers["Cookie"] = cookie

    try:
        resp = requests.post(
            url=f"{BASE_URL}/checkin/all_reward", headers=headers, data=data, timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        log_warning(f"获取奖励信息失败: {e}")
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


def get_user_info(cookie: str) -> dict:
    """获取用户信息（金币、碎银、等级）"""
    headers = {
        "Host": "zhiyou.smzdm.com",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148/smzdm 10.4.6 rv:130.1 (iPhone 13; iOS 15.6; zh_CN)/iphone_smzdmapp/10.4.6/wkwebview/jsbv_1.0.0",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "Referer": "https://m.smzdm.com/",
    }

    try:
        resp = requests.get(url=USER_URL, headers=headers, timeout=30)
        resp.raise_for_status()
        html = resp.text

        # 解析用户信息
        name_match = re.search(
            r'<a href="https://zhiyou.smzdm.com/user"> (.*?) </a>', html, re.S
        )
        level_match = re.search(
            r'<img src="https://res.smzdm.com/h5/h5_user/dist/assets/level/(.*?)\.png',
            html,
            re.S,
        )
        gold_match = re.search(
            r'<div class="assets-part assets-gold">\s*<span class="assets-part-element assets-num">(.*?)</span>',
            html,
            re.S,
        )
        silver_match = re.search(
            r'<div class="assets-part assets-prestige">\s*<span class="assets-part-element assets-num">(.*?)</span>',
            html,
            re.S,
        )

        return {
            "name": name_match.group(1).strip() if name_match else "未知用户",
            "level": level_match.group(1).strip() if level_match else "未知",
            "gold": gold_match.group(1).strip() if gold_match else "0",
            "silver": silver_match.group(1).strip() if silver_match else "0",
        }
    except Exception as e:
        log_warning(f"获取用户信息失败: {e}")
        return {"name": "未知用户", "level": "未知", "gold": "0", "silver": "0"}


def main() -> int:
    """主函数"""
    log_info("什么值得买签到任务开始")

    cookie = get_cookie()
    if not cookie:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    # 获取用户信息
    log_info("获取用户信息...")
    user_info = get_user_info(cookie)
    log_info(
        "用户信息:\n"
        f"  昵称: {user_info['name']}\n"
        f"  等级: {user_info['level']}\n"
        f"  金币: {user_info['gold']}\n"
        f"  碎银: {user_info['silver']}"
    )

    # 获取 token
    log_info("获取签到 token...")
    token = robot_token(cookie)
    if not token:
        log_error("无法获取 token，签到失败")
        return 1

    # 执行签到
    log_info("执行签到...")
    error_code, error_msg, data = sign(cookie, token)
    log_info(error_msg)

    # error_code == 0 表示签到成功；其他情况（已签到、重复签到等）跳过奖励查询
    if error_code == 0 and data:
        reward_msgs = get_all_reward(cookie, data)
        for msg in reward_msgs:
            log_info(f"{msg['name']}: {msg['value']}")

    log_success("任务完成")
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
