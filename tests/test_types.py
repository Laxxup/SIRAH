"""Test immutable types and data classes."""

from __future__ import annotations

from sirah.types import (
    CapabilityDefinition,
    CapabilityExecutionResult,
    CapabilityRequest,
    ComponentId,
    ComponentKind,
    ComponentState,
    ComponentStatus,
    ConversationMessage,
    DecisionType,
    FaceDetection,
    InitiativeAction,
    InitiativeDecision,
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
    PerceptionFrame,
    PresentContext,
    SpeechCompletion,
    SpeechRecognitionEvent,
    SystemSnapshot,
)


def test_capability_definition() -> None:
    d = CapabilityDefinition(name="test", description="desc")
    assert d.name == "test"
    assert d.description == "desc"
    assert d.category == "general"
    assert d.requires_safety is True


def test_capability_request() -> None:
    r = CapabilityRequest(name="test", params={"a": 1})
    assert r.name == "test"
    assert r.params["a"] == 1


def test_capability_execution_result() -> None:
    ok = CapabilityExecutionResult(success=True, capability_name="x")
    assert ok.success
    fail = CapabilityExecutionResult(success=False, capability_name="x", error="boom")
    assert not fail.success
    assert fail.error == "boom"


def test_conversation_message() -> None:
    m = ConversationMessage(role="user", content="hola")
    assert m.role == "user"
    assert m.content == "hola"


def test_intelligence_decision() -> None:
    d = IntelligenceDecision(
        decision_type=DecisionType.CONVERSATION,
        text_response="hola",
        confidence=0.95,
    )
    assert d.text_response == "hola"
    assert d.capability_name is None
    assert d.confidence == 0.95


def test_intelligence_request() -> None:
    msgs = (ConversationMessage(role="user", content="test"),)
    req = IntelligenceRequest(messages=msgs)
    assert len(req.messages) == 1
    assert req.temperature == 0.7
    assert req.max_tokens == 256


def test_intelligence_response() -> None:
    d = IntelligenceDecision(decision_type=DecisionType.CONVERSATION, text_response="x")
    r = IntelligenceResponse(raw_text="x", decision=d, latency_ms=100, model="test")
    assert r.decision is d
    assert r.model == "test"


def test_face_detection() -> None:
    f = FaceDetection(bbox=(0.1, 0.2, 0.3, 0.4), confidence=0.9)
    assert f.bbox[0] == 0.1
    assert f.confidence == 0.9


def test_perception_frame() -> None:
    p = PerceptionFrame(timestamp=1.0)
    assert len(p.faces) == 0
    assert p.pose is None


def test_speech_completion() -> None:
    s = SpeechCompletion(operation_id="abc", success=True, duration_ms=50)
    assert s.operation_id == "abc"
    assert s.success


def test_speech_recognition_event() -> None:
    e = SpeechRecognitionEvent(text="hola", is_final=True, confidence=0.9)
    assert e.text == "hola"
    assert e.is_final


def test_initiative_decision() -> None:
    d = InitiativeDecision(action=InitiativeAction.GREET, text="hola")
    assert d.action == InitiativeAction.GREET
    assert d.text == "hola"


def test_system_snapshot_healthy() -> None:
    snap = SystemSnapshot()
    assert snap.healthy()


def test_component_id_str() -> None:
    cid = ComponentId(kind=ComponentKind.CORE, name="test")
    assert str(cid) == "core/test"


def test_component_state_with_status() -> None:
    cid = ComponentId(kind=ComponentKind.VOICE, name="tts")
    cs = ComponentState(id=cid)
    updated = cs.with_status(ComponentStatus.READY, "ok")
    assert updated.status == ComponentStatus.READY
    assert updated.detail == "ok"


def test_present_context_defaults() -> None:
    pc = PresentContext()
    assert pc.user_text is None
    assert pc.face_count == 0
