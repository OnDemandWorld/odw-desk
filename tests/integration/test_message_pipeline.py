"""
ODW.ai Desk — Message Pipeline Integration Test

Simulates a WhatsApp inbound webhook and verifies that the message is
persisted, routed through the event bus, processed by the AI worker,
and dispatched to the WhatsApp adapter.

This test requires a running PostgreSQL database and Redis server.
"""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from desk.config import get_settings
from desk.db import AsyncSessionLocal
from desk.main import app
from desk.models.conversation import Conversation
from desk.models.customer import Customer
from desk.models.message import Message


def _sign_whatsapp_payload(payload: dict) -> tuple[bytes, str]:
    """Return the raw JSON body and X-Hub-Signature-256 header for the payload."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    token = get_settings().whatsapp_webhook_verify_token.encode("utf-8")
    signature = "sha256=" + hmac.new(token, body, hashlib.sha256).hexdigest()
    return body, signature


@pytest.fixture(autouse=True)
def clean_database():
    """Truncate all application tables before and after each integration test."""
    _truncate_tables()
    yield
    _truncate_tables()


def _truncate_tables() -> None:
    """Delete all rows from the main application tables using a sync connection."""
    import psycopg2

    url = str(get_settings().database_url).replace("postgresql+asyncpg://", "postgresql://")
    tables = [
        "messages",
        "conversations",
        "customers",
        "ai_configurations",
        "brand_personas",
        "response_policies",
        "audit_logs",
        "license_state",
        "agents",
    ]
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(f"DELETE FROM {table}")
            conn.commit()


@pytest.fixture
def client():
    """Return a FastAPI TestClient with full lifespan."""
    with TestClient(app) as test_client:
        yield test_client


def build_whatsapp_payload(
    phone_number: str = "+5511999887766",
    body: str = "Hello, I need help",
) -> dict:
    """Return a sample Meta WhatsApp Cloud API webhook payload."""
    import uuid

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+1234567890",
                                "phone_number_id": "PNID",
                            },
                            "messages": [
                                {
                                    "from": phone_number,
                                    "id": f"wamid.{uuid.uuid4().hex}",
                                    "timestamp": str(int(datetime.now(tz=UTC).timestamp())),
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


@pytest.fixture
def whatsapp_payload():
    """Return a unique sample WhatsApp webhook payload."""
    return build_whatsapp_payload()


async def _get_customer_by_identifier(identifier: str) -> Customer | None:
    """Helper to fetch a customer by WhatsApp identifier."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Customer).where(Customer.channel_identifiers["whatsapp"].as_string() == identifier)
        )
        return result.scalar_one_or_none()


async def _get_conversation_for_customer(customer_id: str) -> Conversation | None:
    """Helper to fetch the first conversation for a customer."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _count_messages_for_conversation(conversation_id: str) -> int:
    """Helper to count messages in a conversation."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        return len(result.scalars().all())


@pytest.mark.asyncio
async def test_whatsapp_webhook_creates_conversation_and_message(client, whatsapp_payload):
    """Inbound WhatsApp webhook should create customer, conversation and message."""
    body, signature = _sign_whatsapp_payload(whatsapp_payload)
    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "received"
    assert data["message_count"] == 1
    assert len(data["routed"]) == 1
    assert data["routed"][0]["status"] == "routed"

    # Verify customer was created
    customer = await _get_customer_by_identifier("+5511999887766")
    assert customer is not None
    assert customer.channel_identifiers.get("whatsapp") == "+5511999887766"

    # Verify conversation was created
    conversation = await _get_conversation_for_customer(customer.id)
    assert conversation is not None
    assert conversation.channel == "whatsapp"
    assert conversation.status == "active"

    # Verify the customer message was persisted
    messages = await _count_messages_for_conversation(conversation.id)
    assert messages >= 1


@pytest.mark.asyncio
async def test_whatsapp_pipeline_dispatches_ai_response(client, whatsapp_payload):
    """The full pipeline should persist an AI response after processing the routed event."""
    body, signature = _sign_whatsapp_payload(whatsapp_payload)
    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )
    assert response.status_code == 200

    # Allow the message processor worker to consume the event and dispatch
    await asyncio.sleep(1.5)

    customer = await _get_customer_by_identifier("+5511999887766")
    assert customer is not None

    conversation = await _get_conversation_for_customer(customer.id)
    assert conversation is not None

    # There should be at least two messages: customer + AI response
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
        messages = result.scalars().all()

    sender_types = [m.sender_type for m in messages]
    assert "customer" in sender_types
    assert "ai" in sender_types

    ai_messages = [m for m in messages if m.sender_type == "ai"]
    assert len(ai_messages) >= 1
    assert "We'll get back to you shortly" in ai_messages[0].content
