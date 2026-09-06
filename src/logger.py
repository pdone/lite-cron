#!/usr/bin/env python3
"""
统一日志管理模块（Python 版本）
功能：将日志同时输出到文件和控制台（stdout）

使用方法：
    from logger import log, log_info, log_success, log_error, log_warning
    
    log_info("消息内容")
    log_success("成功消息")
    log_error("错误消息")

    # 任务失败时记录站点返回的完整内容（原文不截断落盘到 logs/responses/<日期>/）
    log_response_detail(response)
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ============ 配置 ============
LOG_DATE = datetime.now().strftime('%Y%m%d')

# 日志目录 - 统一使用当前文件(parent)同级目录的 logs/
# 容器内: /app/webapp.py -> /app/logs/
# 宿主机: src/webapp.py -> src/logs/
LOG_DIR = str(Path(__file__).parent / 'logs')
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, f"{LOG_DATE}.log")


_log_fallback_done = False

# ============ 核心日志函数 ============

def log(message: str, level: str = "INF") -> None:
    """
    通用日志函数
    
    Args:
        message: 日志消息
        level: 日志级别 (INFO/SUCCESS/ERROR/WARNING/DEBUG)
    """
    global LOG_FILE, LOG_DIR, _log_fallback_done
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    # 读取当前任务名（由 task_wrapper 通过环境变量注入）
    task_name = os.environ.get("LITECRON_TASK_NAME", "")
    task_part = f" [TASK:{task_name}]" if task_name else ""

    # 多行消息拆分为逐行输出：跳过纯空白行，保留非空续行原始内容（含缩进）。
    # 每个物理行复用同一 timestamp/level/task_part，保证多行归属始终准确。
    lines = [line for line in message.split('\n') if line.strip()]

    # 输出到控制台（flush=True 确保立即输出到 Docker logs）
    for line in lines:
        print(f"{timestamp} [{level}]{task_part} {line}", flush=True)
    
    # 输出到文件
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            for line in lines:
                f.write(f"{timestamp} [{level}]{task_part} {line}\n")
    except Exception as e:
        if not _log_fallback_done:
            fallback_dir = os.path.join(os.getcwd(), 'logs')
            try:
                Path(fallback_dir).mkdir(parents=True, exist_ok=True)
                LOG_DIR = fallback_dir
                LOG_FILE = os.path.join(LOG_DIR, f"{LOG_DATE}.log")
                _log_fallback_done = True
                warn_msg = f"{timestamp} [WAR] 日志目录不可用，降级到 {LOG_DIR}"
                print(warn_msg, flush=True)
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(warn_msg + '\n')
            except Exception as fallback_e:
                print(f"{timestamp} [ERR] 日志降级也失败: {fallback_e}", flush=True)
        else:
            print(f"[ERR] 无法写入日志文件: {e}")


def log_info(message: str) -> None:
    """INFO 级别日志"""
    log(message, "INF")


def log_success(message: str) -> None:
    """SUCCESS 级别日志"""
    log(message, "INF")


def log_error(message: str) -> None:
    """ERROR 级别日志"""
    log(message, "ERR")


def log_warning(message: str) -> None:
    """WARNING 级别日志"""
    log(message, "WAR")


def log_debug(message: str) -> None:
    """DEBUG 级别日志（仅当 DEBUG=true 时输出）"""
    if os.environ.get('DEBUG', 'false').lower() == 'true':
        log(message, "DBG")


# ============ 辅助函数 ============

def log_reset() -> None:
    """重置/清空日志文件"""
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write('')
    except Exception as e:
        print(f"[ERROR] 无法清空日志文件: {e}")


def log_path() -> str:
    """获取日志文件路径"""
    return LOG_FILE


def log_size() -> int:
    """获取日志文件大小（字节）"""
    try:
        return os.path.getsize(LOG_FILE)
    except (OSError, FileNotFoundError):
        return 0


# ============ 响应原文落盘 ============

# 单个响应原文最大落盘字节数（超过则截断，避免异常大响应撑爆磁盘）
RESPONSE_DUMP_MAX_BYTES = 2 * 1024 * 1024
# 响应可见文本内联到主日志的阈值（字符数），超过则只记录片段
RESPONSE_INLINE_LIMIT = 1000


def log_response_detail(
    response, keyword: str = None, window: int = 300, inline_limit: int = RESPONSE_INLINE_LIMIT
) -> str:
    """
    记录 HTTP 响应详情：完整原文落盘 + 主日志摘要，用于任务失败时排查

    供所有任务脚本在请求失败、解析失败或接口返回异常时调用：
    - 响应**完整原文**（不截断，超 2MB 的部分裁掉）写入 logs/responses/<日期>/ 目录
    - 主日志输出状态码、最终 URL、响应长度与落盘路径
    - 主日志同时输出响应正文：短响应（可见文本 <= inline_limit）全文内联，
      长响应按关键词/开头截取片段，避免日志被大段 HTML 淹没

    Args:
        response: 响应对象（requests/curl_cffi 等，需 status_code/url/text 属性）；
            也兼容直接传入 str/bytes/dict/list；为 None 时只记录一条提示
        keyword: 需要重点定位的页面关键词；为空或未命中时输出页面开头文本
        window: 关键词前后截取的文本宽度
        inline_limit: 可见文本内联到主日志的阈值（字符数），超过则只记片段

    Returns:
        str: 响应原文落盘路径；未成功落盘时返回空字符串
    """
    try:
        if response is None:
            log_warning("页面返回详情: 无响应对象（请求未发出或连接失败）")
            return ""

        if isinstance(response, (bytes, bytearray)):
            html = response.decode("utf-8", "replace")
            status, url, ctype = "N/A", "N/A", ""
        elif isinstance(response, str):
            html = response
            status, url, ctype = "N/A", "N/A", ""
        elif isinstance(response, (dict, list)):
            # 已解析好的 JSON 接口返回，直接序列化后落盘
            html = json.dumps(response, ensure_ascii=False, indent=2, default=str)
            status, url, ctype = "N/A", "N/A", "application/json"
        else:
            html = getattr(response, "text", "") or ""
            if not html:
                content = getattr(response, "content", b"") or b""
                if content:
                    html = content.decode("utf-8", "replace")
            status = getattr(response, "status_code", "N/A")
            url = getattr(response, "url", "N/A")
            ctype = ""
            headers = getattr(response, "headers", None)
            if headers is not None:
                try:
                    ctype = headers.get("Content-Type", "") or ""
                except AttributeError:
                    ctype = ""

        # 完整原文落盘（超长响应截断，避免异常大响应撑爆磁盘）
        truncated = len(html) > RESPONSE_DUMP_MAX_BYTES
        path = save_response_dump(
            html[:RESPONSE_DUMP_MAX_BYTES] if truncated else html,
            url=str(url),
            status=str(status),
            ext=_guess_ext(ctype, html),
            truncated=truncated,
        )

        log_warning(
            f"页面返回详情: HTTP {status} | 最终URL: {url} | 响应长度: {len(html)} 字节"
            + (f" | 完整响应已保存: {path}" if path else " | 完整响应落盘失败")
            + ("（原文超长已截断）" if truncated else "")
        )

        # 去除 script/style 与标签，提取页面可见文本
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            log_warning("页面返回详情: 响应正文为空")
            return path

        # 短响应直接内联全文，长响应只记片段（完整内容看落盘文件）
        if len(text) <= inline_limit:
            log_warning(f"页面返回完整内容: {text}")
            return path

        if keyword:
            # 取最后一次出现，避开顶部导航等链接
            idx = text.rfind(keyword)
            if idx != -1:
                start = max(0, idx - window)
                snippet = text[start:idx + window]
                prefix = "..." if start > 0 else ""
                suffix = "..." if idx + window < len(text) else ""
                log_warning(f"页面文本片段(「{keyword}」附近): {prefix}{snippet}{suffix}")
                return path
        log_warning(f"页面文本片段(开头{window}字): {text[:window]}")
        return path
    except Exception as e:
        log_warning(f"记录页面详情失败: {e}")
        return ""


def _response_dump_dir() -> str:
    """响应原文落盘目录：logs/responses/<日期>/"""
    return os.path.join(LOG_DIR, "responses", datetime.now().strftime("%Y%m%d"))


def _guess_ext(content_type: str, body: str) -> str:
    """根据 Content-Type / 正文首字符猜测落盘文件扩展名"""
    ct = (content_type or "").lower()
    if "json" in ct:
        return "json"
    if "html" in ct or "xml" in ct:
        return "html"
    head = body.lstrip()[:1]
    if head in ("{", "["):
        return "json"
    if head == "<":
        return "html"
    return "txt"


def save_response_dump(
    body: str,
    url: str = "N/A",
    status: str = "N/A",
    ext: str = "txt",
    truncated: bool = False,
) -> str:
    """
    将站点返回的完整原文写入 logs/responses/<日期>/，返回文件路径

    落盘文件带元信息头（时间/任务/URL/状态码/长度），便于事后排查是
    解析规则失效、页面结构变更还是被风控拦截。主日志只保留摘要与路径，
    避免大段 HTML 冲垮 WebUI 日志视图。

    Args:
        body: 响应正文原文
        url: 请求 URL（响应对象的最终 URL）
        status: HTTP 状态码
        ext: 文件扩展名（json/html/txt）
        truncated: 正文是否被截断

    Returns:
        str: 落盘文件路径；失败返回空字符串
    """
    try:
        dump_dir = _response_dump_dir()
        Path(dump_dir).mkdir(parents=True, exist_ok=True)

        task_name = os.environ.get("LITECRON_TASK_NAME", "") or "task"
        # 任务名/状态码可能含路径分隔符等非法字符，统一替换为下划线
        safe_task = re.sub(r"[^\w.\-]", "_", task_name)
        safe_status = re.sub(r"[^\w.\-]", "_", str(status))
        stamp = datetime.now().strftime("%H%M%S_%f")[:-3]
        path = os.path.join(dump_dir, f"{stamp}_{safe_task}_{safe_status}.{ext}")

        header = (
            "# LiteCron 响应原文（任务失败时自动保存，便于排查）\n"
            f"# 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# 任务: {task_name}\n"
            f"# URL: {url}\n"
            f"# 状态码: {status}\n"
            f"# 长度: {len(body)} 字节"
        )
        if truncated:
            header += f"（原文超过 {RESPONSE_DUMP_MAX_BYTES} 字节，已截断保存）"
        header += "\n" + "-" * 60 + "\n"

        with open(path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write(body)
        return path
    except Exception as e:
        log_warning(f"响应原文落盘失败: {e}")
        return ""


# 如果直接运行此脚本，显示测试信息
if __name__ == '__main__':
    log_info("日志模块测试")
    log_success("成功消息测试")
    log_warning("警告消息测试")
    log_error("错误消息测试")
    print(f"\n日志文件路径: {log_path()}")
    print(f"日志文件大小: {log_size()} bytes")
