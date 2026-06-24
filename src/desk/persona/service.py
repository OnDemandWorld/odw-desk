"""
ODW.ai Desk — Persona Service (PERSONA-003, PERSONA-005)

Brand persona prompt composition and injection into inference path.
"""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.models.brand_persona import BrandPersona

logger = structlog.get_logger()


class PersonaService:
    """
    Persona Service for brand voice management and prompt composition.

    Handles persona retrieval, prompt composition, and injection into AI inference.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_persona(self) -> BrandPersona | None:
        """Get the currently active brand persona."""
        query = select(BrandPersona).where(BrandPersona.is_active == True).limit(1)  # noqa: E712
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_persona_by_id(self, persona_id: UUID) -> BrandPersona | None:
        """Get a specific persona by ID."""
        query = select(BrandPersona).where(BrandPersona.id == persona_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def compose_system_prompt(
        self,
        persona: BrandPersona | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Compose system prompt with brand persona injected.

        Args:
            persona: Brand persona to use (if None, uses active persona)
            context: Additional context for prompt composition

        Returns:
            Composed system prompt
        """
        if not persona:
            persona = await self.get_active_persona()

        # Base system prompt
        base_prompt = """You are a helpful customer support agent.
You provide accurate, friendly, and professional assistance to customers.
Base your responses on the provided knowledge base when available.
If you're unsure about something, be honest and offer to escalate to a human agent.
Keep responses concise and focused on resolving the customer's issue."""

        if not persona:
            return base_prompt

        # Inject persona attributes
        prompt_parts = [base_prompt]

        # Add brand voice
        if persona.voice_description:
            prompt_parts.append(f"\n\nBrand Voice: {persona.voice_description}")

        # Add tone
        if persona.tone:
            prompt_parts.append(f"Tone: {persona.tone}")

        # Add formality level
        if persona.formality_level:
            formality_map = {
                "casual": "Use casual, conversational language.",
                "professional": "Use professional, courteous language.",
                "formal": "Use formal, polished language.",
            }
            prompt_parts.append(formality_map.get(persona.formality_level, ""))

        # Add do's and don'ts
        if persona.dos_and_donts:
            dos = persona.dos_and_donts.get("do", [])
            donts = persona.dos_and_donts.get("dont", [])

            if dos:
                prompt_parts.append("\n\nDo:")
                for do_item in dos:
                    prompt_parts.append(f"- {do_item}")

            if donts:
                prompt_parts.append("\n\nDon't:")
                for dont_item in donts:
                    prompt_parts.append(f"- {dont_item}")

        # Add vocabulary guidelines
        if persona.vocabulary_guidelines:
            prompt_parts.append(f"\n\nVocabulary: {persona.vocabulary_guidelines}")

        # Add example phrases
        if persona.example_phrases:
            prompt_parts.append("\n\nExample phrases:")
            for phrase in persona.example_phrases[:3]:  # Limit to 3 examples
                prompt_parts.append(f'- "{phrase}"')

        return "\n".join(prompt_parts)

    async def get_persona_for_inference(
        self,
        conversation_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Get persona configuration for AI inference.

        Args:
            conversation_metadata: Conversation metadata for persona selection

        Returns:
            Persona configuration dict with prompt, backend, and adapter info
        """
        persona = await self.get_active_persona()

        if not persona:
            return {
                "has_persona": False,
                "system_prompt": None,
                "persona_backend": None,
            }

        # Compose system prompt
        system_prompt = await self.compose_system_prompt(persona)

        # Determine persona backend
        persona_backend = persona.persona_backend or "prompt"

        result = {
            "has_persona": True,
            "persona_id": str(persona.id),
            "persona_name": persona.name,
            "system_prompt": system_prompt,
            "persona_backend": persona_backend,
        }

        # Add LoRA adapter info if using adapter backend
        if persona_backend == "lora_adapter" and persona.lora_adapter_uri:
            result["lora_adapter_uri"] = persona.lora_adapter_uri
            result["lora_adapter_version"] = persona.lora_adapter_version

        return result

    async def list_personas(self) -> list[dict[str, Any]]:
        """List all brand personas."""
        query = select(BrandPersona).order_by(BrandPersona.created_at.desc())
        result = await self.db.execute(query)
        personas = result.scalars().all()

        return [
            {
                "id": str(persona.id),
                "name": persona.name,
                "version": persona.version,
                "is_active": persona.is_active,
                "tone": persona.tone,
                "formality_level": persona.formality_level,
                "persona_backend": persona.persona_backend,
                "created_at": persona.created_at.isoformat() if persona.created_at else None,
                "updated_at": persona.updated_at.isoformat() if persona.updated_at else None,
            }
            for persona in personas
        ]

    async def activate_persona(self, persona_id: UUID) -> None:
        """Activate a persona (deactivate all others)."""
        # Deactivate all personas
        query = select(BrandPersona)
        result = await self.db.execute(query)
        all_personas = result.scalars().all()

        for persona in all_personas:
            persona.is_active = False

        # Activate the specified persona
        persona = await self.get_persona_by_id(persona_id)
        if persona:
            persona.is_active = True
            await self.db.commit()
            logger.info("Persona activated", persona_id=str(persona_id), name=persona.name)
