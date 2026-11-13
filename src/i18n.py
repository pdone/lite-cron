#!/usr/bin/env python3
"""WebUI 界面语言（i18n）引擎

设计（见 openspec/changes/add-webui-i18n/design.md）：

- 语言事实存在 Cookie（``litecron_lang``），服务端在渲染前解析，因此首页与登录页
  首屏即为目标语言，不存在「先中文再替换」的闪烁。
- 一份字典同时服务 Python 与浏览器：``t()`` 供后端与 Jinja 使用，
  ``client_catalog()`` 由模板注入成 ``window.I18N`` 供前端 ``T()`` 使用。
- 缺翻回退链：目标语言 -> 简体中文 -> key 本身。
"""

from typing import Dict, Optional

from flask import g, has_request_context, request

from logger import log_error
from locales.en import MESSAGES as EN_MESSAGES
from locales.zh_cn import MESSAGES as ZH_MESSAGES

LANG_COOKIE_NAME = "litecron_lang"
LANG_ZH = "zh-CN"
LANG_EN = "en"
SUPPORTED_LANGUAGES = (LANG_ZH, LANG_EN)
DEFAULT_LANGUAGE = LANG_ZH
FALLBACK_LANGUAGE = LANG_EN
LANG_MODE_SYSTEM = "system"

CATALOGS: Dict[str, Dict[str, str]] = {
    LANG_ZH: ZH_MESSAGES,
    LANG_EN: EN_MESSAGES,
}


def _check_catalogs() -> None:
    """比对两份字典的 key 集合：只告警不抛异常，WebUI 不该因漏一个 key 起不来。"""
    zh_keys = set(ZH_MESSAGES)
    en_keys = set(EN_MESSAGES)
    missing = sorted(zh_keys - en_keys)
    extra = sorted(en_keys - zh_keys)
    if missing:
        log_error(
            f"[i18n] en 字典缺少 {len(missing)} 个键（将回退中文）: "
            + ", ".join(missing[:10])
            + (" ..." if len(missing) > 10 else "")
        )
    if extra:
        log_error(
            f"[i18n] en 字典多出 {len(extra)} 个键（无对应中文）: "
            + ", ".join(extra[:10])
            + (" ..." if len(extra) > 10 else "")
        )


def _negotiate(accept_language: Optional[str]) -> str:
    """按 q 值取浏览器首选语言：zh* -> 简体中文，其余 -> English。"""
    candidates = []
    for index, chunk in enumerate((accept_language or "").split(",")):
        chunk = chunk.strip()
        if not chunk:
            continue
        segments = chunk.split(";")
        tag = segments[0].strip().lower()
        if not tag:
            continue
        quality = 1.0
        for attr in segments[1:]:
            attr = attr.strip()
            if attr.startswith("q="):
                try:
                    quality = float(attr[2:])
                except ValueError:
                    quality = 0.0
        if quality <= 0:
            continue
        candidates.append((quality, index, tag))

    if not candidates:
        return FALLBACK_LANGUAGE

    # q 降序；同 q 保持浏览器给出的顺序
    candidates.sort(key=lambda item: (-item[0], item[1]))
    for _, _, tag in candidates:
        if tag == "*":
            continue
        if tag == "zh" or tag.startswith("zh-"):
            return LANG_ZH
        return LANG_EN
    return FALLBACK_LANGUAGE


def resolve_language(
    cookie_value: Optional[str], accept_language: Optional[str]
) -> str:
    """解析请求语言：合法 Cookie 优先，否则按 Accept-Language 协商。"""
    if cookie_value in SUPPORTED_LANGUAGES:
        return cookie_value
    return _negotiate(accept_language)


def language_mode(cookie_value: Optional[str]) -> str:
    """控件选中态：Cookie 缺失或非法时视为「跟随系统」。"""
    if cookie_value in SUPPORTED_LANGUAGES:
        return cookie_value
    return LANG_MODE_SYSTEM


def init_request_language() -> str:
    """在 before_request 中调用：把解析结果挂到 flask.g。"""
    cookie_value = request.cookies.get(LANG_COOKIE_NAME)
    lang = resolve_language(cookie_value, request.headers.get("Accept-Language"))
    g.lang = lang
    g.lang_mode = language_mode(cookie_value)
    return lang


def current_language() -> str:
    """当前请求语言；无请求上下文（CLI/日志）时回退简体中文。"""
    if has_request_context():
        lang = getattr(g, "lang", None)
        if lang in SUPPORTED_LANGUAGES:
            return lang
    return DEFAULT_LANGUAGE


def _lookup(lang: str, key: str) -> Optional[str]:
    catalog = CATALOGS.get(lang)
    if not catalog:
        return None
    value = catalog.get(key)
    return value if isinstance(value, str) else None


def t(key: str, **params) -> str:
    """取文案：目标语言 -> 简体中文 -> key 本身；支持 ``{name}`` 占位替换。"""
    text = _lookup(current_language(), key)
    if text is None:
        text = _lookup(DEFAULT_LANGUAGE, key)
    if text is None:
        return key
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def client_catalog(lang: Optional[str] = None) -> Dict[str, str]:
    """注入给浏览器的字典：以简体中文打底，目标语言覆盖，缺翻项天然回退中文。"""
    catalog = dict(ZH_MESSAGES)
    target = CATALOGS.get(lang or current_language())
    if target:
        catalog.update({k: v for k, v in target.items() if isinstance(v, str)})
    return catalog


def install(app) -> None:
    """注册 Jinja 全局与语言上下文。"""
    app.jinja_env.globals["_"] = t

    @app.context_processor
    def _inject_language():  # pragma: no cover - 由 Flask 调用
        lang = current_language()
        mode = getattr(g, "lang_mode", LANG_MODE_SYSTEM) if has_request_context() else LANG_MODE_SYSTEM
        return {
            "lang": lang,
            "lang_mode": mode,
            "i18n_catalog": client_catalog(lang),
        }


_check_catalogs()
