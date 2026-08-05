"""Test ActionRunner and SimulatedRobot."""

from __future__ import annotations

import pytest

from sirah.action.runner import ActionRunner
from sirah.action.simulated import SimulatedRobot
from sirah.types import CapabilityRequest, CapabilityExecutionResult
from sirah.errors import CapabilityExecutionError


@pytest.mark.asyncio
async def test_runner_executes_capability() -> None:
    robot = SimulatedRobot()
    runner = ActionRunner(robot=robot)
    req = CapabilityRequest(name="robot.greet")
    result = await runner.run(req)
    assert result.success
    assert result.capability_name == "robot.greet"
    assert len(robot.commands) == 1


@pytest.mark.asyncio
async def test_runner_records_commands() -> None:
    robot = SimulatedRobot()
    runner = ActionRunner(robot=robot)
    await runner.run(CapabilityRequest(name="robot.greet"))
    await runner.run(CapabilityRequest(name="robot.home"))
    assert len(robot.commands) == 2
    assert robot.handled() is True


@pytest.mark.asyncio
async def test_runner_stop_all() -> None:
    robot = SimulatedRobot()
    runner = ActionRunner(robot=robot)
    result = await runner.stop_all()
    assert result.success
    assert result.capability_name == "robot.stop"
    assert robot.last_command is not None


@pytest.mark.asyncio
async def test_runner_no_robot() -> None:
    runner = ActionRunner(robot=None)
    req = CapabilityRequest(name="robot.greet")
    result = await runner.run(req)
    assert result.success


@pytest.mark.asyncio
async def test_simulated_robot_failure() -> None:
    robot = SimulatedRobot(fail_on_send=True)
    runner = ActionRunner(robot=robot)
    req = CapabilityRequest(name="robot.home")
    with pytest.raises(CapabilityExecutionError, match="simulated robot failure"):
        await runner.run(req)


def test_simulated_robot_reset() -> None:
    robot = SimulatedRobot()
    robot.send(CapabilityRequest(name="test"))
    assert len(robot.commands) == 1
    robot.reset()
    assert len(robot.commands) == 0
