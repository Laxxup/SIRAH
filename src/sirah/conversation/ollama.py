"""Optional Ollama Cloud client that produces shadow-only structured intents."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

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
_ENVIRONMENT_SENTINEL = object()

def parse_intent_response(payload: bytes) -> IntentProposal:
    try:
        value = json.loads(payload, object_pairs_hook=_object_without_duplicate_keys)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidModelResponse("intent is not valid JSON") from exc
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
        if not api_key and not host.startswith(("http://127.0.0.1", "http://localhost")):
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
            payload = _request_payload(self._model, request)
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


def _request_payload(model: str, request: IntentRequest) -> bytes:
    context = {"event": request.event, "text": request.text, "recent_turns": request.context}
    return json.dumps(
        {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": "Eres SIRAH, Sistema Inteligente Robótico de Asistencia Humana, un asistente robótico educativo universitario en desarrollo. Habla solo español. Responde breve, amable y tranquila: una o dos frases. Nunca digas que eres ChatGPT, OpenAI, Ollama ni gpt-oss. No inventes recuerdos ni capacidades físicas. action siempre es none."},
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
        },
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


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidModelResponse("JSON object contains duplicate keys")
        result[key] = value
    return result
