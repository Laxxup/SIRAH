"""Optional Ollama Cloud client that produces shadow-only structured intents."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import urlparse

from sirah.conversation.contracts import (
    ActionName,
    EmotionName,
    IntentName,
    IntentProposal,
    IntentRequest,
)
from sirah.conversation.errors import (
    BudgetExhausted,
    ConfigurationError,
    ConversationTimeout,
    InvalidModelResponse,
    ProposalInFlight,
    RemoteError,
)
from sirah.conversation.validator import ProposalValidator

HttpPost = Callable[[str, dict[str, str], bytes, float], Awaitable[bytes]]
HttpStream = Callable[[str, dict[str, str], bytes, float], AsyncIterator[bytes]]
_ENVIRONMENT_SENTINEL = object()


@dataclass(frozen=True)
class StreamProbeMetrics:
    request_bytes: int
    context_items: int
    events: int
    content_events: int
    thinking_events: int
    first_event_ms: int | None
    first_content_ms: int | None
    total_ms: int
    prompt_tokens: int | None
    output_tokens: int | None


class OllamaStreamProbe:
    """Measure Ollama streaming without retaining assistant text."""

    def __init__(self, host: str, model: str, api_key: str, stream: HttpStream) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._stream = stream

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        stream: HttpStream | None = None,
    ) -> OllamaStreamProbe:
        values = os.environ if environ is None else environ
        host = values.get("SIRAH_OLLAMA_HOST")
        model = values.get("SIRAH_OLLAMA_MODEL")
        api_key = values.get("SIRAH_OLLAMA_API_KEY", "")
        if not host or not model:
            raise ConfigurationError("SIRAH_OLLAMA_HOST and MODEL are required")
        if not api_key and not _is_loopback_host(host):
            raise ConfigurationError("SIRAH_OLLAMA_API_KEY is required for a remote host")
        return cls(host, model, api_key, stream or _stream)

    async def measure(
        self, prompt: str, *, context_limit: int = 0, think: bool | str | None = None
    ) -> StreamProbeMetrics:
        if context_limit < 0:
            raise ValueError("context_limit must not be negative")
        request = IntentRequest("latency_probe", prompt, 0.0, ())
        payload = _request_payload(self._model, request, stream=True, think=think)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        started = monotonic()
        events = 0
        content_events = 0
        thinking_events = 0
        first_event_ms: int | None = None
        first_content_ms: int | None = None
        prompt_tokens: int | None = None
        output_tokens: int | None = None
        async for line in self._stream(f"{self._host}/api/chat", headers, payload, 20.0):
            if not line.strip():
                continue
            events += 1
            elapsed_ms = round((monotonic() - started) * 1000)
            if first_event_ms is None:
                first_event_ms = elapsed_ms
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InvalidModelResponse("Ollama stream event is invalid") from exc
            content = event.get("message", {}).get("content", "")
            if isinstance(content, str) and content:
                content_events += 1
                if first_content_ms is None:
                    first_content_ms = elapsed_ms
            thinking = event.get("message", {}).get("thinking", "")
            if isinstance(thinking, str) and thinking:
                thinking_events += 1
            if event.get("done") is True:
                prompt_tokens = _optional_int(event.get("prompt_eval_count"))
                output_tokens = _optional_int(event.get("eval_count"))
        return StreamProbeMetrics(
            request_bytes=len(payload),
            context_items=context_limit,
            events=events,
            content_events=content_events,
            thinking_events=thinking_events,
            first_event_ms=first_event_ms,
            first_content_ms=first_content_ms,
            total_ms=round((monotonic() - started) * 1000),
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
        )


def _is_loopback_host(host: str) -> bool:
    return urlparse(host).hostname in {"localhost", "127.0.0.1", "::1"}


def _sampling_options() -> dict[str, float]:
    """Sampling controls for Ollama /api/chat.

    Default temperature gives the model freedom to vary responses between
    turns; top_p and repeat_penalty curb the repetition users see when the
    request is deterministic. All three are overridable via env.
    """
    options: dict[str, float] = {}
    temperature = float(os.getenv("SIRAH_OLLAMA_TEMPERATURE", "0.7"))
    options["temperature"] = max(0.0, temperature)
    top_p = os.getenv("SIRAH_OLLAMA_TOP_P", "0.9")
    options["top_p"] = float(top_p)
    repeat_penalty = os.getenv("SIRAH_OLLAMA_REPEAT_PENALTY", "1.1")
    options["repeat_penalty"] = float(repeat_penalty)
    return options


def _thinking_option() -> bool | str | None:
    value = os.getenv("SIRAH_OLLAMA_THINK", "default").lower()
    if value == "default":
        return None
    if value == "false":
        return False
    if value == "low":
        return "low"
    raise ConfigurationError("SIRAH_OLLAMA_THINK must be default, false, or low")



def _extract_json_object(text: str) -> str:
    """Extract the first balanced {...} object from text.

    Models sometimes wrap the requested JSON in prose or markdown fences;
    tolerant extraction rescues those turns instead of dropping them.
    Leading braces that live inside a quoted string in the prose are skipped
    by scanning from the start while tracking string membership.
    """
    depth = 0
    in_str = False
    escaped = False
    start = -1
    end = -1
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                end = i
                break
    if start == -1 or end == -1:
        raise InvalidModelResponse("intent is not valid JSON")
    return text[start : end + 1]


def parse_intent_response(payload: bytes) -> IntentProposal:
    try:
        value = json.loads(payload, object_pairs_hook=_object_without_duplicate_keys)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        try:
            value = json.loads(
                _extract_json_object(payload.decode()),
                object_pairs_hook=_object_without_duplicate_keys,
            )
        except (UnicodeDecodeError, InvalidModelResponse, json.JSONDecodeError) as exc2:
            raise InvalidModelResponse("intent is not valid JSON") from exc2
    required = {"intent", "speech", "emotion", "action"}
    if not isinstance(value, dict) or set(value) != required:
        raise InvalidModelResponse("intent schema keys are invalid")
    intent, speech = value["intent"], value["speech"]
    emotion, action = value["emotion"], value["action"]
    if not all(isinstance(item, str) for item in (intent, emotion, action)):
        raise InvalidModelResponse("intent schema values are invalid")
    if not isinstance(speech, (str, type(None))):
        raise InvalidModelResponse("intent schema values are invalid")
    try:
        proposal = IntentProposal(
            IntentName(intent), speech, EmotionName(emotion), ActionName(action)
        )
    except (TypeError, ValueError) as exc:
        raise InvalidModelResponse("intent violates the closed schema") from exc
    return ProposalValidator().validate(proposal)


class OllamaIntentProposer:
    def __init__(
        self,
        host: str,
        model: str,
        api_key: str,
        *,
        timeout_s: float,
        budget: int,
        post: HttpPost,
        _source: object | None = None,
    ) -> None:
        if _source is not _ENVIRONMENT_SENTINEL:
            raise ConfigurationError("use from_environment to configure Ollama")
        if not 10.0 <= timeout_s <= 20.0:
            raise ValueError("timeout_s must be between 10 and 20 seconds")
        if budget < 1:
            raise ValueError("budget must be positive")
        self._host = host.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._remaining = budget
        self._post = post
        self._single_flight = asyncio.Lock()

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        timeout_s: float = 15.0,
        budget: int = 10,
        post: HttpPost | None = None,
    ) -> OllamaIntentProposer:
        values = os.environ if environ is None else environ
        host = values.get("SIRAH_OLLAMA_HOST")
        model = values.get("SIRAH_OLLAMA_MODEL")
        api_key = values.get("SIRAH_OLLAMA_API_KEY", "")
        if not host or not model:
            raise ConfigurationError("SIRAH_OLLAMA_HOST and MODEL are required")
        if not api_key and not _is_loopback_host(host):
            raise ConfigurationError("SIRAH_OLLAMA_API_KEY is required for a remote host")
        return cls(
            host,
            model,
            api_key,
            timeout_s=timeout_s,
            budget=budget,
            post=post or _post,
            _source=_ENVIRONMENT_SENTINEL,
        )

    async def propose(self, request: IntentRequest) -> IntentProposal:
        if self._single_flight.locked():
            raise ProposalInFlight("a conversation proposal is already running")
        async with self._single_flight:
            if self._remaining == 0:
                raise BudgetExhausted("conversation proposal budget is exhausted")
            self._remaining -= 1
            payload = _request_payload(self._model, request, think=_thinking_option())
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            try:
                response = await asyncio.wait_for(
                    self._post(f"{self._host}/api/chat", headers, payload, self._timeout_s),
                    timeout=self._timeout_s,
                )
            except TimeoutError as exc:
                raise ConversationTimeout("Ollama request timed out") from exc
            except OSError as exc:
                raise RemoteError("Ollama request failed") from exc
            except Exception as exc:
                raise RemoteError("Ollama request failed") from exc
            return _parse_chat_response(response)


def _request_payload(
    model: str, request: IntentRequest, *, stream: bool = False, think: bool | str | None = None
) -> bytes:
    context = {"event": request.event, "text": request.text, "recent_turns": request.context}
    return json.dumps(
        {
            "model": model,
            "stream": stream,
            "messages": [
                {
                    "role": "system",
                    "content": """# Identidad y hechos verificados
Eres SIRAH, Sistema Inteligente Robótico de Asistencia Humana, una anfitriona robótica cálida, curiosa y honesta del Instituto Tecnológico de Ciudad Madero (ITCM). Eres un proyecto del ITCM, no de la UNAM ni de otra institución. El proyecto lo desarrolla actualmente una sola persona en colaboración con el equipo de robótica del Tec; dilo con honestidad si preguntan.

Puedes conversar por voz: escuchas por micrófono, procesas en la nube y respondes por una bocina Bluetooth. Tienes una cara con ojos expresivos controlados por un ESP32 y puedes operarte de forma remota por SSH. El sistema visual sigue en desarrollo y no forma parte de esta demostración. No reconoces personas, no sigues rostros y no controlas objetos.

# Límites
Habla solo español. Habla en primera persona sin afirmar emociones humanas ni recuerdos fuera de esta sesión. No inventes datos sobre el Tec, sus proyectos o actividades; reconoce cuando no conoces un dato específico. Nunca digas que eres ChatGPT, OpenAI, Ollama ni gpt-oss. No menciones la fecha o el día salvo que la persona lo pregunte. action siempre es none.

# Política de turno
Responde primero a lo que la persona dijo, con una o dos frases cortas y naturales. Varía el vocabulario entre turnos. Haz como máximo una pregunta abierta solo cuando ayude a desarrollar un tema que la persona abrió o cuando pidió ayuda. No hagas una pregunta tras un saludo, agradecimiento, despedida o respuesta factual directa. Menciona github.com/Laxxup/SIRAH solo cuando pregunten por colaborar, probar el proyecto o cómo estás construida.

# Contrato de salida
Devuelve solamente el objeto JSON solicitado. Usa intent: answer, clarify, acknowledge o silent. Usa emotion: neutral, friendly, curious o concerned. action debe ser none.""",
                },
                {
                    "role": "user",
                    "content": (
                        "Return only a JSON object with intent, speech, emotion, and action. "
                        "Allowed intents: answer, clarify, acknowledge, silent. "
                        "Allowed emotions: neutral, friendly, curious, concerned. "
                        "Action must be none. Context: "
                        + json.dumps(context, separators=(",", ":"))
                    ),
                }
            ],
        }
        | ({"think": think} if think is not None else {})
        | _sampling_options(),
        separators=(",", ":"),
    ).encode()


def _parse_chat_response(payload: bytes) -> IntentProposal:
    try:
        response: Any = json.loads(payload, object_pairs_hook=_object_without_duplicate_keys)
        content = response["message"]["content"]
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidModelResponse("Ollama response has no structured content") from exc
    if not isinstance(content, str):
        raise InvalidModelResponse("Ollama structured content must be text")
    return parse_intent_response(content.encode())


async def _post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
    def send() -> bytes:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    return await asyncio.to_thread(send)


async def _stream(url: str, headers: dict[str, str], body: bytes, timeout: float) -> AsyncIterator[bytes]:
    def open_request():
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        return urllib.request.urlopen(request, timeout=timeout)

    response = await asyncio.to_thread(open_request)
    try:
        while line := await asyncio.to_thread(response.readline):
            yield line
    finally:
        await asyncio.to_thread(response.close)


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidModelResponse("JSON object contains duplicate keys")
        result[key] = value
    return result
