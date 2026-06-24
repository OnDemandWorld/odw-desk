"""
ODW.ai Desk — Ollama/vLLM Provider

Local model provider for Ollama and vLLM endpoints.
"""

from collections.abc import AsyncIterator

import httpx
import structlog

from desk.ai.providers.base import LLMProvider, LLMRequest, LLMResponse

logger = structlog.get_logger()


class OllamaProvider(LLMProvider):
    """
    Ollama/vLLM provider for local model inference.

    Supports OpenAI-compatible API endpoints.
    """

    def __init__(self, endpoint: str, model: str):
        """
        Initialize Ollama provider.

        Args:
            endpoint: Ollama/vLLM endpoint URL
            model: Model name/identifier
        """
        self.endpoint = endpoint.rstrip("/")
        self.model = model

        logger.info("Ollama provider initialized", endpoint=endpoint, model=model)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self.model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate text using Ollama/vLLM."""
        try:
            # Build messages format (OpenAI-compatible)
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.endpoint}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": request.max_tokens,
                        "temperature": request.temperature,
                        "top_p": request.top_p,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                result = response.json()

            # Parse response
            choice = result["choices"][0]
            return LLMResponse(
                text=choice["message"]["content"],
                model=self.model,
                provider=self.provider_name,
                tokens_used=result.get("usage", {}).get("total_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
                metadata={"response_id": result.get("id")},
            )

        except Exception as e:
            logger.error("Ollama generation failed", error=str(e), model=self.model)
            raise

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream text generation from Ollama/vLLM."""
        try:
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.endpoint}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": request.max_tokens,
                        "temperature": request.temperature,
                        "top_p": request.top_p,
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            import json
                            chunk = json.loads(data)
                            if chunk["choices"][0].get("delta", {}).get("content"):
                                yield chunk["choices"][0]["delta"]["content"]

        except Exception as e:
            logger.error("Ollama streaming failed", error=str(e), model=self.model)
            raise

    async def health_check(self) -> bool:
        """Check if Ollama endpoint is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.endpoint}/v1/models")
                return response.status_code == 200
        except Exception as e:
            logger.error("Ollama health check failed", error=str(e))
            return False
