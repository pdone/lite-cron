#!/usr/bin/env python3
"""
百度贴吧自动签到任务

功能：
- 自动签到所有关注的贴吧
- 显示签到统计信息

环境变量：
- TIEBA_COOKIE: 登录 cookie，需包含 BDUSS（必需）
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

import random
import hashlib
import time
import requests
from datetime import datetime
from typing import Optional


# 配置常量
TBS_URL = "http://tieba.baidu.com/dc/common/tbs"
LIKE_URL = "http://c.tieba.baidu.com/c/f/forum/like"
SIGN_URL = "http://c.tieba.baidu.com/c/c/forum/sign"
USER_INFO_URL = "https://zhidao.baidu.com/api/loginInfo"
SIGN_KEY = "tiebaclient!!!"

HEADERS = {
    "Host": "tieba.baidu.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36",
    "Connection": "keep-alive",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
}

SIGN_DATA = {
    "_client_type": "2",
    "_client_version": "9.7.8.0",
    "_phone_imei": "000000000000000",
    "model": "MI+5",
    "net_type": "1",
}


def get_cookie() -> tuple:
    """从环境变量获取 cookie，返回 (cookie_str, bduss)"""
    cookie = os.environ.get("TIEBA_COOKIE")
    if not cookie:
        log_error("错误: 未配置环境变量 TIEBA_COOKIE")
        return None, None

    # 解析 BDUSS
    cookie_dict = {}
    for item in cookie.split("; "):
        if "=" in item:
            key, value = item.split("=", 1)
            cookie_dict[key.strip()] = value.strip()

    bduss = cookie_dict.get("BDUSS")
    if not bduss:
        log_error("错误: Cookie 中未找到 BDUSS")
        return None, None

    return cookie, bduss


def request_with_retry(
    session: requests.Session,
    url: str,
    method: str = "get",
    data: Optional[dict] = None,
    retry: int = 3,
) -> dict:
    """带重试的请求"""
    last_response = None
    for i in range(retry):
        try:
            if method.lower() == "get":
                response = session.get(url, timeout=10)
            else:
                response = session.post(url, data=data, timeout=10)
            last_response = response

            response.raise_for_status()
            if not response.text.strip():
                raise ValueError("空响应内容")

            return response.json()
        except Exception as e:
            if i == retry - 1:
                # 记录最后一次站点返回的完整内容，便于排查签名失败/风控/空响应
                log_response_detail(last_response)
                raise Exception(f"请求失败: {e}")

            wait_time = 1.5 * (2**i) + random.uniform(0, 1)
            time.sleep(wait_time)

    raise Exception(f"请求失败，已达最大重试次数 {retry}")


def encode_data(data: dict) -> dict:
    """生成签名"""
    s = ""
    for key in sorted(data.keys()):
        s += f"{key}={data[key]}"
    sign = hashlib.md5((s + SIGN_KEY).encode("utf-8")).hexdigest().upper()
    data.update({"sign": sign})
    return data


def get_user_info(session: requests.Session) -> tuple:
    """获取用户信息和 tbs"""
    try:
        result = request_with_retry(session, TBS_URL)
        if result.get("is_login", 0) == 0:
            return None, "登录失败，Cookie 异常"

        tbs = result.get("tbs", "")

        try:
            user_info = request_with_retry(session, USER_INFO_URL)
            user_name = user_info.get("userName", "未知用户")
        except Exception:
            user_name = "未知用户"

        return tbs, user_name
    except Exception as e:
        return None, f"登录验证异常: {e}"


def get_favorite_forums(session: requests.Session, bduss: str) -> list:
    """获取关注的贴吧列表"""
    forums = []
    page_no = 1

    while True:
        data = {
            "BDUSS": bduss,
            "_client_type": "2",
            "_client_id": "wappc_1534235498291_488",
            "_client_version": "9.7.8.0",
            "_phone_imei": "000000000000000",
            "from": "1008621y",
            "page_no": str(page_no),
            "page_size": "200",
            "model": "MI+5",
            "net_type": "1",
            "timestamp": str(int(time.time())),
            "vcode_tag": "11",
        }
        data = encode_data(data)

        try:
            res = request_with_retry(session, LIKE_URL, "post", data)

            if "forum_list" in res:
                for forum_type in ["non-gconforum", "gconforum"]:
                    if forum_type in res["forum_list"]:
                        items = res["forum_list"][forum_type]
                        if isinstance(items, list):
                            forums.extend(items)
                        elif isinstance(items, dict):
                            forums.append(items)

            if res.get("has_more") != "1":
                break

            page_no += 1
            time.sleep(random.uniform(1, 2))

        except Exception as e:
            log_warning(f"获取贴吧列表出错: {e}")
            break

    log_info(f"共获取到 {len(forums)} 个关注的贴吧")
    return forums


def sign_forums(session: requests.Session, forums: list, bduss: str, tbs: str) -> dict:
    """签到所有贴吧"""
    success_count = error_count = exist_count = shield_count = 0
    total = len(forums)

    log_info(f"开始签到 {total} 个贴吧")
    last_request_time = time.time()

    for idx, forum in enumerate(forums):
        # 计算延迟
        elapsed = time.time() - last_request_time
        delay = max(0, 1.0 + random.uniform(0.5, 1.5) - elapsed)
        time.sleep(delay)
        last_request_time = time.time()

        # 每 10 个贴吧休息一段时间
        if (idx + 1) % 10 == 0:
            extra_delay = random.uniform(5, 10)
            log_info(f"已签到 {idx + 1}/{total} 个贴吧，休息 {extra_delay:.2f} 秒")
            time.sleep(extra_delay)

        forum_name = forum.get("name", "")
        forum_id = forum.get("id", "")
        log_prefix = f"【{forum_name}】({idx + 1}/{total})"

        try:
            data = SIGN_DATA.copy()
            data.update(
                {
                    "BDUSS": bduss,
                    "fid": forum_id,
                    "kw": forum_name,
                    "tbs": tbs,
                    "timestamp": str(int(time.time())),
                }
            )
            data = encode_data(data)

            result = request_with_retry(session, SIGN_URL, "post", data)
            error_code = result.get("error_code", "")

            if error_code == "0":
                success_count += 1
                rank = result.get("user_info", {}).get("user_sign_rank", "未知")
                log_success(f"{log_prefix} 签到成功，第{rank}个签到")
            elif error_code == "160002":
                exist_count += 1
                log_info(f'{log_prefix} {result.get("error_msg", "今日已签到")}')
            elif error_code == "340006":
                shield_count += 1
                log_error(f"{log_prefix} 贴吧已被屏蔽")
            else:
                error_count += 1
                log_error(
                    f'{log_prefix} 签到失败: {result.get("error_msg", "未知错误")}'
                )

        except Exception as e:
            error_count += 1
            log_error(f"{log_prefix} 签到异常: {e}")

    return {
        "total": total,
        "success": success_count,
        "exist": exist_count,
        "shield": shield_count,
        "error": error_count,
    }


def main() -> int:
    """主函数"""
    # start_time = datetime.now()
    # start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')

    log_info("百度贴吧签到任务开始")

    # 获取 cookie
    cookie, bduss = get_cookie()
    if not cookie or not bduss:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    # 创建会话
    session = requests.Session()
    session.headers.update(HEADERS)
    cookie_dict = {
        item.split("=")[0]: item.split("=")[1]
        for item in cookie.split("; ")
        if "=" in item
    }
    requests.utils.add_dict_to_cookiejar(session.cookies, cookie_dict)

    # 验证登录
    log_info("验证登录状态...")
    tbs, user_name = get_user_info(session)
    if not tbs:
        log_error(f"{user_name}")
        return 1
    log_success(f"登录成功，用户: {user_name}")

    # 获取贴吧列表
    log_info("获取关注列表...")
    forums = get_favorite_forums(session, bduss)

    if not forums:
        log_warning("未获取到任何贴吧，跳过签到")
        return 0

    # 签到
    stats = sign_forums(session, forums, bduss, tbs)

    # 记录结束时间
    # end_time = datetime.now()
    # end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    # duration = (end_time - start_time).total_seconds()

    stats_msg = (
        f"签到统计:\n"
        f'  总数: {stats["total"]}\n'
        f'  成功: {stats["success"]}\n'
        f'  已签: {stats["exist"]}\n'
        f'  屏蔽: {stats["shield"]}\n'
        f'  失败: {stats["error"]}'
    )
    log_info(stats_msg)

    return 0 if stats["error"] == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
