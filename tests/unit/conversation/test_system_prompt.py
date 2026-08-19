"""Deterministic checks for the SIRAH system prompt and JSON contract.

These tests assert that the prompt contains the behavioral rules that drive the
adaptive conversational policy, without snapshotting the full prose. The
user-message JSON contract is asserted separately because removing it breaks
structured output (verified experimentally: 22/22 InvalidModelResponse).
"""

from __future__ import annotations

import json

from sirah.conversation.contracts import IntentRequest
from sirah.conversation.ollama import SYSTEM_PROMPT, _request_payload


def _user_message() -> str:
    request = IntentRequest("latency_probe", "hola", 1.0)
    payload = json.loads(_request_payload("test-model", request, think="low"))
    return payload["messages"][1]["content"]


def test_system_prompt_keeps_sirah_identity_and_verified_facts():
    assert "anfitriona robótica" in SYSTEM_PROMPT
    assert "Instituto Tecnológico de Ciudad Madero" in SYSTEM_PROMPT
    assert "no de la UNAM" in SYSTEM_PROMPT
    assert "una sola persona" in SYSTEM_PROMPT


def test_system_prompt_keeps_capabilities_and_limitations():
    assert "ESP32" in SYSTEM_PROMPT
    assert "Bluetooth" in SYSTEM_PROMPT
    assert "resumen de visión actual" in SYSTEM_PROMPT
    assert "etiquetas temporales, nunca identidad" in SYSTEM_PROMPT
    assert "No reconoces identidades, emociones ni objetos" in SYSTEM_PROMPT
    assert "no afirmes lo que no ves" in SYSTEM_PROMPT


def test_system_prompt_guides_adaptive_response_depth():
    assert "Ajusta la extensión a la intención" in SYSTEM_PROMPT
    assert "suficiente detalle para explicar o enseñar" in SYSTEM_PROMPT
    assert "conciso si piden" in SYSTEM_PROMPT
    assert "amplía si piden más profundidad" in SYSTEM_PROMPT


def test_system_prompt_uses_recent_turns_for_followups():
    assert "turnos recientes" in SYSTEM_PROMPT
    assert "¿por qué?" in SYSTEM_PROMPT
    assert "¿y eso?" in SYSTEM_PROMPT
    assert "continúa" in SYSTEM_PROMPT
    assert "no lo trates como aislado" in SYSTEM_PROMPT


def test_system_prompt_instructs_simpler_explanations():
    assert "explícalo más fácil" in SYSTEM_PROMPT
    assert "lenguaje simple" in SYSTEM_PROMPT
    assert "analogía" in SYSTEM_PROMPT


def test_system_prompt_instructs_recommendations_with_reasoning():
    assert "recomendaciones u opiniones" in SYSTEM_PROMPT
    assert "razón breve" in SYSTEM_PROMPT


def test_system_prompt_requires_spanish_only_output():
    assert "Habla solo español" in SYSTEM_PROMPT
    assert "Nunca mezcles inglés" in SYSTEM_PROMPT


def test_system_prompt_guides_non_template_greetings():
    assert "sin repetir siempre la misma fórmula" in SYSTEM_PROMPT
    assert "¿En qué puedo ayudarte?" in SYSTEM_PROMPT


def test_system_prompt_guides_natural_uncertainty():
    assert "reconoce con naturalidad cuando no conoces un dato" in SYSTEM_PROMPT


def test_system_prompt_retains_github_mention_policy():
    assert "github.com/Laxxup/SIRAH" in SYSTEM_PROMPT
    assert "colaborar, probar el proyecto o cómo estás construida" in SYSTEM_PROMPT


def test_json_contract_is_present_in_both_required_locations():
    assert "Devuelve solamente el objeto JSON solicitado" in SYSTEM_PROMPT
    assert "intent: answer, clarify, acknowledge o silent" in SYSTEM_PROMPT
    assert "emotion: neutral, friendly, curious o concerned" in SYSTEM_PROMPT
    assert "action debe ser none" in SYSTEM_PROMPT
    assert (
        "Return only a JSON object with intent, speech, emotion, and action"
        in _user_message()
    )
    assert "Allowed intents: answer, clarify, acknowledge, silent" in _user_message()
    assert "Allowed emotions: neutral, friendly, curious, concerned" in _user_message()
    assert "Action must be none" in _user_message()


def test_user_message_contract_keeps_the_json_instruction():
    user = _user_message()
    assert user.startswith("Return only a JSON object with intent, speech, emotion, and action")
    assert "Context: " in user