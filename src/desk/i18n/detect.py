"""
ODW.ai Desk — Language Detection (F-Desk-1 / M4)

Lightweight, dependency-free language detection for reply adaptation.

The suite already ships a fasttext lid model inside Vault, but Desk must not
take a heavy dependency on it (or on any NLP library) just to pick a reply
language. This module provides a pure-Python heuristic that is good enough for
the supported reply languages and, crucially, defaults to English so that
detection failures never change the existing (English) behaviour.
"""

import structlog

logger = structlog.get_logger()

DEFAULT_LANGUAGE = "en"

# Unicode ranges that indicate Chinese (CJK Unified Ideographs + common
# extensions/compatibility blocks). Presence of any of these code points is a
# strong signal the user is writing in Chinese.
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # CJK Unified Ideographs Extension B
)


def _contains_cjk(text: str) -> bool:
    """Return True if any character falls within a CJK ideograph range."""
    for char in text:
        code_point = ord(char)
        for start, end in _CJK_RANGES:
            if start <= code_point <= end:
                return True
    return False


def detect_language(text: str | None) -> str:
    """
    Detect the language of a piece of user text.

    Returns a BCP-47-style short code ('en', 'zh', ...). The heuristic only
    distinguishes the currently supported reply languages: text containing CJK
    ideographs is classified as Chinese ('zh'); everything else (including empty
    or ``None`` input) falls back to English ('en').

    Args:
        text: Inbound user text (may be empty or None).

    Returns:
        Detected language code; defaults to 'en' on any ambiguity or failure.
    """
    if not text:
        return DEFAULT_LANGUAGE

    try:
        return "zh" if _contains_cjk(text) else DEFAULT_LANGUAGE
    except Exception as exc:  # pragma: no cover - defensive, heuristic is total
        logger.warning("Language detection failed, defaulting to en", error=str(exc))
        return DEFAULT_LANGUAGE
