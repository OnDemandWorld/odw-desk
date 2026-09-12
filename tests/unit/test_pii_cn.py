"""回归：中文 PII（手机号/身份证）检测（R1 验收发现，2026-09-12）。"""

import pytest

from desk.ai.pii_shield import PIIShield


@pytest.fixture(scope="module")
def shield():
    return PIIShield()


@pytest.mark.asyncio
async def test_cn_mobile_detected_and_redacted(shield):
    r = await shield.analyze("我的手机号是 13812345678，请回电")
    assert r.pii_detected is True
    assert "PHONE_NUMBER" in r.pii_types
    assert "13812345678" not in r.redacted_text


@pytest.mark.asyncio
async def test_cn_landline_detected(shield):
    r = await shield.analyze("座机 010-88886666 找王女士")
    assert r.pii_detected is True
    assert "PHONE_NUMBER" in r.pii_types


@pytest.mark.asyncio
async def test_cn_id_card_detected(shield):
    r = await shield.analyze("身份证 110101199003078515")
    assert r.pii_detected is True
    assert "ID_CARD" in r.pii_types
    assert "110101199003078515" not in r.redacted_text


@pytest.mark.asyncio
async def test_plain_text_untouched(shield):
    r = await shield.analyze("今天天气不错，想咨询退货政策")
    assert r.pii_detected is False
    assert r.redacted_text == "今天天气不错，想咨询退货政策"
