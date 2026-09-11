"""
ODW.ai Desk — Admin APIs (AGENT-003, AGENT-004)

Admin setup wizard, configuration management, and compliance APIs.
"""

import csv
import hashlib
import io
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid5

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from desk.compliance.service import VALID_DELETE_MODES, ComplianceService
from desk.config import get_settings
from desk.dependencies import get_db
from desk.models.ai_configuration import AIConfiguration
from desk.models.audit_log import AuditLog
from desk.security.rbac import require_role
from desk.utils.encryption import FieldEncryption

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

_FRONTIER_PROVIDERS = ("openai", "anthropic")


def _deployment_uuid() -> UUID:
    """Map the free-form deployment id onto the UUID column deterministically."""
    deployment_id = get_settings().deployment_id
    try:
        return UUID(deployment_id)
    except (ValueError, AttributeError):
        return uuid5(NAMESPACE_DNS, deployment_id)


# ============================================================================
# Setup Wizard API (AGENT-003)
# ============================================================================


@router.get("/setup/status")
async def get_setup_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """
    Get setup wizard status.

    Returns which configuration steps are complete.
    """
    steps = {
        "vault_configured": False,
        "whatsapp_configured": False,
        "ai_model_configured": False,
        "license_activated": False,
    }

    settings = get_settings()

    # Check Vault configuration
    if settings.vault_url and settings.vault_api_key != "vk_dev_local_key":
        steps["vault_configured"] = True

    # Check WhatsApp configuration
    if settings.whatsapp_access_token and settings.whatsapp_phone_number_id:
        steps["whatsapp_configured"] = True

    # Check AI model configuration
    query = select(AIConfiguration).limit(1)
    result = await db.execute(query)
    ai_config = result.scalar_one_or_none()
    if ai_config:
        steps["ai_model_configured"] = True

    # Check license
    if settings.license_key != "free":
        steps["license_activated"] = True

    return {
        "steps": steps,
        "completed_steps": sum(1 for v in steps.values() if v),
        "total_steps": len(steps),
        "setup_complete": all(steps.values()),
    }


@router.post("/setup/vault")
async def configure_vault(
    vault_url: str = Query(..., description="Vault API URL"),
    vault_api_key: str = Query(..., description="Vault API key"),
    collection_id: str = Query(..., description="Default collection ID"),
) -> dict[str, Any]:
    """Configure Vault connection."""
    # In production, this would update settings in database
    logger.info("Vault configured", vault_url=vault_url, collection_id=collection_id)
    return {
        "success": True,
        "message": "Vault configuration saved",
        "vault_url": vault_url,
        "collection_id": collection_id,
    }


@router.post("/setup/whatsapp")
async def configure_whatsapp(
    access_token: str = Query(..., description="WhatsApp access token"),
    phone_number_id: str = Query(..., description="Phone number ID"),
    business_account_id: str = Query(..., description="Business account ID"),
    webhook_verify_token: str = Query(..., description="Webhook verify token"),
) -> dict[str, Any]:
    """Configure WhatsApp Business API."""
    logger.info("WhatsApp configured", phone_number_id=phone_number_id)
    return {
        "success": True,
        "message": "WhatsApp configuration saved",
        "phone_number_id": phone_number_id,
    }


@router.post("/setup/ai-model")
async def configure_ai_model(
    provider: str = Query(..., description="Model provider (ollama, openai, anthropic)"),
    model_name: str = Query(..., description="Model name"),
    api_key: str = Query(None, description="API key (if required)"),
    endpoint: str = Query(None, description="Endpoint URL (if required)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Configure AI model."""
    # Create or update AI configuration
    query = select(AIConfiguration).limit(1)
    result = await db.execute(query)
    ai_config = result.scalar_one_or_none()

    if not ai_config:
        ai_config = AIConfiguration(
            deployment_id=_deployment_uuid(),
            system_prompt="You are a helpful customer support agent.",
        )
        db.add(ai_config)

    if provider in _FRONTIER_PROVIDERS:
        ai_config.frontier_provider = provider
        ai_config.frontier_model_name = model_name
        if api_key:
            # Derive a 32-byte AES key from the app secret (same fallback as
            # FieldEncryption.from_env, but sourced from settings so this works
            # even when SECRET_KEY is not exported to the environment).
            key = hashlib.sha256(get_settings().secret_key.encode()).digest()
            encrypted = FieldEncryption(key).encrypt(api_key)
            ai_config.frontier_api_key_encrypted = encrypted.encode("ascii")
    else:
        # Local model (ollama / vLLM / …): provider itself is not persisted;
        # the engine instantiates the local provider from settings.
        ai_config.local_model_name = model_name
        if endpoint:
            ai_config.local_model_endpoint = endpoint

    await db.commit()

    logger.info("AI model configured", provider=provider, model=model_name)

    return {
        "success": True,
        "message": "AI model configuration saved",
        "provider": provider,
        "model": model_name,
    }


# ============================================================================
# Configuration APIs (AGENT-004)
# ============================================================================


@router.get("/config/ai")
async def get_ai_configuration(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Get current AI configuration."""
    query = select(AIConfiguration).limit(1)
    result = await db.execute(query)
    ai_config = result.scalar_one_or_none()

    if not ai_config:
        return {"configured": False}

    routing_policy = ai_config.routing_policy or {}
    return {
        "configured": True,
        "frontier_provider": ai_config.frontier_provider,
        "frontier_model_name": ai_config.frontier_model_name,
        "local_model_name": ai_config.local_model_name,
        "local_model_endpoint": ai_config.local_model_endpoint,
        "confidence_threshold": ai_config.confidence_threshold,
        "max_tokens": routing_policy.get("max_tokens"),
        "temperature": routing_policy.get("temperature"),
        "pii_shield_enabled": ai_config.pii_shield_enabled,
        "created_at": ai_config.created_at.isoformat() if ai_config.created_at else None,
    }


@router.put("/config/ai")
async def update_ai_configuration(
    confidence_threshold: float = Query(None, ge=0.0, le=1.0),
    max_tokens: int = Query(None, ge=1, le=4096),
    temperature: float = Query(None, ge=0.0, le=2.0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update AI configuration parameters."""
    query = select(AIConfiguration).limit(1)
    result = await db.execute(query)
    ai_config = result.scalar_one_or_none()

    if not ai_config:
        raise HTTPException(status_code=404, detail="AI configuration not found")

    if confidence_threshold is not None:
        ai_config.confidence_threshold = confidence_threshold

    # max_tokens / temperature are tuning overrides carried in routing_policy.
    routing_policy = dict(ai_config.routing_policy or {})
    if max_tokens is not None:
        routing_policy["max_tokens"] = max_tokens
    if temperature is not None:
        routing_policy["temperature"] = temperature
    ai_config.routing_policy = routing_policy

    await db.commit()

    logger.info("AI configuration updated")

    return {
        "success": True,
        "confidence_threshold": ai_config.confidence_threshold,
        "max_tokens": routing_policy.get("max_tokens"),
        "temperature": routing_policy.get("temperature"),
    }


@router.get("/config/pii")
async def get_pii_configuration() -> dict[str, Any]:
    """Get PII shield configuration."""
    settings = get_settings()
    return {
        "pii_shield_enabled": settings.pii_shield_enabled,
        "frontier_allowed_with_redaction": settings.pii_frontier_allowed_with_redaction,
    }


@router.put("/config/pii")
async def update_pii_configuration(
    pii_shield_enabled: bool = Query(None),
    frontier_allowed_with_redaction: bool = Query(None),
) -> dict[str, Any]:
    """Update PII shield configuration."""
    # In production, this would update settings in database
    logger.info(
        "PII configuration updated",
        pii_shield_enabled=pii_shield_enabled,
        frontier_allowed_with_redaction=frontier_allowed_with_redaction,
    )
    return {
        "success": True,
        "message": "PII configuration updated",
    }


# ============================================================================
# Compliance APIs (AGENT-004)
# ============================================================================


@router.get("/compliance/audit-logs")
async def get_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: str = Query(None, description="Filter by action type"),
    actor_id: UUID = Query(None, description="Filter by actor ID"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get audit logs with optional filters."""
    query = select(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)

    query = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": str(log.id),
                "action": log.action,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "actor_type": log.actor_type,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id),
                "details": log.details,
                "ip_address": log.ip_address,
                "previous_hash": log.previous_hash[:16] + "..." if log.previous_hash else None,
                "hash": log.hash[:16] + "..." if log.hash else None,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
            for log in logs
        ],
        "total": len(logs),
        "limit": limit,
        "offset": offset,
    }


# ----------------------------------------------------------------------------
# Compliance audit report export (V1.4 F-3)
# ----------------------------------------------------------------------------

# Columns emitted for each audit record (JSON + CSV share this ordering).
_AUDIT_REPORT_COLUMNS = [
    "id",
    "timestamp",
    "event_type",
    "actor_type",
    "actor_id",
    "resource_type",
    "resource_id",
    "action",
    "details",
    "ip_address",
    "previous_hash",
    "hash",
]


def build_audit_report_query(
    start: datetime | None = None,
    end: datetime | None = None,
    actor: str | None = None,
    action: str | None = None,
    limit: int = 1000,
) -> Select[tuple[AuditLog]]:
    """
    Build the filtered audit-report query (P1).

    Filters (all optional, combined with AND):
    - ``start``/``end``: inclusive timestamp range (``AuditLog.timestamp``).
    - ``actor``: exact match on ``actor_id`` (compared as text — actor ids are
      logged as opaque strings such as ``"system"`` / ``"admin-1"``).
    - ``action``: exact match on ``action``.

    Results are newest-first and capped at ``limit``.
    """
    query = select(AuditLog)
    if start is not None:
        query = query.where(AuditLog.timestamp >= start)
    if end is not None:
        query = query.where(AuditLog.timestamp <= end)
    if actor:
        query = query.where(cast(AuditLog.actor_id, String) == actor)
    if action:
        query = query.where(AuditLog.action == action)
    return query.order_by(AuditLog.timestamp.desc()).limit(limit)


def _audit_record_dict(log: AuditLog) -> dict[str, Any]:
    """Serialize an AuditLog row to a plain dict for JSON/CSV export."""
    return {
        "id": str(log.id),
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "event_type": log.event_type,
        "actor_type": log.actor_type,
        "actor_id": str(log.actor_id) if log.actor_id else None,
        "resource_type": log.resource_type,
        "resource_id": str(log.resource_id),
        "action": log.action,
        "details": log.details,
        "ip_address": log.ip_address,
        "previous_hash": log.previous_hash,
        "hash": log.hash,
    }


def _parse_report_timestamp(value: str, field: str) -> datetime:
    """Parse an ISO-8601 query timestamp, tolerating a trailing 'Z'."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid {field} timestamp; expected ISO-8601"
        ) from exc


@router.get("/compliance/report", dependencies=[Depends(require_role("admin"))])
async def get_compliance_report(
    format: str = Query("json", description="Output format: json (default) or csv"),
    start: str = Query(None, description="Inclusive start timestamp (ISO-8601)"),
    end: str = Query(None, description="Inclusive end timestamp (ISO-8601)"),
    actor: str = Query(None, description="Filter by actor id"),
    action: str = Query(None, description="Filter by action"),
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Export compliance audit records (SOC2/GDPR evidence) as JSON or CSV.

    Guarded by ``require_role('admin')``. Records are filtered by an optional
    time range (``start``/``end``), ``actor``, and ``action``, newest-first.
    CSV is produced with the stdlib ``csv`` module (no extra dependency).
    """
    if format not in ("json", "csv"):
        raise HTTPException(status_code=422, detail="format must be 'json' or 'csv'")

    start_dt = _parse_report_timestamp(start, "start") if start else None
    end_dt = _parse_report_timestamp(end, "end") if end else None

    query = build_audit_report_query(
        start=start_dt, end=end_dt, actor=actor, action=action, limit=limit
    )
    result = await db.execute(query)
    logs = result.scalars().all()
    records = [_audit_record_dict(log) for log in logs]

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=_AUDIT_REPORT_COLUMNS)
        writer.writeheader()
        for record in records:
            row = dict(record)
            # Flatten the details dict to a JSON string for CSV cells.
            row["details"] = "" if row["details"] is None else str(row["details"])
            writer.writerow(row)
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=compliance_report.csv"},
        )

    return {
        "format": "json",
        "total": len(records),
        "filters": {"start": start, "end": end, "actor": actor, "action": action},
        "records": records,
    }


@router.post("/compliance/export")
async def export_customer_data(
    customer_id: UUID = Query(..., description="Customer ID to export"),
    actor_id: str = Query("system", description="Actor requesting the export (for audit)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Export customer data (GDPR Article 20 - Right to data portability).

    Aggregates the customer's profile, conversations, and messages into a
    machine-readable JSON payload and writes an audit record.
    """
    service = ComplianceService(db)
    try:
        export = await service.export_customer_data(customer_id, actor_id=actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"success": True, "format": "json", "export": export}


@router.post("/compliance/delete")
async def delete_customer_data(
    customer_id: UUID = Query(..., description="Customer ID to delete"),
    reason: str = Query(..., description="Deletion reason"),
    mode: str = Query("anonymize", description="Erasure strategy: anonymize (default) or hard"),
    actor_id: str = Query("system", description="Actor requesting the deletion (for audit)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Delete customer data (GDPR Article 17 - Right to erasure).

    ``anonymize`` (default) replaces PII with placeholders while preserving
    conversation structure; ``hard`` deletes messages, conversations, and the
    customer record. The operation is transactional and writes an audit record.
    """
    if mode not in VALID_DELETE_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mode '{mode}'; expected one of {list(VALID_DELETE_MODES)}",
        )

    service = ComplianceService(db)
    try:
        summary = await service.delete_customer_data(
            customer_id, mode=mode, actor_id=actor_id, reason=reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"success": True, **summary}


@router.get("/compliance/reports")
async def get_compliance_reports() -> dict[str, Any]:
    """Get available compliance reports."""
    return {
        "reports": [
            {
                "id": "data-processing-summary",
                "name": "Data Processing Summary",
                "description": "Summary of data processing activities",
                "generated_at": None,
            },
            {
                "id": "pii-detection-report",
                "name": "PII Detection Report",
                "description": "Report of PII detection and redaction activities",
                "generated_at": None,
            },
            {
                "id": "ai-decision-log",
                "name": "AI Decision Log",
                "description": "Log of all AI decisions and confidence scores",
                "generated_at": None,
            },
        ]
    }
