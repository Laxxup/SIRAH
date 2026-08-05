"""Ollama local intelligence adapter — fallback when offline."""

from __future__ import annotations

import asyncio
import json
import logging
from time import monotonic
from typing import Any

from sirah.intelligence.port import IntelligencePort
from sirah.types import (
    IntelligenceRequest,
    IntelligenceResponse,
    IntelligenceDecision,
    DecisionType,
)
from sirah.errors import (
    IntelligenceUnavailableError,
    IntelligenceTimeoutError,
    InvalidIntelligenceResponseError,
)

__all__ = ["OllamaIntelligence"]

logger = logging.getLogger(__name__)


class OllamaIntelligence:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        timeout: float = 30.0,
        temperature: float = 0.7,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._temperature = temperature

    async def health(self) -> bool:
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self._base_url}/api/tags") as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        t0 = monotonic()
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "Eres SIRAH, asistente robótico. Responde en español, "
                    "de forma natural y cálida. Responde SOLO en JSON con "
                    '{"text_response": "...", "capability_name": null, "capability_params": {}}'
                ),
            }
        ]
        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature or self._temperature,
            },
            "format": "json",
        }

        import aiohttp

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self._base_url}/api/chat", json=payload
                ) as resp:
                    if resp.status != 200:
                        raise IntelligenceUnavailableError(f"Ollama HTTP {resp.status}")
                    data = await resp.json()
                    content = data["message"]["content"]
        except asyncio.TimeoutError:
            raise IntelligenceTimeoutError(f"Ollama timed out after {self._timeout}s")
        except aiohttp.ClientError as exc:
            raise IntelligenceUnavailableError(f"Ollama error: {exc}")

        latency = (monotonic() - t0) * 1000
        decision = self._parse(content)
        return IntelligenceResponse(
            raw_text=content, decision=decision, latency_ms=latency, model=self._model
        )

    def _parse(self, raw: str) -> IntelligenceDecision:
        try:
            data = json.loads(raw)
            return IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response=data.get("text_response", raw.strip()),
                capability_name=data.get("capability_name"),
                capability_params=data.get("capability_params", {}),
                confidence=0.95,
            )
        except (json.JSONDecodeError, KeyError):
            return IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response=raw.strip()[:500],
                confidence=0.6,
            )
