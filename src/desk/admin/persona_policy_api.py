"""
ODW.ai Desk — Persona & Policy Admin APIs (PERSONA-002, POLICY-002)

Admin UI endpoints for brand persona and response policy management.
"""

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
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
            "voice_description": persona.voice_description,
            "dos_and_donts": persona.dos_and_donts,
            "vocabulary_guidelines": persona.vocabulary_guidelines,
            "example_phrases": persona.example_phrases,
            "persona_backend": persona.persona_backend,
            "lora_adapter_uri": persona.lora_adapter_uri,
            "lora_adapter_version": persona.lora_adapter_version,
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


@router.post("/policies")
async def create_policy(
    name: str = Query(..., description="Policy name"),
    hook_type: str = Query(..., description="Hook type: pre_generation or post_generation"),
    rule_type: str = Query(..., description="Rule type: keyword, regex, topic, custom"),
    action_type: str = Query(..., description="Action type: allow, block, redirect, flag"),
    priority: int = Query(0, description="Policy priority (higher = evaluated first)"),
    description: str = Query(None, description="Policy description"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new response policy."""
    engine = PolicyEngine(db)
    # For MVP, use simple conditions
    conditions = {"keywords": []}
    action_config = {}

    policy = await engine.create_policy(
        name=name,
        hook_type=hook_type,
        rule_type=rule_type,
        action_type=action_type,
        conditions=conditions,
        action_config=action_config,
        priority=priority,
        description=description,
    )

    return {
        "success": True,
        "policy_id": str(policy.id),
        "message": "Policy created",
    }


@router.post("/policies/test")
async def test_policy(
    hook_type: str = Query(..., description="Hook type to test"),
    content: str = Query(..., description="Content to test against policies"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Test content against active policies."""
    engine = PolicyEngine(db)

    if hook_type == "pre_generation":
        result = await engine.run_pre_generation_hooks(content)
    elif hook_type == "post_generation":
        result = await engine.run_post_generation_hooks(content, content)
    else:
        raise HTTPException(status_code=400, detail="Invalid hook_type")

    return {
        "hook_type": hook_type,
        "content": content,
        "result": result,
    }
