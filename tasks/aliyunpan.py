#!/usr/bin/env python3
"""
阿里云盘自动签到任务

功能：
- 自动签到阿里云盘
- 获取签到奖励

环境变量：
- ALIYUN_REFRESH_TOKEN: 阿里云盘 refresh token（必需）
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

import requests
from datetime import datetime


# 配置常量
TOKEN_URL = "https://auth.aliyundrive.com/v2/account/token"
SIGN_LIST_URL = "https://member.aliyundrive.com/v1/activity/sign_in_list"
SIGN_REWARD_URL = "https://member.aliyundrive.com/v1/activity/sign_in_reward"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def get_refresh_token() -> str:
    """从环境变量获取 refresh token"""
    token = os.environ.get("ALIYUN_REFRESH_TOKEN")
    if not token:
        log_error("错误: 未配置环境变量 ALIYUN_REFRESH_TOKEN")
        return None
    return token


def update_token(refresh_token: str) -> str:
    """使用 refresh token 获取 access token"""
    response = None
    try:
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        response = requests.post(TOKEN_URL, json=data, headers=HEADERS, timeout=30)
        response.raise_for_status()
        result = response.json()

        access_token = result.get("access_token")
        if access_token:
            log_success("Token 刷新成功")
            return access_token
        else:
            error_msg = result.get("message", "未知错误")
            log_error(f"Token 刷新失败: {error_msg}")
            # 记录接口返回的完整内容，便于排查 refresh token 失效等原因
            log_response_detail(response)
            return None
    except Exception as e:
        log_error(f"Token 刷新请求失败: {e}")
        log_response_detail(response)
        return None


def sign(access_token: str) -> list:
    """执行签到"""
    response = None
    try:
        headers = HEADERS.copy()
        headers["Authorization"] = access_token

        # 获取签到列表
        response = requests.post(SIGN_LIST_URL, headers=headers, json={}, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "result" not in result:
            log_warning(f"响应异常: {result}")
            # 记录接口返回的完整内容，便于排查签到异常
            log_response_detail(response)
            return [{"name": "签到结果", "value": "接口响应异常"}]

        sign_result = result["result"]
        sign_days = sign_result.get("signInCount", 0)

        # 领取奖励
        data = {"signInDay": sign_days}
        requests.post(SIGN_REWARD_URL, headers=headers, json=data, timeout=30)

        # 查找今天签到状态
        msg = []
        sign_logs = sign_result.get("signInLogs", [])
        today_log = None

        for log in sign_logs:
            if log.get("status") == "miss":
                # 找到了第一个未签到的，说明前一个是今天
                idx = sign_logs.index(log)
                if idx > 0:
                    today_log = sign_logs[idx - 1]
                break

        if today_log:
            is_reward = today_log.get("isReward", False)
            if is_reward:
                reward = today_log.get("reward", {})
                reward_name = reward.get("name", "未知奖励")
                reward_desc = reward.get("description", "")
                msg = [
                    {"name": "累计签到", "value": sign_days},
                    {"name": "今日奖励", "value": f"{reward_name} {reward_desc}"},
                ]
            else:
                msg = [
                    {"name": "累计签到", "value": sign_days},
                    {"name": "今日奖励", "value": "签到成功，今日无额外奖励"},
                ]
        else:
            # 可能全部签到了或今天已签
            msg = [
                {"name": "累计签到", "value": sign_days},
                {"name": "签到结果", "value": "今日已签到"},
            ]

        return msg

    except Exception as e:
        # 记录接口返回的完整内容，便于排查签到失败原因
        log_response_detail(response)
        return [{"name": "签到结果", "value": f"签到失败: {e}"}]


def main() -> int:
    """主函数"""
    # start_time = datetime.now()
    # start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')

    log_info("阿里云盘签到任务开始")

    refresh_token = get_refresh_token()
    if not refresh_token:
        log_info("任务终止: 未配置有效凭据")
        return 1

    # 获取 access token
    log_info("刷新 Access Token...")
    access_token = update_token(refresh_token)
    if not access_token:
        log_error("Token 刷新失败，无法签到")
        return 1

    # 执行签到
    msg_list = sign(access_token)
    if msg_list:
        lines = [f"  {msg['name']}: {msg['value']}" for msg in msg_list]
        log_info("执行签到..." + "\n".join(lines))

    # 记录结束时间
    # end_time = datetime.now()
    # end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    # duration = (end_time - start_time).total_seconds()

    log_success("任务完成")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
