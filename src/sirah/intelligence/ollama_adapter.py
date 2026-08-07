"""Ollama intelligence adapter — local or Ollama Cloud via Ollama server."""

from __future__ import annotations

import json
import logging
from time import monotonic
from typing import Any

from sirah.errors import (
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceUnavailableError,
)
from sirah.types import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
)

__all__ = ["OllamaIntelligence"]

logger = logging.getLogger(__name__)


class OllamaIntelligence:
    """Talk to an Ollama server (local or cloud) for conversational reasoning.

    Falls back to a secondary model if the primary fails with timeout or
    unavailability. Does NOT fall back to a different provider.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "gpt-oss:120b-cloud",
        fallback_model: str | None = "gemma3:4b",
        timeout: float = 30.0,
        health_timeout: float = 5.0,
        temperature: float = 0.7,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._fallback_model = fallback_model
        self._timeout = timeout
        self._health_timeout = health_timeout
        self._temperature = temperature

    @property
    def primary_model(self) -> str:
        return self._model

    @property
    def fallback_model(self) -> str | None:
        return self._fallback_model

    async def health(self) -> bool:
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=self._health_timeout)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(f"{self._base_url}/api/tags") as resp,
            ):
                return resp.status == 200
        except Exception:
            return False

    async def connectivity_check(self) -> dict[str, Any]:
        """Deep connectivity diagnosis: API, models, latency, version."""
        import aiohttp

        result: dict[str, Any] = {
            "url": self._base_url,
            "api_accessible": False,
            "version": None,
            "latency_ms": None,
            "primary_model_found": False,
            "fallback_model_found": False,
            "available_models": [],
            "warnings": [],
        }
        t0 = monotonic()
        try:
            timeout = aiohttp.ClientTimeout(total=self._health_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self._base_url}/api/tags") as resp:
                    result["latency_ms"] = round((monotonic() - t0) * 1000, 1)
                    if resp.status != 200:
                        result["warnings"].append(f"Ollama API HTTP {resp.status}")
                        return result
                    result["api_accessible"] = True
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    result["available_models"] = models
                    result["primary_model_found"] = self._model in models
                    if self._fallback_model:
                        result["fallback_model_found"] = self._fallback_model in models
                try:
                    async with session.get(f"{self._base_url}/api/version") as vresp:
                        if vresp.status == 200:
                            vdata = await vresp.json()
                            result["version"] = vdata.get("version")
                except Exception:
                    pass
        except TimeoutError:
            result["warnings"].append(f"timeout after {self._health_timeout}s")
        except aiohttp.ClientError as exc:
            result["warnings"].append(f"connection error: {exc}")
        except Exception as exc:
            result["warnings"].append(f"unexpected: {exc}")
        return result

    def format_diagnosis(self, diagnosis: dict[str, Any]) -> str:
        lines = []
        if diagnosis["api_accessible"]:
            lines.append(f"Ollama API accesible: {diagnosis['url']}")
            if diagnosis["version"]:
                lines.append(f"  version: {diagnosis['version']}")
            if diagnosis["latency_ms"] is not None:
                lines.append(f"  latencia: {diagnosis['latency_ms']}ms")
            status = "OK" if diagnosis["primary_model_found"] else "FALTA"
            lines.append(f"  modelo principal ({self._model}): {status}")
            if self._fallback_model:
                fb = "OK" if diagnosis["fallback_model_found"] else "FALTA"
                lines.append(f"  modelo fallback ({self._fallback_model}): {fb}")
            if not diagnosis["primary_model_found"] and diagnosis["available_models"]:
                lines.append(f"  modelos disponibles: {', '.join(diagnosis['available_models'])}")
        else:
            lines.append(f"Ollama API NO accesible: {diagnosis['url']}")
        for w in diagnosis["warnings"]:
            lines.append(f"  ! {w}")
        return "\n".join(lines)

    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        system_content = request.system_prompt_override or _DEFAULT_SYSTEM_PROMPT
        try:
            return await self._call_with_model(self._model, system_content, request)
        except (IntelligenceTimeoutError, IntelligenceUnavailableError) as exc:
            if self._fallback_model and self._fallback_model != self._model:
                logger.warning(
                    "Ollama principal (%s) fallo (%s), reintentando con fallback %s",
                    self._model,
                    type(exc).__name__,
                    self._fallback_model,
                )
                try:
                    return await self._call_with_model(
                        self._fallback_model, system_content, request
                    )
                except (IntelligenceTimeoutError, IntelligenceUnavailableError):
                    logger.error(
                        "Ollama fallback (%s) tambien fallo", self._fallback_model
                    )
                    raise
            raise

    async def _call_with_model(
        self,
        model: str,
        system_content: str,
        request: IntelligenceRequest,
    ) -> IntelligenceResponse:
        import aiohttp

        t0 = monotonic()
        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": request.temperature or self._temperature},
            "format": "json",
        }

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(f"{self._base_url}/api/chat", json=payload) as resp,
            ):
                if resp.status == 429:
                    raise IntelligenceRateLimitError(
                        f"Ollama rate limited (model={model})"
                    )
                if resp.status >= 500:
                    raise IntelligenceUnavailableError(
                        f"Ollama server error {resp.status} (model={model})"
                    )
                if resp.status != 200:
                    raise IntelligenceUnavailableError(
                        f"Ollama HTTP {resp.status} (model={model})"
                    )
                data = await resp.json()
                content = data["message"]["content"]
        except TimeoutError as exc:
            raise IntelligenceTimeoutError(
                f"Ollama timed out after {self._timeout}s (model={model})"
            ) from exc
        except aiohttp.ClientError as exc:
            raise IntelligenceUnavailableError(
                f"Ollama connection error (model={model}): {exc}"
            ) from exc
        except (KeyError, TypeError, IndexError) as exc:
            if isinstance(exc, KeyError) and "message" in str(exc):
                raise IntelligenceUnavailableError(
                    f"Ollama malformed response (model={model}): {exc}"
                ) from exc
            raise IntelligenceUnavailableError(
                f"Ollama malformed response (model={model}): {exc}"
            ) from exc

        latency = (monotonic() - t0) * 1000
        decision = self._parse(content)
        return IntelligenceResponse(
            raw_text=content,
            decision=decision,
            latency_ms=latency,
            model=model,
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
        except (json.JSONDecodeError, KeyError, TypeError):
            return IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response=raw.strip()[:500],
                confidence=0.6,
            )


_DEFAULT_SYSTEM_PROMPT = (
    "Eres SIRAH, un robot social con ojos con servos, camara, microfono y altavoz. "
    "Responde en español, de forma natural y calida. "
    "Responde SOLO en JSON: "
    '{"text_response": "...", "capability_name": null, "capability_params": {}}'
)
