"""
ODW.ai Desk — LLM Providers

Provider implementations for local and frontier models.
"""

from desk.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from desk.ai.providers.ollama import OllamaProvider
from desk.ai.providers.openai import OpenAIProvider

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "OllamaProvider",
    "OpenAIProvider",
]
