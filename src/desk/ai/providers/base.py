"""
ODW.ai Desk — LLM Provider Abstraction (AI-004)

Abstract base class for LLM providers with implementations for local (Ollama/vLLM)
and frontier (OpenAI/Anthropic) models.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class LLMRequest:
    """Request to an LLM provider."""

    prompt: str
    system_prompt: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.95
    stream: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "prompt": self.prompt,
            "system_prompt": self.system_prompt,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": self.stream,
        }


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    text: str
    model: str
    provider: str
    tokens_used: int
    finish_reason: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "tokens_used": self.tokens_used,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata or {},
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate text from a prompt.

        Args:
            request: LLM request with prompt and parameters

        Returns:
            LLM response with generated text and metadata
        """
        pass

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream text generation (if supported).

        Args:
            request: LLM request with prompt and parameters

        Yields:
            Text chunks as they are generated
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is reachable."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider name."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return model name."""
        pass
