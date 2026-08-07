"""SIRAH Web Lab client for the headless runtime."""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from flask import Flask, jsonify, render_template, request

from sirah.core.runtime_client import RuntimeClient
from sirah.core.runtime_transport import RuntimeTransportClient
from sirah.errors import RuntimeAccessDeniedError, SirahRecoverableError
from sirah.types import ClientKind

__all__ = ["create_app"]


class _MalformedRuntimeResultError(Exception):
    """A runtime response cannot be safely represented by this HTTP adapter."""


def create_app(*, client: RuntimeClient) -> Flask:
    """Create a Web Lab adapter that never owns runtime resources."""
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")

    @app.route("/")
    def index() -> str:
        return render_template("index.html")

    @app.route("/api/chat", methods=["POST"])
    def api_chat() -> Any:
        data = request.get_json(silent=True) or {}
        text = data.get("text") if isinstance(data, Mapping) else None
        if not isinstance(text, str) or not text.strip():
            return _error_response("invalid_request", "Text is required.", 400)
        try:
            result = asyncio.run(client.submit_text(text))
            response = _serialize_chat_result(result)
        except Exception as exc:
            return _runtime_error_response(exc)
        return jsonify({"ok": True, "response": response})

    @app.route("/api/status")
    def api_status() -> Any:
        try:
            snapshot = asyncio.run(client.read_status())
            status = _serialize_status(snapshot)
        except Exception as exc:
            return _runtime_error_response(exc)
        return jsonify({"ok": True, **status})

    @app.route("/api/listen", methods=["POST"])
    def api_listen() -> Any:
        try:
            result = asyncio.run(client.submit_local_voice_turn())
            voice_turn = _serialize_voice_turn(result)
        except Exception as exc:
            return _runtime_error_response(exc)
        return jsonify({"ok": True, **voice_turn})

    return app


def _runtime_error_response(error: Exception) -> tuple[Any, int]:
    """Expose a stable error class without leaking runtime or device details."""
    if isinstance(error, RuntimeAccessDeniedError):
        return _error_response("access_denied", "Request not authorised.", 403)
    if isinstance(error, _MalformedRuntimeResultError):
        return _error_response(
            "invalid_runtime_result", "Runtime returned an invalid result.", 502
        )
    if isinstance(error, (SirahRecoverableError, RuntimeError)):
        return _error_response("runtime_unavailable", "Runtime is unavailable.", 503)
    return _error_response("internal_error", "Runtime request failed.", 500)


def _error_response(code: str, message: str, status: int) -> tuple[Any, int]:
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


def _serialize_status(snapshot: object) -> dict[str, object]:
    components = _read(snapshot, "components", None)
    if not isinstance(components, (list, tuple)):
        raise _MalformedRuntimeResultError
    serialized_components = [_serialize_component(component) for component in components]
    voice = next(
        (component for component in serialized_components if component["kind"] == "voice"),
        None,
    )
    voice_status = voice["status"] if voice is not None else "unavailable"
    return {
        "healthy": _status_healthy(serialized_components),
        "components": serialized_components,
        "voice": {
            "available": voice is not None and voice_status == "ready",
            "status": voice_status,
            "detail": voice["detail"] if voice is not None else "voice component unavailable",
        },
    }


def _status_healthy(components: list[dict[str, str]]) -> bool:
    return bool(components) and all(component["status"] == "ready" for component in components)


def _serialize_component(component: object) -> dict[str, str]:
    component_id = _read(component, "id")
    kind = _read(component_id, "kind")
    name = _read(component_id, "name")
    status = _read(component, "status")
    detail = _read(component, "detail")
    if (
        not isinstance(kind, str)
        or not isinstance(name, str)
        or not isinstance(status, str)
        or not isinstance(detail, str)
    ):
        raise _MalformedRuntimeResultError
    return {"kind": kind, "name": name, "status": status, "detail": detail}


def _serialize_chat_result(result: object) -> str:
    message = _read(result, "message")
    content = _read(message, "content")
    if not isinstance(content, str):
        raise _MalformedRuntimeResultError
    return content


def _serialize_voice_turn(result: object) -> dict[str, object]:
    metrics = _read(result, "diagnostics")
    completion = _read(result, "tts_completion")
    turn_id = _read(result, "turn_id")
    stage = _read(result, "stage")
    transcript = _read(result, "transcript")
    response = _read(result, "response")
    if (
        not isinstance(turn_id, str)
        or not turn_id
        or not isinstance(stage, str)
        or not stage
        or not _is_optional_string(transcript)
        or not _is_optional_string(response)
    ):
        raise _MalformedRuntimeResultError
    return {
        "turn_id": turn_id,
        "stage": stage,
        "metrics": _serialize_metrics(metrics),
        "transcript": transcript,
        "response": response,
        "tts_completion": _serialize_tts_completion(completion),
    }


def _serialize_metrics(metrics: object) -> dict[str, object] | None:
    if metrics is None:
        return None
    values = {
        field: _read(metrics, field)
        for field in (
            "bytes_count",
            "duration_ms",
            "sample_rate",
            "channels",
            "sample_width",
            "rms",
            "peak",
            "is_silent",
        )
    }
    if (
        not all(
            _is_nonnegative_int(values[field])
            for field in ("bytes_count", "duration_ms", "rms", "peak")
        )
        or not all(
            _is_positive_int(values[field])
            for field in ("sample_rate", "channels", "sample_width")
        )
        or not isinstance(values["is_silent"], bool)
        or cast(int, values["rms"]) > cast(int, values["peak"])
        or cast(int, values["peak"]) > 32_768
    ):
        raise _MalformedRuntimeResultError
    return values


def _serialize_tts_completion(completion: object) -> dict[str, object] | None:
    if completion is None:
        return None
    operation_id = _read(completion, "operation_id")
    success = _read(completion, "success")
    duration_ms = _read(completion, "duration_ms")
    if (
        not isinstance(operation_id, str)
        or not operation_id
        or not isinstance(success, bool)
        or not _is_nonnegative_number(duration_ms)
    ):
        raise _MalformedRuntimeResultError
    return {
        "operation_id": operation_id,
        "success": success,
        "duration_ms": cast(int | float, duration_ms),
    }


def _is_optional_string(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_number(value: object) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    return math.isfinite(value) and value >= 0


def _read(value: object, field: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        value = value.get(field, default)
    elif is_dataclass(value) and not isinstance(value, type):
        value = asdict(value).get(field, default)
    else:
        value = getattr(value, field, default)
    return value.value if isinstance(value, Enum) else value


def main() -> None:
    socket_path = Path(os.environ["SIRAH_RUNTIME_SOCKET"])
    secret = os.environ["SIRAH_WEB_LAB_SECRET"]
    client = RuntimeClient(
        ClientKind.WEB_LAB,
        RuntimeTransportClient(socket_path, ClientKind.WEB_LAB, secret),
    )
    create_app(client=client).run(host="127.0.0.1", port=5000, debug=False)
