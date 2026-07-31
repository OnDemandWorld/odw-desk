"""
ODW.ai Desk — Multilingual Message Resources (F-Desk-1 / M4)

String resources for system/fallback messages, organised by language. English
('en') is the source of truth and the fallback language: every key present in
another language must also exist in 'en'. The English values deliberately match
the previously hardcoded strings so that default behaviour is unchanged.

Add a new language by adding a sibling dict keyed by its short code; add a new
message by adding the key to 'en' first, then to each additional language.
"""

from desk.i18n.detect import DEFAULT_LANGUAGE

# Human-readable language names, used when instructing the LLM which language
# to respond in (see prompt_builder). Falls back to the raw code if unknown.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "zh": "Chinese",
}

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Hello! How can I help you?",
        "fallback_reply": (
            "Thanks for your message! We'll get back to you shortly. (Received: {snippet})"
        ),
        "escalation_notice": (
            "I'm not confident I can help with that. Let me connect you with a human "
            "agent who can assist you better."
        ),
        "policy_block_pre": "I'm unable to respond to that message.",
        "policy_block_post": "I apologize, but I cannot provide that response.",
    },
    "zh": {
        "greeting": "您好！有什么可以帮您？",
        "fallback_reply": "感谢您的来信！我们会尽快回复您。（收到：{snippet}）",
        "escalation_notice": "抱歉，我无法确定能否解决该问题。让我为您转接人工客服，以便更好地协助您。",
        "policy_block_pre": "抱歉，我无法回复该消息。",
        "policy_block_post": "很抱歉，我无法提供该回复。",
    },
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(MESSAGES.keys())

__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGE_NAMES",
    "MESSAGES",
    "SUPPORTED_LANGUAGES",
]
