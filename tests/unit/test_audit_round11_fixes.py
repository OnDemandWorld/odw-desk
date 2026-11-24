"""
Regression tests for full-audit round 1, batch 11 (.ocr-reports/full-audit.json).

Covers AI quality & sovereignty:
- #53 Vault retrieval runs for LOCAL_MODEL_ONLY turns (redacted query)
- #54 knowledge relevance scaled by absolute best-hit quality
- #55 CJK-aware length scoring
- #56 CN phone detection covers +86 and separator formats
- #57 non-English text fails closed to LOCAL_MODEL_ONLY
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestCnPhoneFormats:
    """#56: +86 and separated CN mobiles must be detected."""

    def test_plus86_detected(self) -> None:
        from desk.ai.pii_shield import _cn_recognizer_results

        results = _cn_recognizer_results("call me at +8613812345678 please")
        assert any(r.entity_type == "PHONE_NUMBER" for r in results)

    def test_spaced_format_detected(self) -> None:
        from desk.ai.pii_shield import _cn_recognizer_results

        results = _cn_recognizer_results("我的电话 138 1234 5678 谢谢")
        assert any(r.entity_type == "PHONE_NUMBER" for r in results)

    def test_hyphenated_format_detected(self) -> None:
        from desk.ai.pii_shield import _cn_recognizer_results

        results = _cn_recognizer_results("tel: 138-1234-5678")
        assert any(r.entity_type == "PHONE_NUMBER" for r in results)

    def test_wrong_digit_count_not_matched(self) -> None:
        from desk.ai.pii_shield import _cn_recognizer_results

        results = _cn_recognizer_results("order 138 1234 567 shipped")  # 10 digits
        assert not any(r.entity_type == "PHONE_NUMBER" for r in results)

    def test_bare_format_still_detected(self) -> None:
        from desk.ai.pii_shield import _cn_recognizer_results

        results = _cn_recognizer_results("number 13812345678 ok")
        assert any(r.entity_type == "PHONE_NUMBER" for r in results)


class TestNonEnglishFailClosed:
    """#57: undetected PII in Chinese text must not reach frontier models."""

    def _shield(self):
        from desk.ai.pii_shield import PIIShield

        shield = PIIShield.__new__(PIIShield)
        shield.analyzer = MagicMock()
        shield.analyzer.analyze = MagicMock(return_value=[])
        shield.anonymizer = MagicMock()
        shield.entity_types = []
        shield.allow_frontier_with_redaction = False
        return shield

    async def test_chinese_text_routes_local(self) -> None:
        from desk.ai.pii_shield import RoutingDirective

        shield = self._shield()
        with patch("desk.admin.runtime_settings.get_override", return_value=None):
            result = await shield.analyze("我是张伟，住在北京市朝阳区建国路88号")
        assert result.pii_detected is False
        assert result.routing_directive == RoutingDirective.LOCAL_MODEL_ONLY

    async def test_english_text_unrestricted(self) -> None:
        from desk.ai.pii_shield import RoutingDirective

        shield = self._shield()
        with patch("desk.admin.runtime_settings.get_override", return_value=None):
            result = await shield.analyze("how do I configure the api integration?")
        assert result.routing_directive == RoutingDirective.NO_RESTRICTION


class TestKnowledgeAbsoluteScale:
    """#54: one irrelevant chunk must not outscore a Vault outage."""

    async def test_weak_single_chunk_below_no_docs_neutral(self) -> None:
        from desk.ai.confidence_scorer import ConfidenceScorer
        from desk.ai.vault_client import RetrievedDocument

        scorer = ConfidenceScorer()
        weak = [RetrievedDocument(content="x", score=0.0001, source_id="f", metadata={})]
        weak_score = scorer._score_knowledge(weak)
        no_docs = scorer._score_knowledge([])
        assert weak_score < no_docs

    async def test_good_hit_still_high(self) -> None:
        from desk.ai.confidence_scorer import ConfidenceScorer
        from desk.ai.vault_client import RetrievedDocument

        scorer = ConfidenceScorer()
        good = [
            RetrievedDocument(content="a", score=0.0164, source_id="f", metadata={}),
            RetrievedDocument(content="b", score=0.0161, source_id="f", metadata={}),
        ]
        assert scorer._score_knowledge(good) > 0.9


class TestCjkLengthScoring:
    """#55: Chinese replies must not be scored as one-word answers."""

    def test_long_chinese_reply_full_score(self) -> None:
        from desk.ai.confidence_scorer import ConfidenceScorer

        scorer = ConfidenceScorer()
        text = "您好，您可以按照以下步骤解决问题：" + "详细步骤说明内容" * 15
        assert scorer._score_length(text) == 1.0

    def test_short_chinese_reply_low_score(self) -> None:
        from desk.ai.confidence_scorer import ConfidenceScorer

        scorer = ConfidenceScorer()
        assert scorer._score_length("好的谢谢") == 0.3

    def test_english_scoring_unchanged(self) -> None:
        from desk.ai.confidence_scorer import ConfidenceScorer

        scorer = ConfidenceScorer()
        text = " ".join(["word"] * 50)
        assert scorer._score_length(text) == 1.0


class TestLocalTurnRetrieval:
    """#53: LOCAL_MODEL_ONLY turns retrieve knowledge with a redacted query."""

    async def test_pii_local_turn_retrieves_redacted(self) -> None:
        from desk.ai.engine import AIEngine
        from desk.ai.model_router import ModelTarget

        engine = AIEngine.__new__(AIEngine)
        engine._refresh_runtime_config = AsyncMock()
        pii = SimpleNamespace(
            pii_detected=True,
            pii_types=["EMAIL"],
            redacted_text="reset password for [EMAIL]",
            routing_directive=SimpleNamespace(value="LOCAL_MODEL_ONLY"),
        )
        engine.pii_shield = SimpleNamespace(analyze=AsyncMock(return_value=pii))
        engine.model_router = SimpleNamespace(
            route=AsyncMock(
                return_value=SimpleNamespace(target=ModelTarget.LOCAL, model_name="m", fallback_chain=[])
            )
        )
        engine.vault_client = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
        engine.confidence_scorer = SimpleNamespace(
            score=AsyncMock(
                return_value=SimpleNamespace(score=0.9, should_escalate=False, reasoning="", factors={})
            )
        )
        llm_response = SimpleNamespace(text="answer", provider="p", model="m", tokens_used=1, metadata={})
        engine.local_provider = SimpleNamespace(generate=AsyncMock(return_value=llm_response))
        engine.frontier_provider = None
        engine._escalate_conversation = AsyncMock()
        policy = MagicMock()
        policy.run_pre_generation_hooks = AsyncMock(
            return_value={"policy_decision": "allow", "triggers": [], "redirect_response": None}
        )
        policy.run_post_generation_hooks = AsyncMock(
            return_value={"action": "allow", "violations": [], "append_texts": [], "is_valid": True}
        )
        builder = MagicMock()
        builder.build_prompt_with_persona = AsyncMock(return_value=("sys", "prompt"))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=MagicMock())
        cm.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("desk.ai.engine.PolicyEngine", return_value=policy),
            patch("desk.ai.engine.AsyncSessionLocal", return_value=cm),
            patch("desk.ai.engine.get_prompt_builder_with_persona", new=AsyncMock(return_value=builder)),
        ):
            await engine.process_detailed(
                str(uuid4()), "reset password for a@b.com", "webchat", "v1"
            )
        engine.vault_client.retrieve.assert_awaited_once()
        assert engine.vault_client.retrieve.await_args.kwargs["query"] == "reset password for [EMAIL]"
