"""
ODW.ai Desk — Policy Engine Unit Tests

Covers trigger evaluation (keywords / patterns / topics / metadata) and the
pre-/post-generation hook flows against the real ``response_policies``
column vocabulary (trigger_type, trigger_config, action, action_payload,
applies_to, priority, restricted_topics).
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from desk.policy.engine import TOPIC_KEYWORDS, PolicyEngine


def make_policy(
    *,
    trigger_type="keyword",
    trigger_config=None,
    action="block",
    action_payload=None,
    applies_to="pre",
    priority=100,
    restricted_topics=None,
    is_active=True,
):
    return SimpleNamespace(
        id=uuid4(),
        name=f"policy-{uuid4().hex[:8]}",
        trigger_type=trigger_type,
        trigger_config=trigger_config if trigger_config is not None else {},
        action=action,
        action_payload=action_payload if action_payload is not None else {},
        applies_to=applies_to,
        priority=priority,
        restricted_topics=restricted_topics,
        is_active=is_active,
    )


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    """Minimal AsyncSession stand-in: returns canned rows for any query."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return FakeResult(self.rows)


@pytest.fixture
def anyio_policy_rows():
    return [
        make_policy(
            trigger_config={"keywords": ["refund"]},
            action="block",
            action_payload={"redirect_message": "Refunds go through support@"},
            priority=10,
        ),
    ]


class TestEvaluateTrigger:
    def test_keyword_match(self):
        policy = make_policy(trigger_config={"keywords": ["refund"]})
        engine = PolicyEngine(FakeDB([]))
        assert engine._evaluate_trigger(policy, "I want a REFUND please") is True
        assert engine._evaluate_trigger(policy, "I want to book a table") is False

    def test_pattern_match(self):
        policy = make_policy(trigger_config={"patterns": [r"\bfree\s+trial\b"]})
        engine = PolicyEngine(FakeDB([]))
        assert engine._evaluate_trigger(policy, "Can I get a free trial?") is True
        assert engine._evaluate_trigger(policy, "no trial here") is False

    def test_topic_from_trigger_config(self):
        policy = make_policy(trigger_config={"topics": ["pricing"]})
        engine = PolicyEngine(FakeDB([]))
        assert engine._evaluate_trigger(policy, "why is it so expensive?") is True
        assert engine._evaluate_trigger(policy, "hello there") is False

    def test_topic_from_restricted_topics_column(self):
        policy = make_policy(restricted_topics=["legal"])
        engine = PolicyEngine(FakeDB([]))
        assert engine._evaluate_trigger(policy, "I will sue you") is True

    def test_metadata_conditions_must_all_match(self):
        policy = make_policy(
            trigger_config={"metadata": {"channel": "whatsapp", "tier": "free"}}
        )
        engine = PolicyEngine(FakeDB([]))
        assert (
            engine._evaluate_trigger(policy, "anything", {"channel": "whatsapp", "tier": "free"})
            is True
        )
        assert (
            engine._evaluate_trigger(policy, "anything", {"channel": "whatsapp", "tier": "pro"})
            is False
        )
        assert engine._evaluate_trigger(policy, "anything", None) is False

    def test_topic_lexicon_covers_expected_domains(self):
        assert set(TOPIC_KEYWORDS) >= {"competitor", "pricing", "legal", "medical"}


class TestPreGenerationHooks:
    async def test_block_policy_returns_redirect_response(self):
        policy = make_policy(
            trigger_config={"keywords": ["refund"]},
            action="block",
            action_payload={"redirect_message": "Refunds go through support@acme.com"},
        )
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("I demand a refund")

        assert result["policy_decision"] == "block"
        assert result["redirect_response"] == "Refunds go through support@acme.com"
        assert len(result["triggers"]) == 1
        assert result["triggers"][0]["action"] == "block"

    async def test_no_trigger_allows_generation(self):
        policy = make_policy(trigger_config={"keywords": ["refund"]}, action="block")
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("What are your hours?")

        assert result["policy_decision"] == "allow"
        assert result["triggers"] == []
        assert result["redirect_response"] is None

    async def test_redirect_action_sets_canned_reply(self):
        policy = make_policy(
            trigger_config={"topics": ["competitor"]},
            action="redirect",
            action_payload={"response_template": "We only discuss Acme products."},
        )
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("Is Acme better than CompetitorX?")

        assert result["policy_decision"] == "redirect"
        assert result["redirect_response"] == "We only discuss Acme products."

    async def test_escalate_action_reported(self):
        policy = make_policy(
            trigger_config={"topics": ["legal"]}, action="escalate", applies_to="both"
        )
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_pre_generation_hooks("I am calling my lawyer")

        assert result["policy_decision"] == "escalate"

    async def test_priority_ordering_uses_asc(self):
        # Lower priority value wins; assert the SQL orders ascending.
        compiled_calls = []

        class OrderCaptureDB(FakeDB):
            async def execute(self, query):
                compiled_calls.append(query)
                return FakeResult([])

        engine = PolicyEngine(OrderCaptureDB([]))
        await engine.get_active_policies(phase="pre")

        query = compiled_calls[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY response_policies.priority ASC" in sql
        # Phase filter must include applies_to IN ('pre', 'both') — the old
        # code filtered on a non-existent hook_type column.
        assert "applies_to IN" in sql
        assert "hook_type" not in sql


class TestPostGenerationHooks:
    async def test_block_severity_blocks_response(self):
        policy = make_policy(
            trigger_config={"keywords": ["guarantee"]},
            action="block",
            action_payload={"severity": "error"},
            applies_to="post",
        )
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_post_generation_hooks(
            "We offer a 100% money-back guarantee", "original"
        )

        assert result["is_valid"] is False
        assert result["action"] == "block"
        assert result["violations"][0]["severity"] == "error"

    async def test_warning_severity_allows_response(self):
        policy = make_policy(
            trigger_config={"keywords": ["discount"]},
            action="append_disclaimer",
            action_payload={"severity": "warning"},
            applies_to="post",
        )
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_post_generation_hooks("Take a discount today", "original")

        assert result["is_valid"] is False
        assert result["action"] == "allow"

    async def test_clean_response_is_valid(self):
        policy = make_policy(
            trigger_config={"keywords": ["guarantee"]}, action="block", applies_to="post"
        )
        engine = PolicyEngine(FakeDB([policy]))
        result = await engine.run_post_generation_hooks("Sure, let me help!", "original")

        assert result["is_valid"] is True
        assert result["action"] == "allow"
        assert result["violations"] == []
