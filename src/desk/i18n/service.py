"""
ODW.ai Desk — i18n Service (F-Desk-1 / M4)

Translation lookup and reply-language resolution.

``t(key, lang, **fmt)`` resolves a message template for a language, falling back
to English for missing languages or missing keys, and applies ``str.format``
substitution when format arguments are supplied. ``reply_language`` decides which
language the AI should reply in for an inbound message.
"""

import structlog

from desk.i18n.detect import DEFAULT_LANGUAGE, detect_language
from desk.i18n.messages import MESSAGES

logger = structlog.get_logger()


def t(key: str, lang: str | None = DEFAULT_LANGUAGE, **fmt: object) -> str:
    """
    Translate a message key into a language.

    Resolution order:
      1. ``MESSAGES[lang][key]`` when both exist;
      2. ``MESSAGES['en'][key]`` when the language or key is missing;
      3. the raw ``key`` itself as a last resort (so callers never crash).

    Any ``fmt`` keyword arguments are substituted into the template via
    ``str.format``. If substitution fails (e.g. a missing placeholder argument),
    the unformatted template is returned rather than raising.

    Args:
        key: Message key (e.g. ``"fallback_reply"``).
        lang: Target language code; ``None`` or unknown codes fall back to 'en'.
        **fmt: Format arguments for templated messages.

    Returns:
        The resolved (and formatted) message string.
    """
    language_table = MESSAGES.get(lang or DEFAULT_LANGUAGE)
    template = language_table.get(key) if language_table else None

    if template is None:
        template = MESSAGES[DEFAULT_LANGUAGE].get(key, key)

    if fmt:
        try:
            return template.format(**fmt)
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning(
                "i18n format substitution failed, returning raw template",
                key=key,
                lang=lang,
                error=str(exc),
            )
            return template

    return template


def reply_language(user_text: str | None, conversation_lang: str | None = None) -> str:
    """
    Decide which language the AI should reply in.

    Prefers an explicitly stored conversation language when provided; otherwise
    detects the language of the most recent inbound user text. Detection failures
    fall back to English so default behaviour is unchanged.

    Args:
        user_text: Most recent inbound user message.
        conversation_lang: Optional language already recorded on the conversation.

    Returns:
        Language code to reply in ('en', 'zh', ...).
    """
    if conversation_lang:
        return conversation_lang
    return detect_language(user_text)


__all__ = ["reply_language", "t"]
