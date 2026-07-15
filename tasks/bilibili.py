#!/usr/bin/env python3
"""
Bilibili 自动签到任务 v2

基于 https://github.com/XiaoYiWeio/bili-checkin 改造，适配 LiteCron 框架。
相比原 bilibili.py 的主要改进：
- 从 BILIBILI_COOKIE 中提取 SESSDATA + bili_jct 双字段独立使用，规避 cookie
  字符串分隔符差异导致的 CSRF 解析失败问题
- 通过 /x/member/web/exp/reward 预检查任务状态，已完成任务自动跳过
- 观看任务改用 popular 接口获取视频（含真实 cid）+ heartbeat 心跳上报，
  解决原脚本 cid=0 导致观看任务必失败的问题
- 大会员判定基于 vipStatus（生效中），覆盖月度/年度两种类型
- 移除已下线的直播区签到接口
- 所有响应统一 None 安全处理，避免 'NoneType' object has no attribute 'get'

环境变量（与原 bilibili.py 保持兼容）:
- BILIBILI_COOKIE: B站登录 Cookie（必需，需包含 SESSDATA 和 bili_jct）
- COIN_NUM: 每日投币数量（默认 5）
- SILVER2COIN: 是否兑换银瓜子为硬币（true/false，默认 false）
- RECEIVE_VIP_PRIVILEGE: 是否领取大会员权益（true/false，默认 false）
- SKIP_SHARE: 是否跳过分享任务（true/false，默认 false）
- SKIP_COIN: 是否跳过投币任务（true/false，默认 false，节省硬币）
- LIVE_ROOM_DANMU: 直播间弹幕签到 room_id，多个用逗号分隔（可选）
- LIVE_DANMU_MSG: 弹幕内容（默认 "签到"）

依赖:
- requests
"""

import os
import sys
import json
import time
import random
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug


# ============ 常量 ============

BASE_URL = "https://api.bilibili.com"
LIVE_URL = "https://api.live.bilibili.com"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ============ Cookie 解析 ============

def parse_cookie_fields(cookie_str: str) -> tuple:
    """
    从完整 Cookie 字符串中提取 SESSDATA 和 bili_jct

    兼容分隔符 ';' 和 '; '，以及行首行尾空白。

    Args:
        cookie_str: Cookie 字符串，格式: key1=value1; key2=value2

    Returns:
        tuple: (sessdata, bili_jct)，未找到返回空字符串
    """
    sessdata = ""
    bili_jct = ""

    if not cookie_str:
        return sessdata, bili_jct

    # 统一分割：先按 ; 分割，再 strip 空白
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "SESSDATA":
            sessdata = value
        elif key == "bili_jct":
            bili_jct = value

    return sessdata, bili_jct


def make_headers(sessdata: str, bili_jct: str, referer: str = "https://www.bilibili.com") -> dict:
    """构造请求头，仅携带 SESSDATA 和 bili_jct 两个字段"""
    return {
        "User-Agent": UA,
        "Cookie": f"SESSDATA={sessdata}; bili_jct={bili_jct}",
        "Referer": referer,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


# ============ HTTP 工具 ============

def http_get(url: str, headers: dict, timeout: int = 15) -> dict:
    """GET 请求，返回解析后的 JSON dict，异常时返回 {"code": -1, "message": ...}"""
    try:
        resp = requests.get(url=url, headers=headers, timeout=timeout)
        return resp.json()
    except requests.exceptions.HTTPError as e:
        return {"code": -1, "message": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"code": -1, "message": str(e)}


def http_post(url: str, data: dict, headers: dict, timeout: int = 15) -> dict:
    """POST 请求（表单编码），返回解析后的 JSON dict"""
    headers = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(url=url, data=data, headers=headers, timeout=timeout)
        return resp.json()
    except requests.exceptions.HTTPError as e:
        return {"code": -1, "message": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"code": -1, "message": str(e)}


# ============ 任务接口 ============

def get_user_info(sessdata: str, bili_jct: str) -> dict:
    """获取用户导航信息

    Returns:
        dict: 包含 uid/name/level/current_exp/next_exp/coins/is_login/vip_type/vip_status
    """
    url = f"{BASE_URL}/x/web-interface/nav"
    headers = make_headers(sessdata, bili_jct)
    resp = http_get(url, headers)
    if not resp or resp.get("code") != 0:
        return {"is_login": False}
    data = resp.get("data") or {}
    level_info = data.get("level_info") or {}
    return {
        "uid": data.get("mid"),
        "name": data.get("uname"),
        "level": level_info.get("current_level"),
        "current_exp": level_info.get("current_exp"),
        "next_exp": level_info.get("next_exp", 0),
        "coins": data.get("money", 0),
        "is_login": data.get("isLogin", False),
        "vip_type": data.get("vipType", 0),
        "vip_status": data.get("vipStatus", 0),
    }


def is_vip(user: dict) -> bool:
    """判断是否为有效大会员

    B站 nav 接口字段含义：
    - vipType: 0=无, 1=月度大会员, 2=年度大会员
    - vipStatus: 0=未生效/已过期, 1=生效中

    只要 vipStatus=1 即视为有效大会员（不论月度/年度）。
    """
    return user.get("vip_status") == 1


def check_reward(sessdata: str, bili_jct: str) -> dict:
    """查询今日任务完成状态

    Returns:
        dict: {login, watch, share, coins}
    """
    url = f"{BASE_URL}/x/member/web/exp/reward"
    headers = make_headers(sessdata, bili_jct, "https://account.bilibili.com/")
    resp = http_get(url, headers)
    if not resp or resp.get("code") != 0:
        return {}
    data = resp.get("data") or {}
    return {
        "login": data.get("login", False),
        "watch": data.get("watch", data.get("watch_av", False)),
        "share": data.get("share", data.get("share_av", False)),
        "coins": data.get("coins", data.get("coins_av", 0)),
    }


def get_popular_videos(sessdata: str, bili_jct: str, count: int = 20) -> list:
    """获取热门视频列表（含完整 aid/bvid/cid/title/duration）"""
    url = f"{BASE_URL}/x/web-interface/popular?ps={count}&pn=1"
    headers = make_headers(sessdata, bili_jct)
    resp = http_get(url, headers)
    if not resp or resp.get("code") != 0:
        return []
    items = (resp.get("data") or {}).get("list") or []
    return [
        {
            "aid": v.get("aid"),
            "bvid": v.get("bvid"),
            "cid": v.get("cid"),
            "title": v.get("title", ""),
            "duration": v.get("duration", 100),
        }
        for v in items
        if v.get("aid")
    ]


def pick_video(sessdata: str, bili_jct: str) -> dict:
    """从热门视频中随机挑选一个"""
    videos = get_popular_videos(sessdata, bili_jct)
    if not videos:
        return {}
    return random.choice(videos)


def do_watch(sessdata: str, bili_jct: str) -> dict:
    """模拟观看视频（heartbeat 心跳上报），+5 EXP

    使用 popular 接口返回的真实 cid，解决原脚本 cid=0 必失败的问题。
    """
    video = pick_video(sessdata, bili_jct)
    if not video:
        return {"success": False, "message": "无法获取视频列表"}

    url = f"{BASE_URL}/x/click-interface/web/heartbeat"
    duration = video.get("duration") or 100
    played = random.randint(10, min(duration, 300))
    data = {
        "aid": str(video["aid"]),
        "cid": str(video["cid"]),
        "bvid": video.get("bvid", ""),
        "mid": "",
        "csrf": bili_jct,
        "played_time": str(played),
        "real_played_time": str(played),
        "realtime": str(duration),
        "start_ts": str(int(time.time())),
        "type": "3",
        "dt": "2",
        "play_type": "1",
    }
    headers = make_headers(sessdata, bili_jct, f"https://www.bilibili.com/video/{video.get('bvid', '')}")
    resp = http_post(url, data, headers)
    if resp and resp.get("code") == 0:
        return {"success": True, "exp": 5, "video": video["title"]}
    return {"success": False, "message": resp.get("message", "未知错误") if resp else "请求失败"}


def do_share(sessdata: str, bili_jct: str) -> dict:
    """分享视频，+5 EXP"""
    video = pick_video(sessdata, bili_jct)
    if not video:
        return {"success": False, "message": "无法获取视频列表"}

    url = f"{BASE_URL}/x/web-interface/share/add"
    data = {
        "aid": str(video["aid"]),
        "bvid": video.get("bvid", ""),
        "csrf": bili_jct,
    }
    headers = make_headers(sessdata, bili_jct)
    resp = http_post(url, data, headers)
    if resp and resp.get("code") == 0:
        return {"success": True, "exp": 5, "video": video["title"]}
    # 部分情况下 code 非 0 但实际已分享成功
    msg = resp.get("message", "未知错误") if resp else "请求失败"
    if "重复" in msg or "已分享" in msg:
        return {"success": True, "exp": 0, "video": video["title"], "message": "今日已分享"}
    return {"success": False, "message": msg}


def do_coin(sessdata: str, bili_jct: str, count: int) -> dict:
    """投币任务，每枚 +10 EXP，最多 5 枚 = 50 EXP

    通过预检查的 coins 字段计算还需投币数量，避免超投。
    """
    results = []
    success_count = 0
    total_exp = 0

    for i in range(count):
        video = pick_video(sessdata, bili_jct)
        if not video:
            results.append({"index": i + 1, "success": False, "message": "无法获取视频"})
            continue

        url = f"{BASE_URL}/x/web-interface/coin/add"
        data = {
            "aid": str(video["aid"]),
            "bvid": video.get("bvid", ""),
            "multiply": "1",
            "select_like": "1",
            "csrf": bili_jct,
        }
        headers = make_headers(sessdata, bili_jct)
        resp = http_post(url, data, headers)

        if resp and resp.get("code") == 0:
            success_count += 1
            total_exp += 10
            results.append({"index": i + 1, "success": True, "video": video["title"]})
        else:
            msg = resp.get("message", "未知错误") if resp else "请求失败"
            code = resp.get("code") if resp else -1
            results.append({"index": i + 1, "success": False, "message": msg, "code": code})
            # 34005: 达到上限；-104: 硬币不足；-111: CSRF 失效
            if code in (34005, -104, -111):
                break

        if i < count - 1:
            time.sleep(random.uniform(1.0, 3.0))

    return {
        "success": success_count > 0,
        "exp": total_exp,
        "count": success_count,
        "target": count,
        "details": results,
    }


def do_live_danmu(sessdata: str, bili_jct: str, room_id: int, msg: str) -> dict:
    """直播间弹幕签到（发送一条弹幕）"""
    url = f"{LIVE_URL}/msg/send"
    data = {
        "bubble": "0",
        "msg": msg,
        "color": "16777215",
        "mode": "1",
        "room_type": "0",
        "jumpfrom": "0",
        "reply_mid": "0",
        "reply_attr": "0",
        "replay_dmid": "",
        "statistics": json.dumps({"appId": 100, "platform": 5}),
        "fontsize": "25",
        "rnd": str(int(time.time())),
        "roomid": str(room_id),
        "csrf": bili_jct,
        "csrf_token": bili_jct,
    }
    headers = make_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room_id}")
    headers["Origin"] = "https://live.bilibili.com"
    resp = http_post(url, data, headers)
    if resp and resp.get("code") == 0:
        return {"success": True, "room_id": room_id, "msg": msg}
    err_msg = resp.get("message", resp.get("msg", "未知错误")) if resp else "请求失败"
    return {"success": False, "room_id": room_id, "msg": msg, "message": err_msg}


def get_vip_privilege_list(sessdata: str, bili_jct: str) -> dict:
    """获取大会员权益列表"""
    url = f"{BASE_URL}/x/vip/privilege/my"
    headers = make_headers(sessdata, bili_jct)
    resp = http_get(url, headers)
    if not resp or resp.get("code") != 0:
        return {}
    return resp


def receive_vip_privilege(sessdata: str, bili_jct: str, receive_type: int) -> dict:
    """领取大会员权益"""
    url = f"{BASE_URL}/x/vip/privilege/receive"
    data = {"type": receive_type, "csrf": bili_jct}
    headers = make_headers(sessdata, bili_jct)
    return http_post(url, data, headers)


def silver2coin(sessdata: str, bili_jct: str) -> dict:
    """银瓜子换硬币"""
    url = f"{LIVE_URL}/xlive/revenue/v1/wallet/silver2coin"
    data = {"csrf": bili_jct}
    headers = make_headers(sessdata, bili_jct, "https://live.bilibili.com")
    return http_post(url, data, headers)


def get_wallet_status(sessdata: str, bili_jct: str) -> dict:
    """获取钱包状态（硬币/金瓜子/银瓜子）"""
    url = f"{LIVE_URL}/pay/v1/Exchange/getStatus"
    headers = make_headers(sessdata, bili_jct)
    resp = http_get(url, headers)
    if not resp or resp.get("code") != 0:
        return {}
    return resp.get("data") or {}


# ============ 配置 ============

def get_config() -> dict:
    """从环境变量获取配置

    与原 bilibili.py 保持兼容，新增 SKIP_COIN 和 LIVE_ROOM_DANMU 选项。
    """
    cookie = os.environ.get("BILIBILI_COOKIE", "")
    sessdata, bili_jct = parse_cookie_fields(cookie)

    def env_bool(key: str, default: str = "false") -> bool:
        return os.environ.get(key, default).lower() == "true"

    def env_int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, str(default)))
        except ValueError:
            return default

    live_rooms_raw = os.environ.get("LIVE_ROOM_DANMU", "").strip()
    live_rooms = []
    if live_rooms_raw:
        for r in live_rooms_raw.split(","):
            r = r.strip()
            if r.isdigit():
                live_rooms.append(int(r))

    return {
        "sessdata": sessdata,
        "bili_jct": bili_jct,
        "coin_num": env_int("COIN_NUM", 5),
        "silver2coin": env_bool("SILVER2COIN"),
        "receive_vip_privilege": env_bool("RECEIVE_VIP_PRIVILEGE"),
        "skip_share": env_bool("SKIP_SHARE"),
        "skip_coin": env_bool("SKIP_COIN"),
        "live_rooms": live_rooms,
        "live_danmu_msg": os.environ.get("LIVE_DANMU_MSG", "签到"),
    }


# ============ 主流程 ============

def run_all(config: dict) -> dict:
    """执行所有每日任务

    Returns:
        dict: 包含 user/tasks/total_exp/coin_status 等结果字段
    """
    sessdata = config["sessdata"]
    bili_jct = config["bili_jct"]

    # 1. 校验登录
    user = get_user_info(sessdata, bili_jct)
    if not user.get("is_login"):
        return {"error": "Cookie 无效或已过期（SESSDATA/bili_jct 缺失或失效）"}

    log_info(f"账号: {user['name']} (UID: {user['uid']})")
    log_info(f"当前等级: Lv{user['level']}  经验: {user['current_exp']}/{user['next_exp']}")
    log_info(f"当前硬币: {user['coins']}  大会员: {'是' if is_vip(user) else '否'}")

    # 2. 预检查任务状态
    status_before = check_reward(sessdata, bili_jct)
    if not status_before:
        log_warning("无法获取任务状态，将尝试执行所有任务")
        status_before = {"login": False, "watch": False, "share": False, "coins": 0}

    tasks = []
    total_exp = 0

    # 3. 登录任务（自动完成）
    if status_before.get("login"):
        tasks.append({"task": "login", "success": True, "exp": 0, "message": "今日已完成"})
        log_info("登录任务: 今日已完成")
    else:
        total_exp += 5
        tasks.append({"task": "login", "success": True, "exp": 5, "message": "登录奖励"})
        log_success("登录任务: +5 EXP")

    # 4. 观看任务
    if status_before.get("watch"):
        tasks.append({"task": "watch", "success": True, "exp": 0, "message": "今日已完成"})
        log_info("观看任务: 今日已完成")
    else:
        log_info("执行观看任务...")
        r = do_watch(sessdata, bili_jct)
        if r["success"]:
            total_exp += r["exp"]
            log_success(f"观看任务完成: +{r['exp']} EXP 《{r.get('video', '')}》")
        else:
            log_warning(f"观看任务失败: {r.get('message')}")
        tasks.append({"task": "watch", **r})
        time.sleep(random.uniform(1.0, 2.0))

    # 5. 分享任务
    if config["skip_share"]:
        tasks.append({"task": "share", "success": True, "exp": 0, "message": "已跳过"})
        log_info("分享任务: 已跳过")
    elif status_before.get("share"):
        tasks.append({"task": "share", "success": True, "exp": 0, "message": "今日已完成"})
        log_info("分享任务: 今日已完成")
    else:
        log_info("执行分享任务...")
        r = do_share(sessdata, bili_jct)
        if r["success"]:
            total_exp += r.get("exp", 0)
            log_success(f"分享任务完成: +{r.get('exp', 0)} EXP 《{r.get('video', '')}》")
        else:
            log_warning(f"分享任务失败: {r.get('message')}")
        tasks.append({"task": "share", **r})
        time.sleep(random.uniform(1.0, 2.0))

    # 6. 投币任务
    if config["skip_coin"]:
        tasks.append({"task": "coin", "success": True, "exp": 0, "count": 0, "target": config["coin_num"], "message": "已跳过"})
        log_info("投币任务: 已跳过")
    else:
        coins_done = status_before.get("coins", 0)
        if isinstance(coins_done, bool):
            coins_done = 50 if coins_done else 0
        remaining = max(0, config["coin_num"] - (coins_done // 10))

        if remaining == 0:
            tasks.append({"task": "coin", "success": True, "exp": 0, "count": 0, "target": config["coin_num"], "message": "今日已满"})
            log_info(f"投币任务: 今日已满 ({coins_done // 10}/{config['coin_num']})")
        else:
            log_info(f"投币任务: 今日已投 {coins_done // 10}，还需 {remaining} 枚")
            r = do_coin(sessdata, bili_jct, remaining)
            if r["success"]:
                total_exp += r["exp"]
                log_success(f"投币任务完成: {r['count']}/{r['target']} 枚，+{r['exp']} EXP")
            else:
                # 即使部分失败也记录详情
                if r["count"] > 0:
                    total_exp += r["exp"]
                    log_warning(f"投币任务部分失败: {r['count']}/{r['target']} 枚成功，+{r['exp']} EXP")
                else:
                    last = r["details"][-1] if r["details"] else {}
                    log_warning(f"投币任务失败: {last.get('message', '未知错误')}")
            tasks.append({"task": "coin", **r})

    # 7. 直播间弹幕签到（可选）
    if config["live_rooms"]:
        log_info(f"执行直播间弹幕签到（{len(config['live_rooms'])} 个房间）...")
        danmu_results = []
        for idx, room_id in enumerate(config["live_rooms"]):
            r = do_live_danmu(sessdata, bili_jct, room_id, config["live_danmu_msg"])
            if r["success"]:
                log_success(f"弹幕签到成功: 房间 {room_id}")
            else:
                log_warning(f"弹幕签到失败: 房间 {room_id} - {r.get('message')}")
            danmu_results.append(r)
            if idx < len(config["live_rooms"]) - 1:
                time.sleep(2)
        tasks.append({"task": "live_danmu", "success": all(r["success"] for r in danmu_results), "rooms": danmu_results})

    # 8. 大会员权益（可选）
    if config["receive_vip_privilege"]:
        if is_vip(user):
            log_info("检查大会员权益...")
            vip_ret = get_vip_privilege_list(sessdata, bili_jct)
            welfare_list = (vip_ret.get("data") or {}).get("list") or []
            received = 0
            for welfare in welfare_list:
                if welfare.get("state") == 0:
                    type_id = welfare.get("type")
                    r = receive_vip_privilege(sessdata, bili_jct, type_id)
                    if r.get("code") == 0:
                        received += 1
                        log_success(f"领取权益成功: 类型 {type_id}")
                    else:
                        log_warning(f"领取权益失败: {r.get('message', '未知错误')}")
            tasks.append({"task": "vip_privilege", "success": True, "received": received})
        else:
            log_info("非大会员，跳过权益领取")
            tasks.append({"task": "vip_privilege", "success": True, "message": "非大会员"})

    # 9. 银瓜子换硬币（可选）
    if config["silver2coin"]:
        log_info("执行银瓜子兑换...")
        r = silver2coin(sessdata, bili_jct)
        if r.get("code") == 0:
            log_success(f"兑换成功: {r.get('message', '')}")
        else:
            log_warning(f"兑换失败: {r.get('message', '未知错误')}")
        tasks.append({"task": "silver2coin", **r})

    # 10. 汇总状态
    wallet = get_wallet_status(sessdata, bili_jct)
    user_after = get_user_info(sessdata, bili_jct)

    return {
        "user": user,
        "user_after": user_after,
        "tasks": tasks,
        "total_exp": total_exp,
        "wallet": wallet,
    }


def format_result(result: dict) -> str:
    """格式化最终结果输出"""
    if "error" in result:
        return f"❌ {result['error']}"

    user = result["user"]
    user_after = result["user_after"]
    tasks = result["tasks"]
    total = result["total_exp"]
    wallet = result.get("wallet") or {}

    task_names = {
        "login": "登录",
        "watch": "观看",
        "share": "分享",
        "coin": "投币",
        "live_danmu": "弹幕签到",
        "vip_privilege": "会员权益",
        "silver2coin": "银瓜子兑换",
    }

    lines = [
        f"账号: {user['name']} (UID: {user['uid']})",
    ]

    for t in tasks:
        name = task_names.get(t.get("task"), t.get("task", ""))
        if t.get("success"):
            exp = t.get("exp", 0)
            extra = ""
            if t.get("video"):
                extra = f" 《{t['video'][:20]}》"
            elif t.get("message"):
                extra = f" ({t['message']})"
            elif t.get("text"):
                extra = f" ({t['text']})"
            elif t.get("count") is not None:
                extra = f" ({t['count']}/{t.get('target', 0)}枚)"
            if exp and exp > 0:
                lines.append(f"{name}: 成功 +{exp} EXP{extra}")
            else:
                lines.append(f"{name}: 成功{extra}")
        else:
            lines.append(f"{name}: 失败 ({t.get('message', '未知')})")

    lines.append(f"今日获得: +{total} EXP")
    lines.append(f"当前经验: {user_after.get('current_exp', 0)}/{user_after.get('next_exp', 0)}")

    if wallet:
        lines.append(f"硬币数量: {wallet.get('coin', 0)}")
        lines.append(f"金瓜子数: {wallet.get('gold', 0)}")
        lines.append(f"银瓜子数: {wallet.get('silver', 0)}")

    next_exp = user_after.get("next_exp", 0) or 1
    cur_exp = user_after.get("current_exp", 0)
    exp_remaining = max(0, next_exp - cur_exp)
    if exp_remaining > 0:
        days = exp_remaining // 65 + 1
        lines.append(f"升级还需: 约 {days} 天")

    return "\n".join(lines)


def main() -> int:
    """主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info("Bilibili 签到任务 v2 开始")

    config = get_config()

    if not config["sessdata"] or not config["bili_jct"]:
        log_error("Cookie 解析失败: BILIBILI_COOKIE 中未找到 SESSDATA 或 bili_jct")
        log_error("请确认 Cookie 完整（需包含 SESSDATA 和 bili_jct 两个字段）")
        return 1

    log_debug(f"配置: coin_num={config['coin_num']} skip_coin={config['skip_coin']} "
              f"skip_share={config['skip_share']} silver2coin={config['silver2coin']} "
              f"receive_vip={config['receive_vip_privilege']} live_rooms={config['live_rooms']}")

    try:
        result = run_all(config)

        if "error" in result:
            log_error(result["error"])
            return 1

        output = format_result(result)
        log_info("任务结果:\n" + output)

        # 判定失败：任何任务失败都视为整体失败（触发通知）
        failed_tasks = [t for t in result["tasks"] if not t.get("success")]
        if failed_tasks:
            failed_names = [t.get("task", "?") for t in failed_tasks]
            log_warning(f"部分任务失败: {', '.join(failed_names)}")
            return 1

        log_success("Bilibili 任务执行完成")
        return 0

    except Exception as e:
        log_error(f"任务执行异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
