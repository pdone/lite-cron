#!/usr/bin/env python3
"""
Bilibili 自动签到任务 v2

基于 https://github.com/XiaoYiWeio/bili-checkin 改造，适配 LiteCron 框架。
相比原 bilibili.py 的主要改进：
- 从 BILIBILI_COOKIE 中提取 SESSDATA + bili_jct 双字段独立使用，规避 cookie
  字符串分隔符差异导致的 CSRF 解析失败问题；同时透传完整 Cookie 字符串，
  让分享等加强风控的接口能通过校验（需在 Cookie 中包含 buvid3/buvid4 等字段）
- 通过 /x/member/web/exp/reward 预检查任务状态，已完成任务自动跳过
- 观看任务改用 popular 接口获取视频（含真实 cid）+ heartbeat 心跳上报，
  解决原脚本 cid=0 导致观看任务必失败的问题
- 大会员判定基于 vipStatus（生效中），覆盖月度/年度两种类型
- 移除已下线的直播区签到接口
- 所有响应统一 None 安全处理，避免 'NoneType' object has no attribute 'get'

环境变量（统一使用 BILIBILI_ 前缀）:
- BILIBILI_COOKIE: B站登录 Cookie（必需，需包含 SESSDATA 和 bili_jct；
  建议同时包含 buvid3/buvid4/b_nutss 等设备指纹字段以通过分享接口风控）
- BILIBILI_COIN_NUM: 每日投币数量（默认 5）
- BILIBILI_COIN_FOLLOW: 投币是否只给关注列表 UP 主（true/false，默认 false）
- BILIBILI_WATCH_FOLLOW: 观看是否只看关注列表 UP 主视频（true/false，默认 false）
- BILIBILI_FOLLOW_SAMPLE: 关注列表随机采样 UP 主数量（默认 10，越小请求越少）

关注列表视频获取策略:
- 优先通过动态 feed 接口（/x/polymer/web-dynamic/v1/feed/all?type=video）单请求拉取
  关注 UP 主最新视频，请求量最小、风控友好（尤其走代理 IP 时）；
- 动态 feed 失败时回退到「随机采样 FOLLOW_SAMPLE 个 UP 主 + space/arc/search 取最新投稿」；
- 两次均失败则本轮自动降级为热门视频（仅告警一次，不重复刷屏）。
- BILIBILI_SILVER2COIN: 是否兑换银瓜子为硬币（true/false，默认 false）
- BILIBILI_RECEIVE_VIP_PRIVILEGE: 是否领取大会员权益（true/false，默认 false）
- BILIBILI_SKIP_SHARE: 是否跳过分享任务（true/false，默认 false）
- BILIBILI_SKIP_COIN: 是否跳过投币任务（true/false，默认 false，节省硬币）
- BILIBILI_PROXY: HTTP(S) 代理地址（可选，如 http://127.0.0.1:7890，留空则直连）

依赖:
- requests
"""

import os
import sys
import json
import time
import random
import requests
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug


# ============ 常量 ============

BASE_URL = "https://api.bilibili.com"
LIVE_URL = "https://api.live.bilibili.com"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 代理（由 main() 根据 BILIBILI_PROXY 设置，requests 代理字典或 None）
PROXIES = None

# 完整 Cookie 字符串（由 main() 根据 BILIBILI_COOKIE 设置）
# 透传包含 buvid3/buvid4 等设备指纹字段的完整 Cookie，让分享等加强风控的接口能通过校验
# 为空时回退到仅 SESSDATA+bili_jct 两字段（兼容旧配置，但分享接口可能失败）
FULL_COOKIE = ""


# ============ Cookie 解析 ============

def parse_cookie_fields(cookie_str: str) -> tuple:
    """
    从完整 Cookie 字符串中提取 SESSDATA 和 bili_jct，并归一化完整 Cookie

    兼容分隔符 ';' 和 '; '，以及行首行尾空白。

    Args:
        cookie_str: Cookie 字符串，格式: key1=value1; key2=value2

    Returns:
        tuple: (sessdata, bili_jct, full_cookie)
            - sessdata/bili_jct: 单独提取的两字段（csrf 等场景需要）
            - full_cookie: 归一化后的完整 Cookie 字符串（key=value; key=value 形式），
              透传给请求头使用，确保 buvid3/buvid4 等设备指纹字段不丢失
    """
    sessdata = ""
    bili_jct = ""
    pairs = []

    if not cookie_str:
        return sessdata, bili_jct, ""

    # 统一分割：先按 ; 分割，再 strip 空白
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if key == "SESSDATA":
            sessdata = value
        elif key == "bili_jct":
            bili_jct = value
        pairs.append(f"{key}={value}")

    full_cookie = "; ".join(pairs)
    return sessdata, bili_jct, full_cookie


def make_headers(sessdata: str, bili_jct: str, referer: str = "https://www.bilibili.com") -> dict:
    """构造请求头

    优先使用全局 FULL_COOKIE（包含 buvid3/buvid4 等设备指纹字段，分享接口风控必需）；
    FULL_COOKIE 为空时回退到仅 SESSDATA+bili_jct 两字段（兼容旧配置）。
    """
    cookie = FULL_COOKIE if FULL_COOKIE else f"SESSDATA={sessdata}; bili_jct={bili_jct}"
    return {
        "User-Agent": UA,
        "Cookie": cookie,
        "Referer": referer,
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


# ============ HTTP 工具 ============

def http_get(url: str, headers: dict, timeout: int = 15) -> dict:
    """GET 请求，返回解析后的 JSON dict，异常时返回 {"code": -1, "message": ...}"""
    try:
        resp = requests.get(url=url, headers=headers, timeout=timeout, proxies=PROXIES)
        return resp.json()
    except requests.exceptions.HTTPError as e:
        return {"code": -1, "message": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"code": -1, "message": str(e)}


def http_post(url: str, data: dict, headers: dict, timeout: int = 15) -> dict:
    """POST 请求（表单编码），返回解析后的 JSON dict"""
    headers = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(url=url, data=data, headers=headers, timeout=timeout, proxies=PROXIES)
        return resp.json()
    except requests.exceptions.HTTPError as e:
        return {"code": -1, "message": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"code": -1, "message": str(e)}


# ============ 任务接口 ============

def _to_int(value, default: int = 0) -> int:
    """安全转 int，B 站接口部分字段会返回字符串形式数字（如 next_exp="28800"）"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        "level": _to_int(level_info.get("current_level")),
        "current_exp": _to_int(level_info.get("current_exp")),
        "next_exp": _to_int(level_info.get("next_exp"), 0),
        "coins": _to_int(data.get("money"), 0),
        "is_login": data.get("isLogin", False),
        "vip_type": _to_int(data.get("vipType"), 0),
        "vip_status": _to_int(data.get("vipStatus"), 0),
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
        "coins": _to_int(data.get("coins", data.get("coins_av", 0)), 0),
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


def get_followings(sessdata: str, bili_jct: str, uid: int, ps: int = 50) -> list:
    """获取关注列表中的 UP 主 mid

    Args:
        uid: 当前登录用户 UID
        ps: 单次拉取数量（最多 50）

    Returns:
        list: 关注 UP 主的 mid 列表
    """
    url = f"{BASE_URL}/x/relation/followings"
    params = {"vmid": uid, "ps": ps, "pn": 1}
    headers = make_headers(sessdata, bili_jct)
    resp = http_get(f"{url}?{urlencode(params)}", headers)
    if not resp or resp.get("code") != 0:
        log_debug(f"关注列表接口失败: code={resp.get('code') if resp else 'N/A'} "
                  f"msg={resp.get('message') if resp else '请求失败'}")
        return []
    return [u.get("mid") for u in (resp.get("data") or {}).get("list") or [] if u.get("mid")]


def get_dynamic_feed_videos(sessdata: str, bili_jct: str, max_videos: int = 20) -> list:
    """通过 Web 动态 feed 一次性获取关注 UP 主的最新视频

    使用 /x/polymer/web-dynamic/v1/feed/all 接口，单次请求即可拿到关注 UP 主
    投稿的视频动态，无需逐个 UP 主调用 space/arc/search，请求量从「1+N」降到 1，
    大幅降低触发 B站风控（-412）的概率，尤其适合走代理 IP 的场景。

    动态返回的视频无 cid（cid=0），观看前需通过 view 接口按 bvid 解析。

    Args:
        max_videos: 最多收集多少条视频

    Returns:
        list: 视频字典列表，字段同 get_popular_videos
    """
    url = f"{BASE_URL}/x/polymer/web-dynamic/v1/feed/all"
    params = {"timezone_offset": -480, "type": "video", "page": 1}
    headers = make_headers(sessdata, bili_jct, "https://t.bilibili.com/")
    resp = http_get(f"{url}?{urlencode(params)}", headers)
    if not resp or resp.get("code") != 0:
        log_debug(f"动态 feed 接口失败: code={resp.get('code') if resp else 'N/A'} "
                  f"msg={resp.get('message') if resp else '请求失败'}")
        return []

    items = (resp.get("data") or {}).get("items") or []
    videos = []
    for item in items:
        if item.get("type") != "DYNAMIC_TYPE_AV":
            continue
        modules = item.get("modules") or {}
        major = ((modules.get("module_dynamic") or {}).get("major")) or {}
        archive = major.get("archive") or {}
        aid = archive.get("aid")
        if not aid:
            continue
        author = (modules.get("module_author") or {}).get("name", "")
        videos.append(
            {
                "aid": int(aid) if str(aid).isdigit() else aid,
                "bvid": archive.get("bvid"),
                "cid": 0,  # 动态不返回 cid，观看时按 bvid 解析
                "title": archive.get("title", ""),
                "duration": _parse_length(archive.get("duration_text", "100")),
                "owner": author,
            }
        )
        if len(videos) >= max_videos:
            break
    return videos


def _parse_length(length) -> int:
    """将视频时长字符串 'mm:ss' / 'hh:mm:ss' 转为秒数，解析失败返回 100"""
    try:
        parts = [int(p) for p in str(length).split(":")]
    except (ValueError, AttributeError):
        return 100
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return 100


def get_following_videos(
    sessdata: str, bili_jct: str, uid: int, sample: int = 10, per_up: int = 1, max_videos: int = 20
) -> list:
    """获取关注 UP 主最近发布的视频（含 aid/bvid/cid/title/duration）

    优先策略：动态 feed 单请求拉取（get_dynamic_feed_videos），请求量最小、
    风控最友好。若动态 feed 失败（返回空），回退到「随机采样 sample 个 UP 主，
    每个取 per_up 条最新投稿」的 space/arc/search 方案。space/arc/search 对
    IP 风控敏感（走代理时易返回 -412），故仅作兜底。

    Args:
        uid: 当前登录用户 UID
        sample: 回退方案中随机采样的 UP 主数量（默认 10）
        per_up: 回退方案中每个 UP 主取多少条最新视频（默认 1）
        max_videos: 最多收集多少条视频（安全上限，默认 20）

    Returns:
        list: 视频字典列表，字段同 get_popular_videos
    """
    # 优先：动态 feed 单请求
    videos = get_dynamic_feed_videos(sessdata, bili_jct, max_videos)
    if videos:
        return videos

    # 兜底：随机采样 UP 主 + space/arc/search
    log_debug("动态 feed 未取到视频，回退到关注列表采样方案")
    mids = get_followings(sessdata, bili_jct, uid)
    if not mids:
        return []

    # 随机采样指定数量的 UP 主，避免每次都打全部关注列表
    if len(mids) > sample:
        mids = random.sample(mids, sample)

    videos = []
    for mid in mids:
        if len(videos) >= max_videos:
            break
        url = f"{BASE_URL}/x/space/arc/search"
        params = {"mid": mid, "ps": per_up, "pn": 1, "order": "pubdate"}
        headers = make_headers(sessdata, bili_jct)
        resp = http_get(f"{url}?{urlencode(params)}", headers)
        if not resp or resp.get("code") != 0:
            continue
        vlist = (resp.get("data") or {}).get("list") or {}
        vlist = vlist.get("vlist") or []
        for v in vlist:
            if not v.get("aid"):
                continue
            videos.append(
                {
                    "aid": v.get("aid"),
                    "bvid": v.get("bvid"),
                    "cid": v.get("cid", 0),
                    "title": v.get("title", ""),
                    "duration": _parse_length(v.get("length", "100")),
                    "owner": v.get("author", ""),
                }
            )
            if len(videos) >= max_videos:
                break
    return videos


def get_video_cid(sessdata: str, bili_jct: str, bvid: str) -> int:
    """通过 bvid 获取视频真实 cid（space/arc/search 返回的 cid 常为 0）"""
    url = f"{BASE_URL}/x/web-interface/view?bvid={bvid}"
    headers = make_headers(sessdata, bili_jct)
    resp = http_get(url, headers)
    if resp and resp.get("code") == 0:
        return (resp.get("data") or {}).get("cid", 0)
    return 0


def pick_video(
    sessdata: str, bili_jct: str, uid: int = None, follow: bool = False, following_pool: list = None
) -> dict:
    """挑选一个视频

    follow=True 且能成功获取关注列表视频时，从关注 UP 主视频中随机挑选；
    否则回退到热门视频。

    Args:
        uid: 当前登录用户 UID（follow=True 时必填）
        follow: 是否仅从关注列表选取
        following_pool: 预先拉取好的关注列表视频池（由 run_all 统一拉一次后复用），
            传入后不再重复请求接口，避免高频触发 B站风控限流
    """
    if follow:
        # 优先使用复用池；未提供时（兼容旧调用）才临时拉取
        if following_pool is None and uid:
            following_pool = get_following_videos(sessdata, bili_jct, uid)
        if following_pool:
            return random.choice(following_pool)
        log_warning("关注列表视频获取失败，回退到热门视频")
    videos = get_popular_videos(sessdata, bili_jct)
    if not videos:
        return {}
    return random.choice(videos)


def do_watch(
    sessdata: str, bili_jct: str, uid: int = None, follow: bool = False, following_pool: list = None
) -> dict:
    """模拟观看视频（heartbeat 心跳上报），+5 EXP

    使用接口返回的真实 cid，解决原脚本 cid=0 必失败的问题。
    follow=True 时仅观看关注 UP 主发布的视频（cid 可能为 0，需额外解析）。
    """
    video = pick_video(sessdata, bili_jct, uid, follow, following_pool)
    if not video:
        return {"success": False, "message": "无法获取视频列表"}

    # 关注列表视频的 cid 常为 0，需通过 view 接口解析真实 cid
    cid = video.get("cid") or 0
    if not cid and video.get("bvid"):
        cid = get_video_cid(sessdata, bili_jct, video["bvid"])
    if not cid:
        return {"success": False, "message": "无法获取视频 cid"}

    url = f"{BASE_URL}/x/click-interface/web/heartbeat"
    duration = int(video.get("duration") or 100)
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
    """分享视频，+5 EXP

    分享接口风控较严，要求 Cookie 中包含 buvid3/buvid4 等设备指纹字段，
    否则会返回「账号异常,操作失败」。若用户 Cookie 中未携带这些字段，
    可通过 BILIBILI_SKIP_SHARE=true 跳过分享任务（仅损失 5 EXP）。
    """
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
    # 「账号异常」通常是 Cookie 缺失 buvid3/buvid4 等设备指纹字段导致的风控拦截
    if "账号异常" in msg or "操作失败" in msg:
        return {
            "success": False,
            "message": f"{msg}（建议在 BILIBILI_COOKIE 中补充 buvid3/buvid4 字段，或设置 BILIBILI_SKIP_SHARE=true 跳过）",
        }
    return {"success": False, "message": msg}


def do_coin(
    sessdata: str, bili_jct: str, count: int, uid: int = None, follow: bool = False, following_pool: list = None
) -> dict:
    """投币任务，每枚 +10 EXP，最多 5 枚 = 50 EXP

    通过预检查的 coins 字段计算还需投币数量，避免超投。
    follow=True 时仅给关注 UP 主的视频投币。
    """
    results = []
    success_count = 0
    total_exp = 0

    for i in range(count):
        video = pick_video(sessdata, bili_jct, uid, follow, following_pool)
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

    所有配置项统一使用 BILIBILI_ 前缀，与其他任务的命名规范保持一致。
    """
    cookie = os.environ.get("BILIBILI_COOKIE", "")
    sessdata, bili_jct, full_cookie = parse_cookie_fields(cookie)

    def env_bool(key: str, default: str = "false") -> bool:
        return os.environ.get(key, default).lower() == "true"

    def env_int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, str(default)))
        except ValueError:
            return default

    return {
        "sessdata": sessdata,
        "bili_jct": bili_jct,
        "full_cookie": full_cookie,
        "coin_num": env_int("BILIBILI_COIN_NUM", 5),
        "coin_follow": env_bool("BILIBILI_COIN_FOLLOW"),
        "watch_follow": env_bool("BILIBILI_WATCH_FOLLOW"),
        "follow_sample": env_int("BILIBILI_FOLLOW_SAMPLE", 10),
        "silver2coin": env_bool("BILIBILI_SILVER2COIN"),
        "receive_vip_privilege": env_bool("BILIBILI_RECEIVE_VIP_PRIVILEGE"),
        "skip_share": env_bool("BILIBILI_SKIP_SHARE"),
        "skip_coin": env_bool("BILIBILI_SKIP_COIN"),
        "proxy": os.environ.get("BILIBILI_PROXY", ""),
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

    # 预拉取关注列表视频（仅一次，供观看/投币复用，避免重复请求触发 B站风控限流）
    following_pool = None
    watch_follow = config["watch_follow"]
    coin_follow = config["coin_follow"]
    if watch_follow or coin_follow:
        log_debug("预拉取关注列表视频（供观看/投币复用）...")
        following_pool = get_following_videos(sessdata, bili_jct, user["uid"], config["follow_sample"])
        if not following_pool:
            # 拉取失败时统一降级为热门视频，并关闭 follow 标记，
            # 避免后续观看/投币每次都重复打印“回退到热门视频”警告
            log_warning("关注列表视频获取失败，本轮观看/投币回退到热门视频")
            watch_follow = False
            coin_follow = False

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
        if watch_follow:
            log_info("执行观看任务（仅关注列表 UP 主）...")
        else:
            log_info("执行观看任务...")
        r = do_watch(sessdata, bili_jct, user["uid"], watch_follow, following_pool)
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
            r = do_coin(sessdata, bili_jct, remaining, user["uid"], coin_follow, following_pool)
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

    # 7. 大会员权益（可选）
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

    # 8. 银瓜子换硬币（可选）
    if config["silver2coin"]:
        log_info("执行银瓜子兑换...")
        r = silver2coin(sessdata, bili_jct)
        if r.get("code") == 0:
            log_success(f"兑换成功: {r.get('message', '')}")
        else:
            log_warning(f"兑换失败: {r.get('message', '未知错误')}")
        tasks.append({"task": "silver2coin", **r})

    # 9. 汇总状态
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

    # 设置代理（全局，所有请求共用）
    proxy = config.get("proxy", "")
    if proxy:
        globals()["PROXIES"] = {"http": proxy, "https": proxy}
        log_info(f"已启用代理: {proxy}")
    else:
        log_debug("未配置代理，使用直连")

    # 设置完整 Cookie（全局，所有请求共用）
    # 透传 buvid3/buvid4 等设备指纹字段，让分享等加强风控的接口能通过校验
    full_cookie = config.get("full_cookie", "")
    if full_cookie:
        globals()["FULL_COOKIE"] = full_cookie
        # 检测是否包含分享接口风控所需的关键字段，缺失时给出提示
        has_buvid = "buvid3" in full_cookie
        if has_buvid:
            log_debug("已加载完整 Cookie（含 buvid3 等设备指纹字段）")
        else:
            log_warning("Cookie 中未检测到 buvid3 字段，分享接口可能返回「账号异常,操作失败」")
            log_warning("建议从浏览器导出完整 Cookie（包含 buvid3/buvid4/b_nutss 等字段）")

    log_debug(f"配置: coin_num={config['coin_num']} coin_follow={config['coin_follow']} "
              f"watch_follow={config['watch_follow']} skip_coin={config['skip_coin']} "
              f"skip_share={config['skip_share']} silver2coin={config['silver2coin']} "
              f"receive_vip={config['receive_vip_privilege']}")

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
