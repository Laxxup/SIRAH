"""Groq Intelligence adapter — Llama 3.3 70B via Groq API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
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
    IntelligenceRateLimitError,
    InvalidIntelligenceResponseError,
)

__all__ = ["GroqIntelligence"]

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """Eres SIRAH, un asistente robótico amable y conversacional.
Hablas español de forma natural y cálida.

Responde SIEMPRE en formato JSON exactamente así:
{
  "text_response": "tu respuesta natural aquí",
  "capability_name": null,
  "capability_params": {}
}

Si el usuario pide una acción física, usa capability_name con uno de:
- "robot.greet" (saludar, parámetros: {"style": "wave"|"bow"|"nod"})
- "robot.stop" (detenerse)
- "robot.home" (posición inicial)

Mantén respuestas cortas (<100 palabras). Sé cálido pero conciso."""


class GroqIntelligence:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 15.0,
        max_retries: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 256,
        system_prompt: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def health(self) -> bool:
        return bool(self._api_key)

    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        if not self._api_key:
            raise IntelligenceUnavailableError("GROQ_API_KEY not set")

        t0 = monotonic()
        payload = self._build_payload(request)

        for attempt in range(self._max_retries):
            try:
                result = await self._call_api(payload)
                latency = (monotonic() - t0) * 1000
                decision = self._parse_decision(result)
                return IntelligenceResponse(
                    raw_text=result,
                    decision=decision,
                    latency_ms=latency,
                    model=self._model,
                )
            except (IntelligenceTimeoutError, IntelligenceRateLimitError) as exc:
                if attempt == self._max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning("Groq attempt %d failed: %s, retrying in %ds", attempt + 1, exc, wait)
                await asyncio.sleep(wait)
            except IntelligenceUnavailableError:
                raise

        raise IntelligenceUnavailableError("all retries exhausted")

    def _build_payload(self, request: IntelligenceRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt}
        ]
        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        return {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature or self._temperature,
            "max_tokens": request.max_tokens or self._max_tokens,
            "response_format": {"type": "json_object"},
        }

    async def _call_api(self, payload: dict[str, Any]) -> str:
        import aiohttp

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=self._timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self._base_url, json=payload, headers=headers
                ) as resp:
                    if resp.status == 429:
                        raise IntelligenceRateLimitError("Groq rate limit")
                    if resp.status == 401:
                        raise IntelligenceUnavailableError("invalid API key")
                    if resp.status >= 500:
                        raise IntelligenceUnavailableError(f"Groq server error {resp.status}")
                    if resp.status != 200:
                        body = await resp.text()
                        raise IntelligenceUnavailableError(f"Groq HTTP {resp.status}: {body}")

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return content
        except asyncio.TimeoutError:
            raise IntelligenceTimeoutError(f"Groq timed out after {self._timeout}s")
        except aiohttp.ClientError as exc:
            raise IntelligenceUnavailableError(f"Groq connection error: {exc}")

    def _parse_decision(self, raw: str) -> IntelligenceDecision:
        try:
            data = json.loads(raw)
            return IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response=data.get("text_response", ""),
                capability_name=data.get("capability_name"),
                capability_params=data.get("capability_params", {}),
                confidence=0.95,
                reasoning="groq-structured-output",
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Groq parse failure: %s, raw=%s", exc, raw[:200])
            return IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response=raw.strip()[:500],
                confidence=0.6,
                reasoning="raw-fallback",
            )
