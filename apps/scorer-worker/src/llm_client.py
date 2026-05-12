"""Minimax OpenAI-compatible chat completion client."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MODEL = "MiniMax-M2.7"
DEFAULT_TIMEOUT_SECONDS = 30.0


class LLMClientError(Exception):
    """Raised when the LLM provider returns an unusable response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MinimaxConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "MinimaxConfig":
        return cls(
            api_key=os.getenv("MINIMAX_API_KEY", ""),
            base_url=os.getenv("MINIMAX_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            model=os.getenv("MINIMAX_MODEL", DEFAULT_MODEL),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        )


class MinimaxLLMClient:
    """Small sync client for Minimax chat completions."""

    def __init__(self, config: MinimaxConfig | None = None):
        self.config = config or MinimaxConfig.from_env()
        self.model = self.config.model

    def chat_completion(self, messages: list[dict[str, str]]) -> str:
        if not self.config.api_key or self.config.api_key == "change_me":
            raise LLMClientError("missing MINIMAX_API_KEY")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.2,
        }
        response = httpx.post(
            f"{self.config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise LLMClientError(
                f"llm provider returned HTTP {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError("llm response missing choices[0].message.content") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("llm response content is empty")
        return content
