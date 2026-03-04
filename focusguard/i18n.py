"""Locale loader. from focusguard.i18n import t, set_locale"""

from __future__ import annotations
from typing import Any

_CURRENT: dict = {}
_LANG: str = "en"


def set_locale(lang: str) -> None:
    global _CURRENT, _LANG
    lang = lang.lower().strip()
    try:
        if lang == "tr":
            from focusguard.locales.tr import STRINGS
        else:
            from focusguard.locales.en import STRINGS
        _CURRENT = STRINGS
        _LANG = lang
    except ImportError:
        from focusguard.locales.en import STRINGS
        _CURRENT = STRINGS
        _LANG = "en"
    if lang not in ("en", "tr"):
        from focusguard.locales.en import STRINGS as _EN
        _CURRENT = _EN
        _LANG = "en"


def t(key: str, **kwargs: Any) -> Any:
    """
    Return translated string for key.
    Supports format args: t("level_label", n=5) → "LEVEL 5"
    Returns the key itself if not found (never crashes).
    """
    val = _CURRENT.get(key, key)
    if kwargs and isinstance(val, str):
        try:
            return val.format(**kwargs)
        except (KeyError, IndexError):
            return val
    return val


def current_lang() -> str:
    return _LANG


# Bootstrap with English so imports never fail before set_locale() is called
set_locale("en")
