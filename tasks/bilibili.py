#!/usr/bin/env python3
"""
Bilibili 自动签到任务

功能：
- B站漫画签到
- B站直播签到
- 视频投币任务
- 观看视频任务
- 分享视频任务
- 银瓜子换硬币
- 领取大会员权益

环境变量：
- BILIBILI_COOKIE: B站登录 Cookie（必需，格式: key1=value1; key2=value2）
- COIN_NUM: 每日投币数量（默认5）
- COIN_TYPE: 投币类型（1=关注用户视频，其他=分区视频，默认1）
- SILVER2COIN: 是否兑换银瓜子为硬币（true/false，默认false）
- RECEIVE_VIP_PRIVILEGE: 是否领取大会员权益（true/false，默认false）
- SKIP_SHARE: 是否跳过分享任务（true/false，默认false）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug

import time
import random
import requests
from datetime import datetime


# 配置常量
BASE_URL = "https://api.bilibili.com"
LIVE_URL = "https://api.live.bilibili.com"
MANGA_URL = "https://manga.bilibili.com"

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.64"
    ),
    "Referer": "https://www.bilibili.com/",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "Connection": "keep-alive",
}


class BiliBili:
    """Bilibili 签到任务类"""

    name = "Bilibili"

    def __init__(self, check_item: dict):
        """初始化

        Args:
            check_item: 配置字典，包含 cookie、coin_num 等参数
        """
        self.check_item = check_item
        self.session = None

    def _init_session(self) -> requests.Session:
        """初始化请求会话"""
        session = requests.session()
        session.headers.update(HEADERS)

        # 解析 Cookie
        cookie_str = self.check_item.get("cookie", "")
        if not cookie_str:
            return None

        cookies = {}
        for item in cookie_str.split("; "):
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key] = value

        requests.utils.add_dict_to_cookiejar(session.cookies, cookies)
        return session

    def get_nav(self) -> tuple:
        """获取用户导航信息

        Returns:
            tuple: (用户名, UID, 是否登录, 硬币数, VIP类型, 当前经验)
        """
        url = f"{BASE_URL}/x/web-interface/nav"
        try:
            ret = self.session.get(url=url, timeout=30).json()
            data = ret.get("data", {})
            return (
                data.get("uname"),
                data.get("mid"),
                data.get("isLogin"),
                data.get("money"),
                data.get("vipType"),
                data.get("level_info", {}).get("current_exp"),
            )
        except Exception as e:
            log_error(f"获取导航信息失败: {e}")
            return None, None, False, 0, 0, 0

    def get_today_exp(self) -> list:
        """获取今日经验信息

        Returns:
            list: 今日经验信息列表
        """
        url = f"{BASE_URL}/x/member/web/exp/log?jsonp=jsonp"
        try:
            today = time.strftime("%Y-%m-%d", time.localtime())
            ret = self.session.get(url=url, timeout=30).json()
            exp_list = ret.get("data", {}).get("list", [])
            return [x for x in exp_list if x.get("time", "").split()[0] == today]
        except Exception as e:
            log_warning(f"获取今日经验失败: {e}")
            return []

    def manga_sign(self) -> str:
        """B站漫画签到

        Returns:
            str: 签到结果消息
        """
        url = f"{MANGA_URL}/twirp/activity.v1.Activity/ClockIn"
        try:
            ret = self.session.post(url=url, data={"platform": "android"}, timeout=30).json()
            if ret.get("code") == 0:
                return "签到成功"
            elif ret.get("msg") == "clockin clockin is duplicate":
                return "今日已签到"
            else:
                msg = f"签到失败: {ret.get('msg', '未知错误')}"
                log_warning(msg)
                return msg
        except Exception as e:
            log_error(f"漫画签到异常: {e}")
            return f"签到异常: {e}"

    def live_sign(self) -> str:
        """B站直播签到

        Returns:
            str: 签到结果消息
        """
        url = f"{LIVE_URL}/xlive/web-ucenter/v1/sign/DoSign"
        try:
            ret = self.session.get(url=url, timeout=30).json()
            code = ret.get("code")
            data = ret.get("data", {})
            if code == 0:
                return (
                    f"签到成功，{data.get('text')}，"
                    f"特别信息:{data.get('specialText')}，"
                    f"本月已签到{data.get('hadSignDays')}天"
                )
            elif code == 1011040:
                return "今日已签到"
            else:
                msg = f"签到失败: {ret.get('message', '未知错误')}"
                log_warning(msg)
                return msg
        except Exception as e:
            log_error(f"直播签到异常: {e}")
            return f"签到异常: {e}"

    def vip_privilege_my(self) -> dict:
        """获取大会员权益信息

        Returns:
            dict: 权益信息
        """
        url = f"{BASE_URL}/x/vip/privilege/my"
        try:
            return self.session.get(url=url, timeout=30).json()
        except Exception as e:
            log_warning(f"获取大会员权益失败: {e}")
            return {}

    def vip_privilege_receive(self, bili_jct: str, receive_type: int = 1) -> dict:
        """领取大会员权益

        Args:
            bili_jct: CSRF Token
            receive_type: 权益类型（1=B币券，2=优惠券）

        Returns:
            dict: 领取结果
        """
        url = f"{BASE_URL}/x/vip/privilege/receive"
        try:
            return self.session.post(
                url=url, data={"type": receive_type, "csrf": bili_jct}, timeout=30
            ).json()
        except Exception as e:
            log_warning(f"领取大会员权益失败: {e}")
            return {}

    def get_region(self, rid: int = 1, num: int = 6) -> list:
        """获取分区视频列表

        Args:
            rid: 分区ID
            num: 获取数量

        Returns:
            list: 视频列表
        """
        url = f"{BASE_URL}/x/web-interface/dynamic/region?ps={num}&rid={rid}"
        try:
            ret = self.session.get(url=url, timeout=30).json()
            archives = ret.get("data", {}).get("archives", [])
            return [
                {
                    "aid": one.get("aid"),
                    "cid": one.get("cid"),
                    "title": one.get("title"),
                    "owner": one.get("owner", {}).get("name"),
                }
                for one in archives
            ]
        except Exception as e:
            log_warning(f"获取分区视频失败: {e}")
            return []

    def get_followings(self, uid: int, pn: int = 1, ps: int = 50) -> dict:
        """获取关注列表

        Args:
            uid: 用户UID
            pn: 页码
            ps: 每页数量

        Returns:
            dict: 关注列表
        """
        url = f"{BASE_URL}/x/relation/followings"
        params = {
            "vmid": uid,
            "pn": pn,
            "ps": ps,
            "order": "desc",
            "order_type": "attention",
        }
        try:
            return self.session.get(url=url, params=params, timeout=30).json()
        except Exception as e:
            log_warning(f"获取关注列表失败: {e}")
            return {}

    def space_arc_search(self, uid: int, pn: int = 1, ps: int = 30) -> tuple:
        """获取用户空间视频

        Args:
            uid: 用户UID
            pn: 页码
            ps: 每页数量

        Returns:
            tuple: (视频列表, 数量)
        """
        url = f"{BASE_URL}/x/space/arc/search"
        params = {"mid": uid, "pn": pn, "ps": ps, "tid": 0, "order": "pubdate"}
        try:
            ret = self.session.get(url=url, params=params, timeout=30).json()
            vlist = ret.get("data", {}).get("list", {}).get("vlist", [])[:2]
            data_list = [
                {
                    "aid": one.get("aid"),
                    "cid": 0,
                    "title": one.get("title"),
                    "owner": one.get("author"),
                }
                for one in vlist
            ]
            return data_list, len(data_list)
        except Exception as e:
            log_warning(f"获取用户视频失败: {e}")
            return [], 0

    def coin_add(self, aid: int, bili_jct: str, num: int = 1) -> dict:
        """给视频投币

        Args:
            aid: 视频AV号
            bili_jct: CSRF Token
            num: 投币数量

        Returns:
            dict: 投币结果
        """
        url = f"{BASE_URL}/x/web-interface/coin/add"
        post_data = {
            "aid": aid,
            "multiply": num,
            "select_like": 1,
            "cross_domain": "true",
            "csrf": bili_jct,
        }
        try:
            return self.session.post(url=url, data=post_data, timeout=30).json()
        except Exception as e:
            log_error(f"投币请求异常: {e}")
            return {"code": -1, "message": str(e)}

    def report_task(self, aid: int, cid: int, bili_jct: str, progres: int = 300) -> dict:
        """上报视频观看进度

        Args:
            aid: 视频AV号
            cid: 视频CID
            bili_jct: CSRF Token
            progres: 观看秒数

        Returns:
            dict: 上报结果
        """
        url = f"{BASE_URL}/x/v2/history/report"
        post_data = {"aid": aid, "cid": cid, "progres": progres, "csrf": bili_jct}
        try:
            return self.session.post(url=url, data=post_data, timeout=30).json()
        except Exception as e:
            log_error(f"观看任务异常: {e}")
            return {"code": -1}

    def share_task(self, aid: int, bili_jct: str) -> dict:
        """分享视频

        Args:
            aid: 视频AV号
            bili_jct: CSRF Token

        Returns:
            dict: 分享结果
        """
        url = f"{BASE_URL}/x/web-interface/share/add"
        post_data = {"aid": aid, "csrf": bili_jct}
        try:
            return self.session.post(url=url, data=post_data, timeout=30).json()
        except Exception as e:
            log_error(f"分享任务异常: {e}")
            return {"code": -1}

    def silver2coin(self, bili_jct: str) -> dict:
        """银瓜子换硬币

        Args:
            bili_jct: CSRF Token

        Returns:
            dict: 兑换结果
        """
        url = f"{LIVE_URL}/xlive/revenue/v1/wallet/silver2coin"
        try:
            return self.session.post(
                url=url, data={"csrf": bili_jct}, timeout=30
            ).json()
        except Exception as e:
            log_error(f"银瓜子兑换异常: {e}")
            return {"code": -1, "message": str(e)}

    def live_status(self) -> list:
        """获取直播状态（金银瓜子数量）

        Returns:
            list: 状态信息列表
        """
        url = f"{LIVE_URL}/pay/v1/Exchange/getStatus"
        try:
            ret = self.session.get(url=url, timeout=30).json()
            data = ret.get("data", {})
            return [
                {"name": "硬币数量", "value": data.get("coin", 0)},
                {"name": "金瓜子数", "value": data.get("gold", 0)},
                {"name": "银瓜子数", "value": data.get("silver", 0)},
            ]
        except Exception as e:
            log_warning(f"获取直播状态失败: {e}")
            return []

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

        # 获取配置
        cookie_str = self.check_item.get("cookie", "")
        bili_jct = ""
        for item in cookie_str.split("; "):
            if item.startswith("bili_jct="):
                bili_jct = item.split("=", 1)[1]
                break

        coin_num = self.check_item.get("coin_num", 5)
        coin_type = self.check_item.get("coin_type", 1)
        do_silver2coin = self.check_item.get("silver2coin", False)
        receive_vip_privilege = self.check_item.get("receive_vip_privilege", False)
        skip_share = self.check_item.get("skip_share", False)

        # 获取用户信息
        uname, uid, is_login, coin, vip_type, current_exp = self.get_nav()
        if not is_login:
            log_error("登录验证失败，请检查 Cookie 是否有效")
            return "登录验证失败，请检查 Cookie 是否有效"

        log_info(f"账号: {uname} (UID: {uid})")
        log_info(f"当前等级经验: {current_exp}")
        log_info(f"当前硬币: {coin}")
        log_info(f"大会员状态: {'是' if vip_type == 2 else '否'}")

        # 漫画签到
        log_info("执行漫画签到...")
        manga_msg = self.manga_sign()
        log_info(f"漫画签到: {manga_msg}")

        # 直播签到
        # log_info("执行直播签到...")
        # live_msg = self.live_sign()
        # log_info(f"直播签到: {live_msg}")

        # 领取大会员权益
        if receive_vip_privilege:
            if vip_type == 2:
                log_info("检查大会员权益...")
                vip_ret = self.vip_privilege_my()
                welfare_list = vip_ret.get("data", {}).get("list", [])
                for welfare in welfare_list:
                    if welfare.get("state") == 0 and welfare.get("vip_type") == vip_type:
                        receive_ret = self.vip_privilege_receive(
                            bili_jct=bili_jct, receive_type=welfare.get("type")
                        )
                        if receive_ret.get("code") == 0:
                            log_success(f"领取权益成功: 类型{welfare.get('type')}")
                        else:
                            log_warning(f"领取权益失败: {receive_ret.get('message', '未知错误')}")
            else:
                log_info("非大会员用户，跳过领取权益")
        else:
            log_info("已配置不领取大会员权益，跳过")

        # 获取视频列表用于投币
        aid_list = self.get_region()

        # 如果是投币给关注用户，获取关注列表的视频
        if coin_type == 1 and uid:
            log_info("获取关注用户视频...")
            following_ret = self.get_followings(uid=uid)
            count = 0
            for following in following_ret.get("data", {}).get("list", []):
                mid = following.get("mid")
                if mid:
                    tmplist, tmpcount = self.space_arc_search(uid=mid)
                    aid_list.extend(tmplist)
                    count += tmpcount
                    if count > coin_num:
                        log_info("已获取足够关注用户视频")
                        break
            else:
                # 如果关注用户不够，补充分区视频
                aid_list.extend(self.get_region())

        # 计算还需要投多少币
        today_exp_list = self.get_today_exp()
        coins_av_count = len([x for x in today_exp_list if x.get("reason") == "视频投币奖励"])
        remaining_coin = min(coin_num - coins_av_count, coin)

        log_info(f"今日已投币: {coins_av_count}，计划投币: {coin_num}，剩余可投: {remaining_coin}")

        # 执行投币
        success_count = 0
        if remaining_coin > 0:
            log_info("开始执行投币任务...")
            for aid_info in aid_list[::-1]:
                aid = aid_info.get("aid")
                if not aid:
                    continue

                ret = self.coin_add(aid=aid, bili_jct=bili_jct)
                code = ret.get("code")

                if code == 0:
                    remaining_coin -= 1
                    success_count += 1
                    log_success(f"投币成功: 《{aid_info.get('title', '未知视频')}》")
                elif code == 34005:
                    log_warning(f"投币失败: 已达到上限 - 《{aid_info.get('title', '未知视频')}》")
                    continue
                elif code == -104:
                    log_warning("投币失败: 硬币不足")
                    break
                elif code == -111:
                    log_error("投币失败: CSRF 验证失败")
                    break
                else:
                    log_warning(f"投币失败: {ret.get('message', '未知错误')}")
                    break

                if remaining_coin <= 0:
                    break

                # 随机延迟 0-5 秒
                delay = random.uniform(0, 5)
                log_debug(f"投币间隔延迟: {delay:.2f}秒")
                time.sleep(delay)

        coin_msg = f"今日成功投币 {success_count + coins_av_count}/{self.check_item.get('coin_num', 5)} 个"
        log_info(coin_msg)

        # 观看视频任务
        if aid_list:
            aid = aid_list[0].get("aid")
            cid = aid_list[0].get("cid")
            title = aid_list[0].get("title")
            log_info(f"执行观看任务: 《{title}》...")
            report_ret = self.report_task(aid=aid, cid=cid, bili_jct=bili_jct)
            if report_ret.get("code") == 0:
                report_msg = f"观看《{title}》300秒"
                log_success(f"观看任务完成: {report_msg}")
            else:
                report_msg = "观看任务失败"
                log_warning(report_msg)
        else:
            report_msg = "无可用视频"
            log_warning(report_msg)

        # 分享任务
        if skip_share:
            share_msg = "已配置跳过"
            log_info("已配置跳过分享任务")
        elif aid_list:
            aid = aid_list[0].get("aid")
            title = aid_list[0].get("title")
            log_info(f"执行分享任务: 《{title}》...")
            share_ret = self.share_task(aid=aid, bili_jct=bili_jct)
            if share_ret.get("code") == 0:
                share_msg = f"分享《{title}》成功"
                log_success(share_msg)
            else:
                share_msg = f"分享失败: {share_ret.get('message', '未知错误')}"
                log_warning(share_msg)
        else:
            share_msg = "无可用视频"
            log_warning(share_msg)

        # 银瓜子换硬币
        s2c_msg = "未开启兑换"
        if do_silver2coin:
            log_info("执行银瓜子兑换硬币...")
            s2c_ret = self.silver2coin(bili_jct=bili_jct)
            s2c_msg = s2c_ret.get("message", "未知结果")
            if s2c_ret.get("code") == 0:
                log_success(f"兑换成功: {s2c_msg}")
            else:
                log_warning(f"兑换失败: {s2c_msg}")

        # 获取最新状态
        live_stats = self.live_status()
        _, _, _, new_coin, _, new_current_exp = self.get_nav()
        today_exp = sum(x.get("delta", 0) for x in self.get_today_exp())
        update_days = (28800 - new_current_exp) // (today_exp if today_exp else 1)

        # 构建结果消息
        msg_lines = [
            f"账号: {uname}",
            f"漫画签到: {manga_msg}",
            # f"直播签到: {live_msg}",
            f"登录任务: 今日已登录",
            f"观看视频: {report_msg}",
            f"分享任务: {share_msg}",
            f"瓜子兑换: {s2c_msg}",
            f"投币任务: {coin_msg}",
            f"今日经验: +{today_exp}",
            f"当前经验: {new_current_exp}",
            f"升级还需: 约{update_days}天",
        ]
        for stat in live_stats:
            msg_lines.append(f"{stat['name']}: {stat['value']}")

        result_msg = "\n".join(msg_lines)
        log_success("Bilibili 任务执行完成")
        return result_msg


def get_config() -> dict:
    """从环境变量获取配置

    Returns:
        dict: 配置字典
    """
    cookie = os.environ.get("BILIBILI_COOKIE", "")
    if not cookie:
        log_error("错误: 未配置环境变量 BILIBILI_COOKIE")
        return {}

    return {
        "cookie": cookie,
        "coin_num": int(os.environ.get("COIN_NUM", "5")),
        "coin_type": int(os.environ.get("COIN_TYPE", "1")),
        "silver2coin": os.environ.get("SILVER2COIN", "false").lower() == "true",
        "receive_vip_privilege": os.environ.get("RECEIVE_VIP_PRIVILEGE", "false").lower() == "true",
        "skip_share": os.environ.get("SKIP_SHARE", "false").lower() == "true",
    }


def main() -> int:
    """主函数

    Returns:
        int: 退出码 (0=成功, 1=失败)
    """
    log_info("Bilibili 签到任务开始")

    # 获取配置
    config = get_config()
    if not config:
        log_warning("任务终止: 未配置有效凭据")
        return 1

    # 执行任务
    try:
        bili = BiliBili(check_item=config)
        result = bili.main()
        log_info("任务结果:\n" + result)
        return 0
    except Exception as e:
        log_error(f"任务执行异常: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
