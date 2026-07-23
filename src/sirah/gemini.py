"""Adaptador opcional de texto estructurado para Google Gemini."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

from .errors import (
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceUnavailableError,
    InvalidIntelligenceResponseError,
)
from .intelligence import (
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
    build_system_prompt,
)

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


@dataclass(slots=True)
class GeminiMetrics:
    requests: int = 0
    successes: int = 0
    errors: int = 0
    rate_limits: int = 0
    elapsed_seconds: float = 0.0
    model: str = DEFAULT_GEMINI_MODEL


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise IntelligenceUnavailableError(
            "Falta GEMINI_API_KEY o GOOGLE_API_KEY."
        )
    return key


def _load_dependencies() -> tuple[Any, Any, Any, Any]:
    try:
        from google import genai
        from google.genai import errors, types
        from pydantic import ConfigDict, Field, create_model
    except ImportError as error:
        raise IntelligenceUnavailableError(
            'Gemini requiere instalar el extra: pip install "sirah[gemini]".'
        ) from error
    return genai, errors, types, (create_model, ConfigDict, Field)


class GeminiIntelligenceAdapter:
    """Propone decisiones; nunca conoce RobotPort ni crea RobotCommand."""

    def __init__(
        self,
        *,
        model: str | None = None,
        max_retries: int = 2,
        base_backoff_seconds: float = 0.25,
        max_response_characters: int = 1_000,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if max_retries < 0 or max_retries > 5:
            raise ValueError("max_retries debe estar entre 0 y 5.")
        self.model = model or os.environ.get(
            "SIRAH_GEMINI_MODEL", DEFAULT_GEMINI_MODEL
        )
        self._max_retries = max_retries
        self._base_backoff = base_backoff_seconds
        self._max_response_characters = max_response_characters
        self._sleep = sleep
        self._jitter = jitter
        self._client = client
        self.metrics = GeminiMetrics(model=self.model)

    def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        genai, errors, types, pydantic = _load_dependencies()
        client = self._client or genai.Client(api_key=_api_key())
        schema_model = self._schema_model(pydantic)
        schema = self._json_schema(request, schema_model)
        started = time.monotonic()
        self.metrics.requests += 1
        try:
            for attempt in range(self._max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model=self.model,
                        contents=build_system_prompt(request),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_json_schema=schema,
                        ),
                    )
                    text = getattr(response, "text", None)
                    if not text:
                        raise InvalidIntelligenceResponseError(
                            "Gemini devolvió una respuesta vacía o bloqueada."
                        )
                    try:
                        validated = schema_model.model_validate_json(text)
                    except Exception as error:
                        raise InvalidIntelligenceResponseError(
                            "Gemini devolvió JSON o esquema inválido."
                        ) from error
                    decision = IntelligenceDecision.from_mapping(
                        validated.model_dump()
                    )
                    decision.validate(
                        max_response_characters=self._max_response_characters
                    )
                    self.metrics.successes += 1
                    return IntelligenceResponse(decision, "google-gemini", self.model)
                except InvalidIntelligenceResponseError:
                    raise
                except TimeoutError as error:
                    if attempt == self._max_retries:
                        raise IntelligenceTimeoutError(
                            "Gemini excedió el tiempo permitido."
                        ) from error
                    self._backoff(attempt)
                except errors.APIError as error:
                    mapped, recoverable = self._map_api_error(error)
                    if not recoverable or attempt == self._max_retries:
                        raise mapped from error
                    self._backoff(attempt)
            raise AssertionError("Bucle de reintentos incoherente.")
        except IntelligenceRateLimitError:
            self.metrics.rate_limits += 1
            self.metrics.errors += 1
            raise
        except (
            IntelligenceTimeoutError,
            IntelligenceUnavailableError,
            InvalidIntelligenceResponseError,
        ):
            self.metrics.errors += 1
            raise
        finally:
            self.metrics.elapsed_seconds += time.monotonic() - started

    def _backoff(self, attempt: int) -> None:
        delay = min(self._base_backoff * (2**attempt), 2.0)
        self._sleep(delay + min(self._jitter(), 1.0) * delay * 0.1)

    @staticmethod
    def _map_api_error(error: Any) -> tuple[Exception, bool]:
        code = getattr(error, "code", 0)
        if code == 429:
            return (
                IntelligenceRateLimitError(
                    "Gemini rechazó la solicitud por cuota o frecuencia."
                ),
                True,
            )
        if code >= 500:
            return (
                IntelligenceUnavailableError(
                    "Gemini no está disponible temporalmente."
                ),
                True,
            )
        if code == 404:
            return (
                IntelligenceUnavailableError(
                    "El modelo Gemini configurado no está disponible."
                ),
                False,
            )
        return (
            IntelligenceUnavailableError("Gemini rechazó la solicitud."),
            False,
        )

    @staticmethod
    def _schema_model(pydantic: Any) -> type[Any]:
        create_model, config_dict, field = pydantic
        return create_model(
            "GeminiDecisionSchema",
            __config__=config_dict(extra="forbid", strict=True),
            decision_type=(
                str,
                field(description="Tipo de decisión permitido."),
            ),
            response_text=(
                str,
                field(min_length=1, description="Respuesta conversacional."),
            ),
            capability=(
                str | None,
                field(default=None, description="Capacidad habilitada o null."),
            ),
            parameters=(
                dict[str, str | int | float | bool],
                field(
                    default_factory=dict,
                    description="Parámetros de alto nivel.",
                ),
            ),
            reason_code=(str | None, field(default=None)),
        )

    @staticmethod
    def _json_schema(request: IntelligenceRequest, model: type[Any]) -> dict[str, Any]:
        schema = model.model_json_schema()
        schema["additionalProperties"] = False
        schema["properties"]["decision_type"]["enum"] = [
            "respond_only",
            "request_capability",
            "clarify",
            "reject",
        ]
        names = [item["name"] for item in request.capabilities]
        schema["properties"]["capability"] = {
            "anyOf": [
                {"type": "string", "enum": names},
                {"type": "null"},
            ],
            "description": "Solo una capacidad habilitada o null.",
        }
        return schema
