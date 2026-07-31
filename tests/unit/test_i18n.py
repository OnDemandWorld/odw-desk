"""
ODW.ai Desk — Unit Tests for Multilingual i18n (F-Desk-1 / M4)

Covers the translation service (en/zh values + fallback to en), the pure-Python
language detector (Chinese vs English), the prompt-builder language instruction,
and the engine fallback path (a Chinese inbound message yields a Chinese reply).

No live DB / LLM is needed: the engine test bypasses __init__ and forces the
safe fallback path with a PII shield that raises.
"""

from desk.ai.engine import AIEngine
from desk.ai.prompt_builder import PromptBuilder
from desk.i18n.detect import detect_language
from desk.i18n.service import reply_language, t

# --- I1: translation service -------------------------------------------------


def test_t_returns_english_value():
    assert t("greeting", "en") == "Hello! How can I help you?"


def test_t_returns_chinese_value():
    assert t("greeting", "zh") == "您好！有什么可以帮您？"


def test_t_falls_back_to_en_for_unknown_language():
    # 'fr' is not a supported language -> English value.
    assert t("greeting", "fr") == "Hello! How can I help you?"


def test_t_falls_back_to_en_for_none_language():
    assert t("escalation_notice", None).startswith("I'm not confident")


def test_t_returns_key_for_missing_key():
    # A key that exists in no language resolves to the raw key (never crashes).
    assert t("does_not_exist", "zh") == "does_not_exist"


def test_t_applies_format_substitution():
    reply = t("fallback_reply", "en", snippet="hello")
    assert reply == "Thanks for your message! We'll get back to you shortly. (Received: hello)"


def test_t_applies_format_substitution_chinese():
    reply = t("fallback_reply", "zh", snippet="你好")
    assert "你好" in reply
    assert "感谢您的来信" in reply


def test_reply_language_prefers_conversation_language():
    assert reply_language("hello there", conversation_lang="zh") == "zh"


# --- I2: language detection --------------------------------------------------


def test_detect_language_chinese():
    assert detect_language("你好，我需要帮助") == "zh"


def test_detect_language_mixed_with_cjk_is_chinese():
    assert detect_language("Hello 你好") == "zh"


def test_detect_language_english():
    assert detect_language("Hello, I need help with my order") == "en"


def test_detect_language_empty_defaults_to_english():
    assert detect_language("") == "en"
    assert detect_language(None) == "en"


def test_reply_language_detects_from_text():
    assert reply_language("你好") == "zh"
    assert reply_language("hi there") == "en"


# --- I3: prompt builder language instruction ---------------------------------


def test_prompt_includes_chinese_language_instruction():
    prompt = PromptBuilder().build_prompt("你好，我想咨询一下")
    assert "Respond in Chinese." in prompt


def test_prompt_includes_english_language_instruction():
    prompt = PromptBuilder().build_prompt("Hello, I need help")
    assert "Respond in English." in prompt


# --- I4: engine fallback is multilingual -------------------------------------


class _RaisingShield:
    """PII shield stand-in whose analyze() always fails, forcing the fallback."""

    async def analyze(self, _text):
        raise RuntimeError("boom")


def _engine_with_failing_shield() -> AIEngine:
    engine = object.__new__(AIEngine)  # skip heavy __init__ (providers, settings)
    engine.pii_shield = _RaisingShield()
    return engine


async def test_chinese_inbound_yields_chinese_fallback():
    engine = _engine_with_failing_shield()
    reply = await engine.process("conv-1", "你好，我需要帮助", "whatsapp", "+123")
    assert "感谢您的来信" in reply
    assert "你好" in reply  # snippet echoed back


async def test_english_inbound_yields_english_fallback():
    engine = _engine_with_failing_shield()
    reply = await engine.process("conv-2", "Hello, I need help", "whatsapp", "+123")
    assert reply.startswith("Thanks for your message!")
    assert "Hello" in reply
