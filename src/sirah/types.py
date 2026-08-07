"""Centralised immutable data types and enums for SIRAH."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sirah.voice.diagnostics import AudioMetrics, AudioStage

__all__ = [
    "DecisionType",
    "ClientKind",
    "ClientCapabilities",
    "RuntimeRequest",
    "ComponentKind",
    "ComponentStatus",
    "InitiativeAction",
    "IntelligenceDecision",
    "IntelligenceRequest",
    "IntelligenceResponse",
    "ConversationMessage",
    "ConversationResult",
    "PresentContext",
    "CapabilityDefinition",
    "CapabilityRequest",
    "CapabilityExecutionResult",
    "SystemSnapshot",
    "ComponentId",
    "ComponentState",
    "InitiativeDecision",
    "FaceDetection",
    "PoseEstimate",
    "PerceptionFrame",
    "SpeechCompletion",
    "SpeechRecognitionEvent",
    "VoiceTurnResult",
    "EdgeMessage",
]


class DecisionType(Enum):
    CONVERSATION = auto()
    INITIATIVE = auto()
    EMERGENCY = auto()


class ClientKind(StrEnum):
    """Identities recognised by the headless runtime."""

    WEB_LAB = "web_lab"
    CLI = "cli"


class ClientCapabilities(StrEnum):
    """Operations exposed to runtime clients in the initial ACL."""

    CONVERSATION_SUBMIT = "conversation.submit"
    STATUS_READ = "status.read"
    DIAGNOSTICS_READ = "diagnostics.read"
    LABORATORY_MANUAL_TEXT = "laboratory.manual_text"
    LOCAL_VOICE_TURN_SUBMIT = "local_voice_turn.submit"


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    """A client operation with immutable, non-device metadata."""

    capability: ClientCapabilities
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


def _freeze_metadata(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_metadata(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_metadata(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze_metadata(item) for item in value)
    return value


class ComponentKind(Enum):
    CORE = "core"
    INTELLIGENCE = "intelligence"
    PERCEPTION = "perception"
    VOICE = "voice"
    ACTION = "action"
    SOCIAL = "social"
    BRIDGE = "bridge"


class ComponentStatus(Enum):
    UNINITIALISED = "uninitialised"
    INITIALISING = "initialising"
    READY = "ready"
    DEGRADED = "degraded"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class InitiativeAction(Enum):
    GREET = "greet"
    CHECK_IN = "check_in"
    SILENT = "silent"


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class PresentContext:
    user_text: str | None = None
    face_count: int = 0
    voice_activity: bool = False
    system_state: str = "idle"


@dataclass(frozen=True, slots=True)
class IntelligenceRequest:
    messages: tuple[ConversationMessage, ...]
    context: PresentContext = field(default_factory=PresentContext)
    max_tokens: int = 256
    temperature: float = 0.7
    system_prompt_override: str | None = None


@dataclass(frozen=True, slots=True)
class IntelligenceDecision:
    decision_type: DecisionType
    text_response: str
    capability_name: str | None = None
    capability_params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    reasoning: str = ""


@dataclass(frozen=True, slots=True)
class IntelligenceResponse:
    raw_text: str
    decision: IntelligenceDecision | None = None
    latency_ms: float = 0.0
    model: str = ""


@dataclass(frozen=True, slots=True)
class ConversationResult:
    message: ConversationMessage
    decision: IntelligenceDecision | None = None
    capability_result: CapabilityExecutionResult | None = None


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    name: str
    description: str
    category: str = "general"
    parameters: tuple[dict[str, Any], ...] = ()
    requires_safety: bool = True
    timeout_ms: float = 30_000.0


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityExecutionResult:
    success: bool
    capability_name: str
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FaceDetection:
    bbox: tuple[float, float, float, float]  # x, y, w, h normalised [0,1]
    confidence: float
    landmarks: tuple[tuple[float, float], ...] | None = None
    face_id: int = -1


@dataclass(frozen=True, slots=True)
class PoseEstimate:
    landmarks: tuple[tuple[float, float, float], ...] = ()
    head_rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class PerceptionFrame:
    timestamp: float
    faces: tuple[FaceDetection, ...] = ()
    pose: PoseEstimate | None = None
    frame_width: int = 640
    frame_height: int = 480


@dataclass(frozen=True, slots=True)
class SpeechCompletion:
    operation_id: str
    success: bool
    error: str | None = None
    duration_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class SpeechRecognitionEvent:
    text: str
    is_final: bool
    confidence: float = 0.0
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class VoiceTurnResult:
    """Ephemeral terminal result for one locally-owned voice turn."""

    turn_id: str
    stage: AudioStage
    diagnostics: AudioMetrics | None = None
    transcript: str | None = None
    response: str | None = None
    tts_completion: SpeechCompletion | None = None


@dataclass(frozen=True, slots=True)
class InitiativeDecision:
    action: InitiativeAction
    text: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ComponentId:
    kind: ComponentKind
    name: str

    def __str__(self) -> str:
        return f"{self.kind.value}/{self.name}"


@dataclass(frozen=True, slots=True)
class ComponentState:
    id: ComponentId
    status: ComponentStatus = ComponentStatus.UNINITIALISED
    detail: str = ""

    def with_status(self, status: ComponentStatus, detail: str = "") -> ComponentState:
        return ComponentState(id=self.id, status=status, detail=detail)


@dataclass(frozen=True, slots=True)
class SystemSnapshot:
    components: tuple[ComponentState, ...] = ()
    timestamp: float = 0.0

    def healthy(self) -> bool:
        return all(
            c.status not in (ComponentStatus.ERROR, ComponentStatus.SHUTDOWN)
            for c in self.components
        )


@dataclass(frozen=True, slots=True)
class EdgeMessage:
    msg_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
