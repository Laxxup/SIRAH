"""Web Lab runtime-client adapter tests."""

from __future__ import annotations

import pytest

from sirah.core.runtime_client import RuntimeClient
from sirah.errors import RuntimeAccessDeniedError
from sirah.types import (
    ClientKind,
    ComponentId,
    ComponentKind,
    ComponentState,
    ComponentStatus,
    RuntimeRequest,
    SpeechCompletion,
    SystemSnapshot,
    VoiceTurnResult,
)
from sirah.voice.diagnostics import AudioMetrics, AudioStage
from sirah.web_server import create_app


class RecordingRuntime:
    def __init__(self) -> None:
        self.requests: list[RuntimeRequest] = []
        self.error: Exception | None = None
        self.result: object | None = None

    async def __call__(self, request: RuntimeRequest) -> object:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        if request.capability.value == "local_voice_turn.submit":
            return VoiceTurnResult(
                turn_id="turn-123",
                stage=AudioStage.COMPLETED,
                diagnostics=AudioMetrics(
                    bytes_count=32000,
                    duration_ms=1000,
                    sample_rate=16000,
                    channels=1,
                    sample_width=2,
                    rms=950,
                    peak=1800,
                    is_silent=False,
                ),
                transcript="hola",
                response="respuesta",
                tts_completion=SpeechCompletion(
                    operation_id="speech-123",
                    success=True,
                    duration_ms=250,
                ),
            )
        if request.metadata:
            return {"message": {"content": "respuesta"}}
        return SystemSnapshot(
            components=(
                ComponentState(
                    id=ComponentId(ComponentKind.CORE, "orchestrator"),
                    status=ComponentStatus.READY,
                    detail="started",
                ),
                ComponentState(
                    id=ComponentId(ComponentKind.VOICE, "speech"),
                    status=ComponentStatus.READY,
                    detail="recognizer ready",
                ),
            )
        )


@pytest.fixture
def web_app():  # type: ignore[no-untyped-def]
    runtime = RecordingRuntime()
    return create_app(client=RuntimeClient(ClientKind.WEB_LAB, runtime)), runtime


def test_status_route_reads_runtime_client(web_app) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    assert response.json == {
        "ok": True,
        "healthy": True,
        "components": [
            {"kind": "core", "name": "orchestrator", "status": "ready", "detail": "started"},
            {"kind": "voice", "name": "speech", "status": "ready", "detail": "recognizer ready"},
        ],
        "voice": {"available": True, "status": "ready", "detail": "recognizer ready"},
    }
    assert runtime.requests[0].capability.value == "status.read"


@pytest.mark.parametrize(
    "status",
    [
        ComponentStatus.UNINITIALISED,
        ComponentStatus.DEGRADED,
        ComponentStatus.ERROR,
        ComponentStatus.SHUTDOWN,
    ],
)
def test_status_marks_any_non_ready_component_unhealthy(
    web_app, status: ComponentStatus
) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app
    runtime.result = SystemSnapshot(
        components=(
            ComponentState(
                id=ComponentId(ComponentKind.VOICE, "speech"),
                status=status,
                detail="voice unavailable",
            ),
        )
    )

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    assert response.json["healthy"] is False
    assert response.json["voice"] == {
        "available": False,
        "status": status.value,
        "detail": "voice unavailable",
    }


def test_status_reports_voice_as_explicitly_unavailable_when_missing(web_app) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app
    runtime.result = SystemSnapshot(
        components=(
            ComponentState(
                id=ComponentId(ComponentKind.CORE, "orchestrator"),
                status=ComponentStatus.READY,
            ),
        )
    )

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    assert response.json["voice"] == {
        "available": False,
        "status": "unavailable",
        "detail": "voice component unavailable",
    }


def test_status_marks_an_empty_component_snapshot_unhealthy(web_app) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app
    runtime.result = SystemSnapshot()

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    assert response.json["healthy"] is False
    assert response.json["voice"]["available"] is False


def test_chat_route_submits_runtime_client_text(web_app) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app

    response = app.test_client().post("/api/chat", json={"text": "hola"})

    assert response.status_code == 200
    assert response.json["response"] == "respuesta"
    assert runtime.requests[0].metadata == {"text": "hola"}


@pytest.mark.parametrize("payload", [[], {"text": 7}])
def test_chat_route_rejects_malformed_json_with_a_safe_error(
    web_app, payload: object
) -> None:  # type: ignore[no-untyped-def]
    app, _ = web_app

    response = app.test_client().post("/api/chat", json=payload)

    assert response.status_code == 400
    assert response.json == {
        "ok": False,
        "error": {"code": "invalid_request", "message": "Text is required."},
    }


def test_chat_route_rejects_invalid_json_with_a_safe_error(web_app) -> None:  # type: ignore[no-untyped-def]
    app, _ = web_app

    response = app.test_client().post(
        "/api/chat", data="{", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.json == {
        "ok": False,
        "error": {"code": "invalid_request", "message": "Text is required."},
    }


def test_listen_route_submits_a_metadata_free_local_voice_turn(web_app) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app

    response = app.test_client().post("/api/listen", json={"device": "hw:3,0"})

    assert response.status_code == 200
    assert response.json == {
        "ok": True,
        "turn_id": "turn-123",
        "stage": "completed",
        "metrics": {
            "bytes_count": 32000,
            "duration_ms": 1000,
            "sample_rate": 16000,
            "channels": 1,
            "sample_width": 2,
            "rms": 950,
            "peak": 1800,
            "is_silent": False,
        },
        "transcript": "hola",
        "response": "respuesta",
        "tts_completion": {
            "operation_id": "speech-123",
            "success": True,
            "duration_ms": 250,
        },
    }
    assert runtime.requests[0].capability.value == "local_voice_turn.submit"
    assert runtime.requests[0].metadata == {}


def _voice_result() -> dict[str, object]:
    return {
        "turn_id": "turn-123",
        "stage": "completed",
        "diagnostics": {
            "bytes_count": 32000,
            "duration_ms": 1000,
            "sample_rate": 16000,
            "channels": 1,
            "sample_width": 2,
            "rms": 950,
            "peak": 1800,
            "is_silent": False,
        },
        "transcript": "hola",
        "response": "respuesta",
        "tts_completion": {
            "operation_id": "speech-123",
            "success": True,
            "duration_ms": 250,
        },
    }


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("diagnostics", "bytes_count"), "32000"),
        (("diagnostics", "duration_ms"), -1),
        (("diagnostics", "sample_rate"), 0),
        (("diagnostics", "channels"), 0),
        (("diagnostics", "sample_width"), 0),
        (("diagnostics", "rms"), -1),
        (("diagnostics", "peak"), -1),
        (("diagnostics", "is_silent"), "false"),
        (("transcript",), 7),
        (("response",), 7),
        (("tts_completion", "operation_id"), 7),
        (("tts_completion", "success"), "true"),
        (("tts_completion", "duration_ms"), -1),
        (("tts_completion", "duration_ms"), float("inf")),
        (("tts_completion", "duration_ms"), float("nan")),
    ],
)
def test_listen_route_rejects_malformed_nested_voice_fields(
    web_app, path: tuple[str, ...], value: object
) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app
    result = _voice_result()
    target: dict[str, object] = result
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value
    runtime.result = result

    response = app.test_client().post("/api/listen", json={})

    assert response.status_code == 502
    assert response.json == {
        "ok": False,
        "error": {
            "code": "invalid_runtime_result",
            "message": "Runtime returned an invalid result.",
        },
    }


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/status", None),
        ("post", "/api/listen", {}),
        ("post", "/api/chat", {"text": "hola"}),
    ],
)
def test_api_routes_return_safe_typed_errors(
    web_app, method: str, path: str, payload: dict[str, str] | None
) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app
    runtime.error = RuntimeAccessDeniedError("capture device hw:3,0 is forbidden")

    response = getattr(app.test_client(), method)(path, json=payload)

    assert response.status_code == 403
    assert response.json == {
        "ok": False,
        "error": {"code": "access_denied", "message": "Request not authorised."},
    }


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/status", None),
        ("post", "/api/listen", {}),
        ("post", "/api/chat", {"text": "hola"}),
    ],
)
def test_api_routes_reject_malformed_runtime_results(
    web_app, method: str, path: str, payload: dict[str, str] | None
) -> None:  # type: ignore[no-untyped-def]
    app, runtime = web_app
    runtime.result = {"unexpected": "result"}

    response = getattr(app.test_client(), method)(path, json=payload)

    assert response.status_code == 502
    assert response.json == {
        "ok": False,
        "error": {
            "code": "invalid_runtime_result",
            "message": "Runtime returned an invalid result.",
        },
    }


def test_template_only_references_implemented_api_routes(web_app) -> None:  # type: ignore[no-untyped-def]
    app, _ = web_app

    html = app.test_client().get("/").get_data(as_text=True)

    assert "/api/chat" in html
    assert "/api/listen" in html
    assert "/api/status" in html
    for stale_route in (
        "/api/autonomy",
        "/api/mood",
        "/api/overlay",
        "/api/upload_frame",
        "/api/vision",
        "/camera",
    ):
        assert stale_route not in html


def test_template_renders_structured_errors_and_marks_failed_status_unavailable(
    web_app,
) -> None:  # type: ignore[no-untyped-def]
    app, _ = web_app

    html = app.test_client().get("/").get_data(as_text=True)

    assert "data.error?.message || 'Error'" in html
    assert "function setUnavailableStatus" in html
    assert "status-dot error" in html
    assert "Voz: no disponible" in html
