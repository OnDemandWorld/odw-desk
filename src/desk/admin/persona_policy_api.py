"""
ODW.ai Desk — Persona & Policy Admin APIs (PERSONA-002, POLICY-002)

Admin UI endpoints for brand persona and response policy management.
"""

from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from desk.dependencies import get_db
from desk.models.agent import Agent
from desk.models.brand_persona import BrandPersona
from desk.persona.service import PersonaService
from desk.policy.engine import PolicyEngine

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Persona & Policy"])


# ============================================================================
# Brand Persona APIs (PERSONA-002)
# ============================================================================


class CreatePersonaRequest(BaseModel):
    """FR-BP-01: operator-defined brand persona. Previously personas could be
    listed/activated but never created — the table was unreachable."""

    name: str = Field(min_length=1, max_length=255)
    tone: str = Field(min_length=1, max_length=100)
    formality_level: str = Field(default="neutral", pattern="^(casual|neutral|formal)$")
    vocabulary_notes: str | None = None
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    emoji_policy: str = Field(default="moderate", pattern="^(none|minimal|moderate|liberal)$")
    signature_phrases: list[str] | None = None
    few_shot_examples: list[dict[str, Any]] | None = None
    deployment_id: UUID | None = None


@router.post("/personas", status_code=201)
async def create_persona(
    body: CreatePersonaRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    persona = BrandPersona(
        deployment_id=body.deployment_id or uuid4(),
        name=body.name,
        tone=body.tone,
        formality_level=body.formality_level,
        vocabulary_notes=body.vocabulary_notes,
        dos=body.dos,
        donts=body.donts,
        emoji_policy=body.emoji_policy,
        signature_phrases=body.signature_phrases,
        few_shot_examples=body.few_shot_examples,
        is_active=False,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    logger.info("Brand persona created", persona_id=str(persona.id), name=persona.name)
    return {
        "id": str(persona.id),
        "name": persona.name,
        "tone": persona.tone,
        "is_active": persona.is_active,
    }


# ============================================================================
# Agent APIs — creation (D-2): the operator console takeover flow requires an
# Agent row; previously nothing could create one ("no agent seeded" in the
# inbox made human takeover unusable out of the box).
# ============================================================================


class CreateAgentRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=5, max_length=255)
    role: str = Field(default="agent", pattern="^(admin|agent|read_only)$")
    user_id: UUID | None = None
    max_concurrent_conversations: int = Field(default=5, ge=1, le=50)


@router.post("/agents", status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    agent = Agent(
        user_id=body.user_id or uuid4(),
        display_name=body.display_name,
        email=body.email,
        role=body.role,
        max_concurrent_conversations=body.max_concurrent_conversations,
    )
    db.add(agent)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An agent with that email already exists") from exc
    await db.refresh(agent)
    logger.info("Agent created", agent_id=str(agent.id), email=agent.email)
    return {
        "id": str(agent.id),
        "display_name": agent.display_name,
        "email": agent.email,
        "role": agent.role,
    }


@router.get("/agents")
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """List human agents (id/email/name — used by the console takeover UI)."""
    from sqlalchemy import select

    result = await db.execute(select(Agent).order_by(Agent.created_at.desc()).limit(200))
    return [
        {
            "id": str(a.id),
            "display_name": a.display_name,
            "email": a.email,
            "role": a.role,
            "is_online": a.is_online,
        }
        for a in result.scalars().all()
    ]


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
