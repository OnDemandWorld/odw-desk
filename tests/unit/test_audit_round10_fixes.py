"""
Regression tests for full-audit round 1, batch 10 (.ocr-reports/full-audit.json).

Covers compliance / crypto / license hardening:
- #39 audit chain appends serialized via advisory lock
- #47 single field-key derivation; optional dedicated encryption key
- #48 license activation requires an HMAC-signed key
- #49 NULL valid_until fails closed; gates re-check expiry directly
- #50 retention anonymizes orphaned customer PII
"""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from desk.config import Settings


def _result(scalar=None, items=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = items if items is not None else []
    r.scalars.return_value.first.return_value = scalar
    return r


def _mock_db(results):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=results)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


class TestAuditChainLock:
    """#39: the chain head read must happen under an advisory lock."""

    async def test_advisory_lock_precedes_head_read(self) -> None:
        from desk.compliance.engine import ComplianceEngine

        db = _mock_db([MagicMock(), _result(scalar=None)])
        engine = ComplianceEngine(db)
        await engine.log_audit_event(
            action="export",
            actor_id="system",
            actor_type="system",
            resource_type="customer",
            resource_id="c1",
        )
        first_query = str(db.execute.await_args_list[0].args[0])
        assert "pg_advisory_xact_lock" in first_query


class TestFieldKeyDerivation:
    """#47: all paths derive the same key; dedicated key honored."""

    def test_from_env_matches_derive_field_key(self) -> None:
        from desk.utils.encryption import FieldEncryption, derive_field_key

        hex_secret = "ab" * 32
        with patch.dict("os.environ", {"SECRET_KEY": hex_secret}):
            via_env = FieldEncryption.from_env("SECRET_KEY")
        via_derive = FieldEncryption(derive_field_key(hex_secret))
        ct = via_env.encrypt("hello")
        assert via_derive.decrypt(ct) == "hello"

    def test_dedicated_encryption_key_used(self) -> None:
        from desk.utils.encryption import derive_field_key, field_encryption_from_settings

        settings = Settings(desk_encryption_key="dedicated", secret_key="s" * 64)
        with patch("desk.config.get_settings", return_value=settings):
            enc = field_encryption_from_settings()
        expected = derive_field_key("dedicated")
        assert enc.decrypt(enc.encrypt("x")) == "x"
        assert expected == hashlib.sha256(b"dedicated").digest()


def _license_state():
    return SimpleNamespace(
        license_key=None,
        tier="free",
        status="active",
        valid_until=None,
        grace_period_ends=None,
        features={},
        last_validated_at=None,
    )


def _signed_key(tier: str, expiry: datetime, secret: str) -> str:
    expiry_str = expiry.isoformat()
    sig = hmac.new(secret.encode(), f"{tier}.{expiry_str}".encode(), hashlib.sha256).hexdigest()
    return f"{tier}.{expiry_str}.{sig}"


class TestSignedLicenseActivation:
    """#48: literal tier words no longer grant licenses."""

    def _manager(self, secret: str):
        from desk.license.manager import LicenseManager

        mgr = LicenseManager(MagicMock())
        mgr._license_state = _license_state()
        mgr.db.commit = AsyncMock()
        settings = Settings(license_activation_secret=secret)
        mgr.settings = settings  # activate reads self.settings, not get_settings()
        return mgr, settings

    async def test_literal_enterprise_rejected(self) -> None:
        mgr, settings = self._manager("lic-secret")
        with patch("desk.license.manager.get_settings", return_value=settings):
            with pytest.raises(ValueError):
                await mgr.activate_license("enterprise")

    async def test_no_secret_rejected(self) -> None:
        mgr, settings = self._manager("")
        with patch("desk.license.manager.get_settings", return_value=settings):
            with pytest.raises(ValueError):
                await mgr.activate_license("anything")

    async def test_signed_key_activates(self) -> None:
        mgr, settings = self._manager("lic-secret")
        expiry = datetime.now(tz=UTC) + timedelta(days=30)
        key = _signed_key("enterprise", expiry, "lic-secret")
        with patch("desk.license.manager.get_settings", return_value=settings):
            out = await mgr.activate_license(key)
        assert out["success"] is True
        assert out["tier"] == "enterprise"
        assert mgr._license_state.valid_until == expiry

    async def test_tampered_signature_rejected(self) -> None:
        mgr, settings = self._manager("lic-secret")
        expiry = datetime.now(tz=UTC) + timedelta(days=30)
        key = _signed_key("enterprise", expiry, "wrong-secret")
        with patch("desk.license.manager.get_settings", return_value=settings):
            with pytest.raises(ValueError):
                await mgr.activate_license(key)

    async def test_expired_key_rejected(self) -> None:
        mgr, settings = self._manager("lic-secret")
        expiry = datetime.now(tz=UTC) - timedelta(days=1)
        key = _signed_key("paid", expiry, "lic-secret")
        with patch("desk.license.manager.get_settings", return_value=settings):
            with pytest.raises(ValueError):
                await mgr.activate_license(key)


class TestLicenseExpiryFailClosed:
    """#49: NULL valid_until and elapsed expiry must deny."""

    async def test_null_valid_until_invalid(self) -> None:
        from desk.license.manager import LicenseManager

        mgr = LicenseManager(MagicMock())
        mgr._license_state = _license_state()
        mgr.db.commit = AsyncMock()
        assert await mgr.validate_license() is False
        assert mgr._license_state.status == "expired"

    def test_gate_rechecks_expiry_directly(self) -> None:
        from desk.license.manager import FeatureGate, LicenseManager

        mgr = LicenseManager(MagicMock())
        state = _license_state()
        state.tier = "enterprise"
        state.status = "active"  # stale cached status
        state.valid_until = datetime.now(tz=UTC) - timedelta(days=10)
        state.grace_period_ends = datetime.now(tz=UTC) - timedelta(days=3)
        mgr._license_state = state
        assert mgr.check_feature_gate(FeatureGate.COMPLIANCE_TOOLS) is False

    def test_null_valid_until_denies_gate(self) -> None:
        from desk.license.manager import FeatureGate, LicenseManager

        mgr = LicenseManager(MagicMock())
        state = _license_state()
        state.tier = "enterprise"
        state.status = "active"
        state.valid_until = None
        mgr._license_state = state
        assert mgr.check_feature_gate(FeatureGate.COMPLIANCE_TOOLS) is False


class TestRetentionCustomerPii:
    """#50: orphaned customers are anonymized by the retention sweep."""

    async def test_orphan_customer_anonymized(self) -> None:
        from desk.compliance.engine import ComplianceEngine

        customer = MagicMock()
        customer.id = "cust-1"
        customer.display_name = "Alice"
        customer.channel_identifiers = {"whatsapp": "+123"}
        db = _mock_db(
            [
                _result(items=[]),  # no expired conversations
                _result(items=[customer]),  # orphaned customer
                MagicMock(),  # advisory lock (audit write)
                _result(scalar=None),  # chain head
            ]
        )
        engine = ComplianceEngine(db)
        summary = await engine.enforce_retention_policy()
        assert summary["anonymized_customers"] == 1
        assert customer.display_name is None
        assert customer.channel_identifiers == {}
