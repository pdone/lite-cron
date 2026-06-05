#!/usr/bin/env python3
"""
通知模块 - 支持 WEBHOOK 和 NTFY 两种通知方式
配置从 config.yml 的 notify 部分读取（层级结构）

配置示例:
notify:
  on_failure: true
  on_success: false
  webhook:
    url: "https://example.com/webhook"
    method: "POST"
    content_type: "application/json"
    body: |
      title: $title
      content: $content
    headers: |
      Authorization: Bearer xxx
  ntfy:
    url: "https://ntfy.sh"
    topic: "mytopic"
    priority: "3"
    token: ""
"""
import json
import os
import re
import sys
import threading
import urllib.parse
from pathlib import Path
from typing import Dict, Optional

import requests
import yaml

# 导入日志模块
from logger import log_info, log_success, log_error, log_warning

# 配置缓存
_notify_config: Optional[Dict] = None


def _load_config() -> Dict:
    """从 config.yml 加载通知配置（层级结构）"""
    global _notify_config
    if _notify_config is not None:
        return _notify_config

    config_paths = [
        "/app/config.yml",
        "config.yml",
        os.environ.get("LITECRON_CONFIG", "/app/config.yaml"),
    ]

    for config_path in config_paths:
        path = Path(config_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)

                notify_config = config.get("notify", {})
                
                # 读取 webhook 配置（层级结构）
                webhook_config = notify_config.get("webhook", {})
                ntfy_config = notify_config.get("ntfy", {})
                
                _notify_config = {
                    # 通知触发设置
                    "on_failure": notify_config.get("on_failure", True),
                    "on_success": notify_config.get("on_success", False),
                    
                    # Webhook 配置
                    "webhook_url": webhook_config.get("url", ""),
                    "webhook_body": webhook_config.get("body", ""),
                    "webhook_headers": webhook_config.get("headers", ""),
                    "webhook_method": webhook_config.get("method", "POST"),
                    "webhook_content_type": webhook_config.get(
                        "content_type", "application/json"
                    ),
                    
                    # NTFY 配置
                    "ntfy_url": ntfy_config.get("url", ""),
                    "ntfy_topic": ntfy_config.get("topic", ""),
                    "ntfy_priority": str(ntfy_config.get("priority", "3")),
                    "ntfy_token": ntfy_config.get("token", ""),
                    "ntfy_username": ntfy_config.get("username", ""),
                    "ntfy_password": ntfy_config.get("password", ""),
                    "ntfy_actions": ntfy_config.get("actions", ""),
                    "ntfy_headers": ntfy_config.get("headers", ""),
                }
                return _notify_config
            except Exception:
                continue

    # 默认空配置
    _notify_config = {
        "on_failure": True,
        "on_success": False,
        "webhook_url": "",
        "webhook_body": "",
        "webhook_headers": "",
        "webhook_method": "POST",
        "webhook_content_type": "application/json",
        "ntfy_url": "",
        "ntfy_topic": "",
        "ntfy_priority": "3",
        "ntfy_token": "",
        "ntfy_username": "",
        "ntfy_password": "",
        "ntfy_actions": "",
    }
    return _notify_config


def _check_webhook_config(config: Dict) -> bool:
    """检查 WEBHOOK 配置是否有效"""
    return bool(config.get("webhook_url") and config.get("webhook_method"))


def _check_ntfy_config(config: Dict) -> bool:
    """检查 NTFY 配置是否有效"""
    return bool(config.get("ntfy_url") and config.get("ntfy_topic"))


def _parse_headers(headers_str: str) -> Dict:
    """解析请求头字符串为字典"""
    if not headers_str:
        return {}

    parsed = {}
    for line in headers_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        i = line.find(":")
        if i == -1:
            continue
        key = line[:i].strip()
        val = line[i + 1 :].strip()
        if key:
            parsed[key] = parsed.get(key, "") + ", " + val if key in parsed else val
    return parsed


def _parse_body(body: str, content_type: str, title: str, content: str) -> str:
    """解析并替换 body 中的变量"""
    if not body or content_type == "text/plain":
        return body

    # 替换 $title 和 $content
    formatted = body.replace("$title", title.replace("\n", "\\n")).replace(
        "$content", content.replace("\n", "\\n")
    )

    # 解析为字典格式
    pattern = r"(\w+):\s*((?:(?!\n\w+:).)*)"
    matches = {}
    for match in re.finditer(pattern, formatted):
        key, value = match.group(1).strip(), match.group(2).strip()
        matches[key] = value

    if content_type == "application/x-www-form-urlencoded":
        return urllib.parse.urlencode(matches, doseq=True)
    elif content_type == "application/json":
        return json.dumps(matches)

    return formatted


def webhook_notify(title: str, content: str, config: Dict, log_content: str = "", log_lines: int = 15) -> None:
    """WEBHOOK 通知 - 使用传入的 title 和 content 组织请求体"""
    url = config.get("webhook_url", "")
    method = config.get("webhook_method", "POST")
    content_type = config.get("webhook_content_type", "application/json")
    headers_str = config.get("webhook_headers", "")

    if not url:
        log_warning("WEBHOOK 未配置 URL")
        return

    headers = _parse_headers(headers_str)
    headers["Content-Type"] = content_type

    # 格式化 URL 中的变量
    formatted_url = url.replace("$title", urllib.parse.quote_plus(title)).replace(
        "$content", urllib.parse.quote_plus(content)
    )

    # 根据 content_type 组织请求体
    if content_type == "application/json":
        body_data = {
            "title": title,
            "content": content
        }
        # 如果有日志内容，添加到请求体
        # if log_content:
        #     body_data["log"] = log_content
        formatted_body = json.dumps(body_data, ensure_ascii=False)
    elif content_type == "application/x-www-form-urlencoded":
        body_data = {
            "title": title,
            "content": content
        }
        # if log_content:
        #     body_data["log"] = log_content
        formatted_body = urllib.parse.urlencode(body_data, doseq=True)
    elif content_type == "text/markdown":
        formatted_body = f"**{title}**\n{content}"
        if log_content:
            prefixed_log = "\n".join(f"- {line}" for line in log_content.split("\n"))
            formatted_body += f"\n\n最近{log_lines}行日志：\n\n{prefixed_log}"
    else:
        # text/plain 或其他格式，直接发送 content
        formatted_body = f"{title} {content}"

    try:
        response = requests.request(
            method=method,
            url=formatted_url,
            headers=headers,
            data=formatted_body,
            timeout=15,
        )

        if response.status_code == 200:
            log_success("WEBHOOK 推送成功！")
        else:
            log_error(f"WEBHOOK 推送失败: {response.status_code}")
            log_error(f"   错误信息: {response.text}")
    except Exception as e:
        log_error(f"WEBHOOK 推送异常: {e}")


def ntfy_notify(title: str, content: str, config: Dict, log_content: str = "", log_lines: int = 15) -> None:
    """NTFY 通知 - 使用 headers 方式"""
    import base64

    url_base = config.get("ntfy_url", "")
    topic = config.get("ntfy_topic", "")
    priority = config.get("ntfy_priority", "3")
    token = config.get("ntfy_token", "")
    username = config.get("ntfy_username", "")
    password = config.get("ntfy_password", "")
    actions = config.get("ntfy_actions", "")
    headers_str = config.get("ntfy_headers", "")

    def encode_rfc2047(text: str) -> str:
        """将文本编码为符合 RFC 2047 标准的格式"""
        encoded_bytes = base64.b64encode(text.encode("utf-8"))
        encoded_str = encoded_bytes.decode("utf-8")
        return f"=?utf-8?B?{encoded_str}?="

    # 解析自定义 headers
    custom_headers = _parse_headers(headers_str)

    # 构建 headers
    encoded_title = encode_rfc2047(title)
    headers = {
        "Title": encoded_title,
        "Priority": priority,
    }

    # 合并自定义 headers（自定义 headers 优先级更高）
    headers.update(custom_headers)

    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif username and password:
        auth_str = f"{username}:{password}"
        headers["Authorization"] = (
            f"Basic {base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')}"
        )

    # 构建消息内容，如果有日志内容附加到末尾
    message = content

    if actions:
        headers["Actions"] = encode_rfc2047(actions)
    elif log_content:
        log_action = [
            {
                "action": "view",
                "label": "查看日志",
                "url": log_content
            }
        ]
        headers["Actions"] = encode_rfc2047(log_action)

    url = f"{url_base}/{topic}"
    data = message.encode(encoding="utf-8")

    try:
        response = requests.post(url, data=data, headers=headers, timeout=15)
        if response.status_code == 200:
            log_success("NTFY 推送成功！")
        else:
            log_error(f"NTFY 推送失败: {response.status_code} {response.text}")
    except Exception as e:
        log_error(f"NTFY 推送异常: {e}")


def ntfy_notify2(title: str, content: str, config: Dict, log_content: str = "", log_lines: int = 15) -> None:
    """
    NTFY 通知 - 使用 JSON 格式发送

    参考: https://docs.ntfy.sh/publish/#publish-as-json

    Args:
        title: 通知标题
        content: 通知内容
        config: 配置字典
        log_content: 日志内容（作为 action 按钮的 URL）
        log_lines: 日志行数，默认为 15
    """
    import base64

    url_base = config.get("ntfy_url", "")
    topic = config.get("ntfy_topic", "")
    priority = config.get("ntfy_priority", "3")
    token = config.get("ntfy_token", "")
    username = config.get("ntfy_username", "")
    password = config.get("ntfy_password", "")

    if not url_base or not topic:
        log_warning("NTFY 未配置 URL 或 Topic")
        return

    # 构建 JSON 请求体
    body_data = {
        "topic": topic,
        "title": title,
        "message": content,
        "priority": int(priority) if priority.isdigit() else 3,
    }

    # 添加日志内容作为 action 按钮
    if log_content:
        # 对 title 和 log_content 进行 URL 编码
        encoded_title = urllib.parse.quote(title)
        temp_content = f"{content}\n\n最近{log_lines}行日志：\n\n{log_content}"
        encoded_log = urllib.parse.quote(temp_content)
        log_url = f"https://msg.dva.dpdns.org/?t={encoded_title}&m={encoded_log}"
        body_data["actions"] = [
            {
                "action": "view",
                "label": f"📋 查看最近{log_lines}行日志",
                "url": log_url
            }
        ]

    # 设置认证
    headers = {
        "Content-Type": "application/json"
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif username and password:
        auth_str = f"{username}:{password}"
        headers["Authorization"] = f"Basic {base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')}"

    url = f"{url_base}"

    try:
        response = requests.post(
            url,
            data=json.dumps(body_data, ensure_ascii=False),
            headers=headers,
            timeout=15
        )

        if response.status_code == 200:
            log_success("NTFY 推送成功！")
        else:
            log_error(f"NTFY 推送失败: {response.status_code} {response.text}")
    except Exception as e:
        log_error(f"NTFY 推送异常: {e}")


def notify(title: str, content: str, force: bool = False, log_content: str = "", log_lines: int = 15) -> None:
    """
    发送通知 (支持 WEBHOOK 和 NTFY)

    Args:
        title: 通知标题
        content: 通知内容
        force: 强制发送，忽略 on_failure/on_success 设置
        log_content: 日志内容（作为独立字段传递）
        log_lines: 日志行数，默认为 15
    """
    if not content:
        log_warning(f"推送内容为空，跳过: {title}")
        return

    config = _load_config()
    
    # 检查是否需要发送通知
    if not force:
        # 根据标题判断是失败还是成功通知
        is_failure = "失败" in title or "错误" in title or "异常" in title
        if is_failure and not config.get("on_failure", True):
            log_info(f"跳过失败通知（on_failure=false）: {title}")
            return
        if not is_failure and not config.get("on_success", False):
            log_info(f"跳过成功通知（on_success=false）: {title}")
            return

    threads = []

    # WEBHOOK 通知
    if _check_webhook_config(config):
        t = threading.Thread(
            target=webhook_notify, args=(title, content, config, log_content, log_lines), name="webhook"
        )
        threads.append(t)
        t.start()
    else:
        log_warning("WEBHOOK 未配置 (缺少 notify.webhook.url)")

    # NTFY 通知
    if _check_ntfy_config(config):
        t = threading.Thread(
            target=ntfy_notify2, args=(title, content, config, log_content, log_lines), name="ntfy"
        )
        threads.append(t)
        t.start()
    else:
        log_warning("NTFY 未配置 (缺少 notify.ntfy.url 或 notify.ntfy.topic)")

    # 等待所有通知完成
    for t in threads:
        t.join()


def notify_task_result(task_name: str, success: bool, message: str = "") -> None:
    """
    发送任务执行结果通知
    
    Args:
        task_name: 任务名称
        success: 是否成功
        message: 附加消息（可选）
    """
    if success:
        title = f"✅ {task_name} 执行成功"
    else:
        title = f"❌ {task_name} 执行失败"
    
    content = message if message else ("任务执行完成" if success else "任务执行失败，请查看日志")
    
    notify(title, content)


def main():
    """测试入口"""
    import argparse
    import base64

    parser = argparse.ArgumentParser(description="通知模块")
    parser.add_argument("title", nargs="?", default="测试通知", help="通知标题")
    parser.add_argument("content", nargs="?", default="这是一条测试消息", help="通知内容")
    parser.add_argument("--log-content", "-l", default="", help="日志内容（独立字段，可为 base64 编码）")
    parser.add_argument("--log-lines", "-n", type=int, default=15, help="日志行数，默认为 15")
    parser.add_argument("--force", "-f", action="store_true", help="强制发送通知")

    args = parser.parse_args()

    log_content = args.log_content
    # 如果 log_content 是 base64 编码的，尝试解码
    # if log_content:
    #     try:
    #         log_content = base64.b64decode(log_content).decode('utf-8')
    #     except Exception:
    #         pass  # 如果解码失败，保持原值

    notify(args.title, args.content, force=args.force, log_content=log_content, log_lines=args.log_lines)


if __name__ == "__main__":
    main()
