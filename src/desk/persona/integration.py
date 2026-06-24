"""
ODW.ai Desk — Persona Integration (PERSONA-004, PERSONA-005)

Integration of persona service into AI inference path.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from desk.ai.prompt_builder import PromptBuilder
from desk.persona.service import PersonaService

logger = structlog.get_logger()


class PersonaIntegratedPromptBuilder(PromptBuilder):
    """
    Enhanced Prompt Builder with persona integration.

    Extends base PromptBuilder to inject brand persona into system prompts.
    """

    def __init__(
        self,
        db: AsyncSession,
        system_prompt: str | None = None,
        max_context_messages: int = 10,
        max_knowledge_chars: int = 2000,
    ):
        super().__init__(system_prompt, max_context_messages, max_knowledge_chars)
        self.db = db
        self.persona_service = PersonaService(db)

    async def build_prompt_with_persona(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        knowledge_context: list[dict[str, Any]] | None = None,
        conversation_metadata: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """
        Build prompt with persona-injected system prompt.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # Get persona configuration
        persona_config = await self.persona_service.get_persona_for_inference(conversation_metadata)

        # Get system prompt (with persona if available)
        if persona_config.get("has_persona"):
            system_prompt = persona_config["system_prompt"]
            logger.info(
                "Using brand persona",
                persona_id=persona_config.get("persona_id"),
                persona_name=persona_config.get("persona_name"),
            )
        else:
            system_prompt = self.get_system_prompt()

        # Build user prompt
        user_prompt = self.build_prompt(
            user_message=user_message,
            conversation_history=conversation_history,
            knowledge_context=knowledge_context,
            metadata=conversation_metadata,
        )

        return system_prompt, user_prompt


async def get_prompt_builder_with_persona(db: AsyncSession) -> PersonaIntegratedPromptBuilder:
    """Factory function to get a persona-integrated prompt builder."""
    return PersonaIntegratedPromptBuilder(db)
