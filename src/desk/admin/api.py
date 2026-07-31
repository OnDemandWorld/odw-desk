"""
ODW.ai Desk — Admin APIs (AGENT-003, AGENT-004)

Admin setup wizard, configuration management, and compliance APIs.
"""

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.compliance.service import VALID_DELETE_MODES, ComplianceService
from desk.config import get_settings
from desk.dependencies import get_db
from desk.models.ai_configuration import AIConfiguration
from desk.models.audit_log import AuditLog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


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
            provider=provider,
            model_name=model_name,
            api_key_encrypted=api_key or "",
            endpoint=endpoint or "",
        )
        db.add(ai_config)
    else:
        ai_config.provider = provider
        ai_config.model_name = model_name
        if api_key:
            ai_config.api_key_encrypted = api_key
        if endpoint:
            ai_config.endpoint = endpoint

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

    return {
        "configured": True,
        "provider": ai_config.provider,
        "model_name": ai_config.model_name,
        "endpoint": ai_config.endpoint,
        "confidence_threshold": ai_config.confidence_threshold,
        "max_tokens": ai_config.max_tokens,
        "temperature": ai_config.temperature,
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
    if max_tokens is not None:
        ai_config.max_tokens = max_tokens
    if temperature is not None:
        ai_config.temperature = temperature

    await db.commit()

    logger.info("AI configuration updated")

    return {
        "success": True,
        "confidence_threshold": ai_config.confidence_threshold,
        "max_tokens": ai_config.max_tokens,
        "temperature": ai_config.temperature,
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
