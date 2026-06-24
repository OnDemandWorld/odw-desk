"""
ODW.ai Desk — Prompt Builder (AI-006)

Constructs system prompts and user prompts with conversation context
and retrieved knowledge for LLM inference.
"""

from typing import Any

import structlog

logger = structlog.get_logger()


class PromptBuilder:
    """
    Prompt builder for constructing LLM prompts.

    Combines system instructions, conversation context, retrieved knowledge,
    and user messages into well-structured prompts.
    """

    DEFAULT_SYSTEM_PROMPT = """You are a helpful customer support agent for ODW.ai Desk.
You provide accurate, friendly, and professional assistance to customers.
Base your responses on the provided knowledge base when available.
If you're unsure about something, be honest and offer to escalate to a human agent.
Keep responses concise and focused on resolving the customer's issue."""

    def __init__(
        self,
        system_prompt: str | None = None,
        max_context_messages: int = 10,
        max_knowledge_chars: int = 2000,
    ):
        """
        Initialize Prompt Builder.

        Args:
            system_prompt: Custom system prompt (defaults to DEFAULT_SYSTEM_PROMPT)
            max_context_messages: Maximum number of context messages to include
            max_knowledge_chars: Maximum characters for knowledge base content
        """
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.max_context_messages = max_context_messages
        self.max_knowledge_chars = max_knowledge_chars

    def build_prompt(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        knowledge_context: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a complete prompt for LLM inference.

        Args:
            user_message: Current user message
            conversation_history: List of previous messages [{role, content}]
            knowledge_context: Retrieved knowledge documents
            metadata: Additional metadata for prompt customization

        Returns:
            Formatted prompt string
        """
        prompt_parts = []

        # Add knowledge context if available
        if knowledge_context:
            knowledge_text = self._format_knowledge(knowledge_context)
            if knowledge_text:
                prompt_parts.append(f"Relevant information:\n{knowledge_text}\n")

        # Add conversation history
        if conversation_history:
            history_text = self._format_history(conversation_history)
            if history_text:
                prompt_parts.append(f"Conversation history:\n{history_text}\n")

        # Add current message
        prompt_parts.append(f"Customer: {user_message}\n")
        prompt_parts.append("Agent:")

        return "\n".join(prompt_parts)

    def get_system_prompt(self) -> str:
        """Get the system prompt."""
        return self.system_prompt

    def _format_knowledge(self, knowledge_context: list[dict[str, Any]]) -> str:
        """Format knowledge base documents for prompt inclusion."""
        if not knowledge_context:
            return ""

        formatted_parts = []
        total_chars = 0

        for i, doc in enumerate(knowledge_context, 1):
            content = doc.get("content", "")
            if not content:
                continue

            # Truncate if needed
            if total_chars + len(content) > self.max_knowledge_chars:
                remaining_chars = self.max_knowledge_chars - total_chars
                if remaining_chars > 100:
                    content = content[:remaining_chars] + "..."
                else:
                    break

            formatted_parts.append(f"[{i}] {content}")
            total_chars += len(content)

        return "\n".join(formatted_parts)

    def _format_history(self, conversation_history: list[dict[str, str]]) -> str:
        """Format conversation history for prompt inclusion."""
        if not conversation_history:
            return ""

        # Limit to max_context_messages
        limited_history = conversation_history[-self.max_context_messages :]

        formatted_parts = []
        for msg in limited_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "customer":
                formatted_parts.append(f"Customer: {content}")
            elif role in ["agent", "ai"]:
                formatted_parts.append(f"Agent: {content}")
            elif role == "system":
                # Skip system messages in history
                continue

        return "\n".join(formatted_parts)
