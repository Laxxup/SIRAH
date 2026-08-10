"""Component registry — runtime status bookkeeping (Stage 7).

Tracks each component's readiness as `ready | degraded | off`. Design
rules (legacy eyes.md concept, plan Stage 7):

- A serial failure DEGRADES eyes but the runtime keeps running: other
  components (camera, behavior, heartbeat?) continue and the app reports
  the degraded status instead of dying.
- `off` is the intentional not-present / not-armed state (eyes disarmed by
  SIRAH_EYES=0, lab disabled, camera absent).
- The registry is synchronous: status mutations happen on the asyncio loop
  thread; no locking needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ComponentStatus(str):
    """Component readiness levels (registry contract)."""

    READY = "ready"
    DEGRADED = "degraded"
    OFF = "off"


@dataclass(frozen=True)
class ComponentState:
    status: str  # ComponentStatus value
    detail: str = ""


@dataclass
class ComponentRegistry:
    components: dict[str, ComponentState] = field(default_factory=dict)

    def set(self, name: str, status: str, detail: str = "") -> None:
        self.components[name] = ComponentState(status, detail)

    def update(self, name: str, **changes: str) -> None:
        current = self.components.get(name, ComponentState(ComponentStatus.OFF))
        self.components[name] = ComponentState(
            status=changes.get("status", current.status),
            detail=changes.get("detail", current.detail),
        )

    def get(self, name: str) -> ComponentState:
        return self.components.get(name, ComponentState(ComponentStatus.OFF))

    def snapshot(self) -> dict[str, ComponentState]:
        return dict(self.components)

    def all_ready(self) -> bool:
        return any(s.status == ComponentStatus.READY for s in self.components.values())