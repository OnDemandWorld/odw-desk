"""
ODW.ai Desk — Persona & Policy Admin APIs (PERSONA-002, POLICY-002)

Admin UI endpoints for brand persona and response policy management.
"""

from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from desk.dependencies import get_db
from desk.persona.service import PersonaService
from desk.policy.engine import PolicyEngine

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Persona & Policy"])


# ============================================================================
# Brand Persona APIs (PERSONA-002)
# ============================================================================


@router.get("/personas")
async def list_personas(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """List all brand personas."""
    service = PersonaService(db)
    return await service.list_personas()


@router.get("/personas/active")
async def get_active_persona(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Get the currently active brand persona."""
    service = PersonaService(db)
    persona = await service.get_active_persona()

    if not persona:
        return {"active": False, "persona": None}

    return {
        "active": True,
        "persona": {
            "id": str(persona.id),
            "name": persona.name,
            "version": persona.version,
            "tone": persona.tone,
            "formality_level": persona.formality_level,
            "vocabulary_notes": persona.vocabulary_notes,
            "dos": persona.dos,
            "donts": persona.donts,
            "signature_phrases": persona.signature_phrases,
            "few_shot_examples": persona.few_shot_examples,
            "persona_backend": persona.persona_backend,
            "adapter_uri": persona.adapter_uri,
            "adapter_version": persona.adapter_version,
        },
    }


@router.post("/personas/{persona_id}/activate")
async def activate_persona(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activate a brand persona."""
    service = PersonaService(db)
    await service.activate_persona(persona_id)
    return {"success": True, "message": "Persona activated"}


@router.get("/personas/{persona_id}/preview")
async def preview_persona_prompt(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Preview the composed system prompt for a persona."""
    service = PersonaService(db)
    persona = await service.get_persona_by_id(persona_id)

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    system_prompt = await service.compose_system_prompt(persona)

    return {
        "persona_id": str(persona_id),
        "persona_name": persona.name,
        "system_prompt": system_prompt,
        "prompt_length": len(system_prompt),
    }


# ============================================================================
# Response Policy APIs (POLICY-002)
# ============================================================================


@router.get("/policies")
async def list_policies(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """List all response policies."""
    engine = PolicyEngine(db)
    return await engine.list_policies()


class PolicyCreateRequest(BaseModel):
    """Request body for creating a response policy."""

    name: str = Field(..., description="Policy name")
    trigger_type: Literal["keyword", "classifier", "llm_intent"] = Field(
        ..., description="How the trigger is evaluated"
    )
    action: Literal[
        "template", "redirect", "inject_context", "append_disclaimer", "block", "escalate"
    ] = Field(..., description="Action taken when the trigger matches")
    trigger_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Trigger configuration: keywords, patterns, topics, metadata",
    )
    action_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific payload: redirect_message, severity, ...",
    )
    applies_to: Literal["pre", "post", "both"] = Field("pre", description="Pipeline phase")
    priority: int = Field(100, description="Evaluation order (lower = higher priority)")
    description: str | None = Field(None, description="Policy description")
    restricted_topics: list[str] | None = Field(None, description="Restricted topic labels")


@router.post("/policies")
async def create_policy(
    request: PolicyCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new response policy."""
    engine = PolicyEngine(db)

    try:
        policy = await engine.create_policy(
            name=request.name,
            trigger_type=request.trigger_type,
            action=request.action,
            trigger_config=request.trigger_config,
            action_payload=request.action_payload,
            applies_to=request.applies_to,
            priority=request.priority,
            description=request.description,
            restricted_topics=request.restricted_topics,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "policy_id": str(policy.id),
        "message": "Policy created",
    }


@router.post("/policies/{policy_id}/activate")
async def activate_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activate a response policy."""
    engine = PolicyEngine(db)
    policy = await engine.set_policy_active(policy_id, True)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"success": True, "message": "Policy activated"}


@router.post("/policies/{policy_id}/deactivate")
async def deactivate_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deactivate a response policy."""
    engine = PolicyEngine(db)
    policy = await engine.set_policy_active(policy_id, False)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"success": True, "message": "Policy deactivated"}


@router.post("/policies/test")
async def test_policy(
    phase: str = Query(..., description="Pipeline phase to test: pre or post"),
    content: str = Query(..., description="Content to test against policies"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Test content against active policies."""
    engine = PolicyEngine(db)

    if phase == "pre":
        result = await engine.run_pre_generation_hooks(content)
    elif phase == "post":
        result = await engine.run_post_generation_hooks(content, content)
    else:
        raise HTTPException(status_code=400, detail="Invalid phase; use 'pre' or 'post'")

    return {
        "phase": phase,
        "content": content,
        "result": result,
    }
