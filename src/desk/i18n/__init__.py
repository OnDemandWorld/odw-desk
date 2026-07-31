"""
ODW.ai Desk — Internationalization (i18n) package (F-Desk-1 / M4).

Multilingual reply adaptation: language detection, message resources, and a
translation service. Defaults to English so behaviour is backward compatible.
"""

from desk.i18n.detect import DEFAULT_LANGUAGE, detect_language
from desk.i18n.service import reply_language, t

__all__ = [
    "DEFAULT_LANGUAGE",
    "detect_language",
    "reply_language",
    "t",
]
