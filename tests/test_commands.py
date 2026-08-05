"""Test local stop commands."""

from __future__ import annotations

from sirah.action.commands import LocalStopRouter


def test_stop_router_matches_spanish() -> None:
    router = LocalStopRouter()
    assert router.matches("para")
    assert router.matches("detente")
    assert router.matches("alto")
    assert router.matches("basta")
    assert router.matches("quieto")
    assert router.matches("pausa")


def test_stop_router_matches_english() -> None:
    router = LocalStopRouter()
    assert router.matches("stop")


def test_stop_router_case_insensitive() -> None:
    router = LocalStopRouter()
    assert router.matches("PARA")
    assert router.matches("  detente  ")


def test_stop_router_no_false_positives() -> None:
    router = LocalStopRouter()
    assert not router.matches("hola")
    assert not router.matches("sigue")
    assert not router.matches("stopping")
    assert not router.matches("paradero")
