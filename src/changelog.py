#!/usr/bin/env python3
"""WebUI 更新日志渲染器

只覆盖 ``release-notes`` 规格实际产生的语法：版本 / 分类标题、无序列表、段落、
行内代码、粗体与链接。源文本先整体转义，再以占位符生成受控标签，因此文件中的
HTML 只会作为文本出现，链接协议也受白名单限制。
"""

import html
import re
from typing import List
from urllib.parse import urlparse

_VERSION_HEADING = re.compile(r"^##\s+(v\d+(?:\.\d+)*)\s*$")
_H2_HEADING = re.compile(r"^##\s+(.+?)\s*$")
_H3_HEADING = re.compile(r"^###\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^-\s+(.+?)\s*$")
_CODE_SPAN = re.compile(r"`([^`]+)`")
_LINK_SPAN = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_SPAN = re.compile(r"\*\*([^*]+)\*\*")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")
_ANCHOR_UNSAFE = re.compile(r"[^0-9a-zA-Z]+")


def version_anchor(version: str) -> str:
    """版本号转稳定锚点：``1.9.0`` / ``v1.9.0`` -> ``v1-9-0``。"""
    cleaned = _ANCHOR_UNSAFE.sub("-", version.strip()).strip("-")
    if cleaned[:1].lower() == "v":
        cleaned = cleaned[1:]
    return f"v{cleaned}" if cleaned else "v"


def _is_safe_href(target: str) -> bool:
    """仅放行 http(s) 绝对地址与站内相对地址。"""
    if target.startswith(("#", "/", "./", "../")):
        return True
    parsed = urlparse(target)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _render_inline(escaped_text: str) -> str:
    """已转义文本 -> 受控标签组成的内联 HTML。"""
    tokens: List[str] = []

    def stash(fragment: str) -> str:
        tokens.append(fragment)
        return f"\x00{len(tokens) - 1}\x00"

    def code_repl(match: re.Match) -> str:
        return stash(f"<code>{match.group(1)}</code>")

    def link_repl(match: re.Match) -> str:
        label, raw_target = match.group(1), match.group(2)
        target = html.unescape(raw_target)
        if not _is_safe_href(target):
            return match.group(0)
        external = target.startswith(("http://", "https://"))
        attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
        return stash(f'<a href="{raw_target}"{attrs}>{label}</a>')

    text = _CODE_SPAN.sub(code_repl, escaped_text)
    text = _LINK_SPAN.sub(link_repl, text)
    text = _BOLD_SPAN.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    return _PLACEHOLDER.sub(lambda m: tokens[int(m.group(1))], text)


def render_changelog(
    text: str, current_version: str, current_label: str = ""
) -> str:
    """把更新日志渲染为 HTML；从第一个 ``## v<版本>`` 开始，丢弃文档头部。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    start = 0
    for index, line in enumerate(lines):
        if _VERSION_HEADING.match(line):
            start = index
            break

    parts: List[str] = []
    list_open = False
    section_open = False
    paragraph: List[str] = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            parts.append("</ul>")
            list_open = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            parts.append("<p>" + _render_inline(" ".join(paragraph)) + "</p>")
            paragraph = []

    for raw_line in lines[start:]:
        line = raw_line.rstrip()
        if not line.strip():
            flush_paragraph()
            close_list()
            continue

        version_match = _VERSION_HEADING.match(line)
        if version_match:
            flush_paragraph()
            close_list()
            if section_open:
                parts.append("</section>")
            version = version_match.group(1)
            wanted = current_version.strip().lstrip("vV")
            is_current = bool(wanted) and version.lstrip("vV") == wanted
            classes = "changelog-version is-current" if is_current else "changelog-version"
            parts.append(f'<section class="{classes}" id="{version_anchor(version)}">')
            badge = ""
            if is_current and current_label:
                badge = (
                    ' <span class="changelog-current-badge">'
                    f"{html.escape(current_label)}</span>"
                )
            parts.append(f"<h2>{html.escape(version)}{badge}</h2>")
            section_open = True
            continue

        h3_match = _H3_HEADING.match(line)
        if h3_match:
            flush_paragraph()
            close_list()
            parts.append(f"<h3>{_render_inline(html.escape(h3_match.group(1)))}</h3>")
            continue

        h2_match = _H2_HEADING.match(line)
        if h2_match:
            flush_paragraph()
            close_list()
            parts.append(f"<h2>{_render_inline(html.escape(h2_match.group(1)))}</h2>")
            continue

        item_match = _LIST_ITEM.match(line)
        if item_match:
            flush_paragraph()
            if not list_open:
                parts.append("<ul>")
                list_open = True
            parts.append(f"<li>{_render_inline(html.escape(item_match.group(1)))}</li>")
            continue

        close_list()
        paragraph.append(html.escape(line.strip()))

    flush_paragraph()
    close_list()
    if section_open:
        parts.append("</section>")

    return "\n".join(parts)