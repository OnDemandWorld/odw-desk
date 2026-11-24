"""
Regression tests for full-audit round 1, batch 5 (.ocr-reports/full-audit.json).

Covers the policy-engine cluster:
- #32 trigger_config validated at creation; malformed entries skipped at runtime
- #33 metadata conditions are a mandatory AND-gate; metadata-only policies fire
- #34 word-boundary keyword matching (no 'vs' in 'TVs', no 'law' in 'flaw')
- #86 append_disclaimer is not a violation; single evaluation pass
- #87 PolicyEngine defaults to the current deployment scope
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from desk.policy.engine import PolicyEngine, default_deployment_id, validate_trigger_config


def make_policy(**kwargs):
    base = {
        "id": uuid4(),
        "name": "p",
        "trigger_type": "keyword",
        "trigger_config": {},
        "action": "block",
        "action_payload": {},
        "applies_to": "pre",
        "priority": 100,
        "restricted_topics": None,
        "is_active": True,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return FakeResult(self.rows)


class TestTriggerConfigValidation:
    """#32: bad shapes/regexes rejected at creation, skipped at runtime."""

    def test_non_list_keywords_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_trigger_config({"keywords": 5})

    def test_invalid_regex_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_trigger_config({"patterns": ["("]})

    def test_non_dict_metadata_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_trigger_config({"metadata": []})

    def test_valid_config_accepted(self) -> None:
        validate_trigger_config(
            {"keywords": ["refund"], "patterns": [r"\d+"], "metadata": {"channel": "whatsapp"}}
        )

    async def test_create_policy_rejects_bad_config(self) -> None:
        engine = PolicyEngine(MagicMock())
        with pytest.raises(ValueError):
            await engine.create_policy(
                name="bad", trigger_type="keyword", action="block", trigger_config={"keywords": 5}
            )

    def test_malformed_runtime_config_skipped_not_raised(self) -> None:
        engine = PolicyEngine(FakeDB([]))
        policy = make_policy(trigger_config={"keywords": 5, "patterns": ["("], "metadata": []})
        # Must not raise: previously TypeError/re.error on every message.
        assert engine._evaluate_trigger(policy, "anything") is False


class TestMetadataAndGate:
    """#33: metadata conditions must constrain content matches."""

    async def test_keyword_plus_metadata_requires_metadata_match(self) -> None:
        policy = make_policy(
            trigger_config={"keywords": ["refund"], "metadata": {"channel": "whatsapp"}},
            action="block",
        )
        engine = PolicyEngine(FakeDB([policy]))
        wrong_channel = await engine.run_pre_generation_hooks(
            "I want a refund", conversation_metadata={"channel": "webchat"}
        )
        assert wrong_channel["policy_decision"] == "allow"
        right_channel = await engine.run_pre_generation_hooks(
            "I want a refund", conversation_metadata={"channel": "whatsapp"}
        )
        assert right_channel["policy_decision"] == "block"
        no_metadata = await engine.run_pre_generation_hooks("I want a refund")
        assert no_metadata["policy_decision"] == "allow"

    async def test_metadata_only_policy_fires_on_match(self) -> None:
        policy = make_policy(
            trigger_config={"metadata": {"channel": "email"}}, action="escalate"
        )
        engine = PolicyEngine(FakeDB([policy]))
        hit = await engine.run_pre_generation_hooks(
            "hello", conversation_metadata={"channel": "email"}
        )
        assert hit["policy_decision"] == "escalate"
        miss = await engine.run_pre_generation_hooks(
            "hello", conversation_metadata={"channel": "webchat"}
        )
        assert miss["policy_decision"] == "allow"


class TestWordBoundaryMatching:
    """#34: substring false positives must not fire topic policies."""

    async def test_vs_does_not_match_tvs(self) -> None:
        policy = make_policy(trigger_config={"topics": ["competitor"]}, action="block")
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("I love my new TVs")
        assert result["policy_decision"] == "allow"

    async def test_law_does_not_match_flaw(self) -> None:
        policy = make_policy(trigger_config={"topics": ["legal"]}, action="block")
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("there is a flaw in my order")
        assert result["policy_decision"] == "allow"

    async def test_whole_word_still_matches(self) -> None:
        policy = make_policy(trigger_config={"topics": ["legal"]}, action="block")
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("I will call my lawyer")
        assert result["policy_decision"] == "block"

    async def test_cjk_keyword_substring_semantics(self) -> None:
        policy = make_policy(trigger_config={"keywords": ["退款"]}, action="block")
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("我要退款谢谢")
        assert result["policy_decision"] == "block"


class TestDisclaimerSinglePass:
    """#86: disclaimer-only matches are valid and collected once."""

    async def test_disclaimer_not_a_violation(self) -> None:
        policy = make_policy(
            trigger_config={"keywords": ["discount"]},
            action="append_disclaimer",
            action_payload={"disclaimer_text": "Terms apply."},
            applies_to="post",
        )
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_post_generation_hooks("Take a discount today", "original")
        assert result["is_valid"] is True
        assert result["action"] == "allow"
        assert result["violations"] == []
        assert result["append_texts"] == ["Terms apply."]


class TestDeploymentScoping:
    """#87: engine defaults to the current deployment."""

    def test_default_deployment_scope(self) -> None:
        engine = PolicyEngine(FakeDB([]))
        assert engine.deployment_id == default_deployment_id()

    def test_explicit_deployment_respected(self) -> None:
        explicit = uuid4()
        engine = PolicyEngine(FakeDB([]), deployment_id=explicit)
        assert engine.deployment_id == explicit

    async def test_set_policy_active_scoped(self) -> None:
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)
        engine = PolicyEngine(db)
        assert await engine.set_policy_active(uuid4(), False) is None
        query = db.execute.await_args.args[0]
        compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
        assert "deployment_id" in compiled
