"""ActionRunner — bridge to Cortex ActionExecutor."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from sirah.errors import CapabilityExecutionError
from sirah.types import CapabilityExecutionResult, CapabilityRequest

__all__ = ["ActionRunner", "RobotPort"]

logger = logging.getLogger(__name__)


class RobotPort(Protocol):
    def send(self, command: object) -> None: ...
    def handled(self) -> bool: ...


class ActionRunner:
    def __init__(
        self,
        robot: RobotPort | None = None,
        translators: dict[str, Any] | None = None,
    ) -> None:
        self._robot = robot
        self._translators = translators or {}

    async def run(self, request: CapabilityRequest) -> CapabilityExecutionResult:
        translator = self._translators.get(request.name)

        if translator is not None:
            try:
                result = translator(request) if callable(translator) else translator
            except Exception as exc:
                raise CapabilityExecutionError(f"translator failed: {exc}") from exc
        else:
            result = None

        if self._robot is not None:
            try:
                self._robot.send(result or request)
            except Exception as exc:
                raise CapabilityExecutionError(f"robot send failed: {exc}") from exc

        return CapabilityExecutionResult(
            success=True,
            capability_name=request.name,
            details={"method": "cortex-bridge"},
        )

    async def stop_all(self) -> CapabilityExecutionResult:
        if self._robot is not None:
            self._robot.send(CapabilityRequest(name="robot.stop"))
        return CapabilityExecutionResult(success=True, capability_name="robot.stop")
