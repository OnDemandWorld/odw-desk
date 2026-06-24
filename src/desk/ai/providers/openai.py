"""
ODW.ai Desk — OpenAI Provider

Frontier model provider for OpenAI API.
"""

from collections.abc import AsyncIterator

import httpx
import structlog

from desk.ai.providers.base import LLMProvider, LLMRequest, LLMResponse

logger = structlog.get_logger()


class OpenAIProvider(LLMProvider):
    """
    OpenAI provider for frontier model inference.

    Uses OpenAI's chat completions API.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-4o-mini)
        """
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"

        logger.info("OpenAI provider initialized", model=model)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self.model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate text using OpenAI API."""
        try:
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
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
            logger.error("OpenAI generation failed", error=str(e), model=self.model)
            raise

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream text generation from OpenAI API."""
        try:
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
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
            logger.error("OpenAI streaming failed", error=str(e), model=self.model)
            raise

    async def health_check(self) -> bool:
        """Check if OpenAI API is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("OpenAI health check failed", error=str(e))
            return False
