# Conversational Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SIRAH answer ordinary social turns naturally rather than with repeated fixed scripts.

**Architecture:** Keep deterministic local responses only for dynamic facts and low-confidence recovery. Move ordinary social turns through the existing `IntentProposer`, and replace the monolithic system prompt with short, ordered policy sections while retaining the existing closed JSON contract.

**Tech Stack:** Python 3.12, pytest, Ollama `/api/chat`.

## Global Constraints

- Keep `IntentName`, `EmotionName`, and `ActionName` closed and unchanged.
- Keep `action` equal to `none`.
- Preserve the ITCM identity and verified capability limitations.
- Do not add persistent memory, tools, providers, or dependencies.

---

### Task 1: Delegate ordinary social turns

**Files:**
- Modify: `tests/unit/conversation/test_core.py:47-68`
- Modify: `src/sirah/conversation/core.py:55-97`

**Interfaces:**
- Consumes: `ConversationCore.respond(transcript: Transcript) -> IntentProposal`
- Produces: social turns forwarded to `IntentProposer.propose(request: IntentRequest) -> IntentProposal`

- [ ] **Step 1: Write failing tests**

```python
async def test_core_delegates_social_turns_to_the_proposer():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "Qué gusto escucharte."))

    response = await ConversationCore(proposer).respond(_transcript("¿Cómo estás?"))

    assert response.speech == "Qué gusto escucharte."
    assert proposer.requests[0].text == "¿Cómo estás?"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/conversation/test_core.py::test_core_delegates_social_turns_to_the_proposer -q`

Expected: failure because `_local()` returns a fixed response.

- [ ] **Step 3: Remove ordinary social branches from `_local()`**

```python
def _local(self, text: str) -> IntentProposal | None:
    normalized = text.lower()
    if "hora" in normalized:
        return IntentProposal(IntentName.ANSWER, f"Son las {self._clock():%H:%M}.", EmotionName.FRIENDLY)
    if "fecha" in normalized or "día" in normalized or "dia" in normalized:
        return IntentProposal(IntentName.ANSWER, f"Hoy es {self._clock():%Y-%m-%d}.", EmotionName.FRIENDLY)
    if any(phrase in normalized for phrase in ("qué puedes hacer", "que puedes hacer", "qué te falta", "que te falta", "qué quieres lograr", "que quieres lograr", "tus capacidades", "tus limitaciones")):
        return IntentProposal(IntentName.ANSWER, "Puedo escucharte y conversar contigo por voz. Mi sistema visual sigue en desarrollo; quiero comprender mejor mi entorno y seguir rostros en el futuro.", EmotionName.FRIENDLY)
    return None
```

- [ ] **Step 4: Run the focused test and the conversation unit suite**

Run: `python -m pytest tests/unit/conversation/test_core.py::test_core_delegates_social_turns_to_the_proposer tests/unit/conversation -q`

Expected: all tests pass.

### Task 2: Make the cloud policy explicit and concise

**Files:**
- Modify: `tests/unit/conversation/test_ollama.py:64-87`
- Modify: `src/sirah/conversation/ollama.py:309-337`

**Interfaces:**
- Consumes: `_request_payload(model: str, request: IntentRequest, *, stream: bool = False, think: bool | str | None = None) -> bytes`
- Produces: an Ollama chat payload with a structured system policy and JSON-only user request.

- [ ] **Step 1: Write failing payload assertions**

```python
assert "# Identidad y hechos verificados" in payload["messages"][0]["content"]
assert "# Política de turno" in payload["messages"][0]["content"]
assert "No hagas una pregunta" in payload["messages"][0]["content"]
assert "solo cuando pregunten por colaborar" in payload["messages"][0]["content"]
```

- [ ] **Step 2: Run the payload test to verify it fails**

Run: `python -m pytest tests/unit/conversation/test_ollama.py::test_ollama_client_sends_only_structured_request_and_parses_intent -q`

Expected: failure because the current system message has no sections or turn policy.

- [ ] **Step 3: Replace the monolithic content with sectioned policy text**

```python
content = """# Identidad y hechos verificados
...
# Política de turno
Responde primero a lo que la persona dijo. Haz como máximo una pregunta abierta solo si ayuda a desarrollar el tema. No hagas una pregunta tras un saludo, agradecimiento, despedida o respuesta factual directa.
...
# Contrato de salida
..."""
```

- [ ] **Step 4: Run the focused test and the conversation unit suite**

Run: `python -m pytest tests/unit/conversation/test_ollama.py::test_ollama_client_sends_only_structured_request_and_parses_intent tests/unit/conversation -q`

Expected: all tests pass.

### Task 3: Verify the change

**Files:**
- Verify: `src/sirah/conversation/core.py`
- Verify: `src/sirah/conversation/ollama.py`
- Verify: `tests/unit/conversation/test_core.py`
- Verify: `tests/unit/conversation/test_ollama.py`

- [ ] **Step 1: Run formatter and static checks**

Run: `python -m ruff check src tests && python -m mypy src`

Expected: no diagnostics.

- [ ] **Step 2: Run the complete test suite**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Inspect the final diff**

Run: `git diff --check && git diff -- src/sirah/conversation/core.py src/sirah/conversation/ollama.py tests/unit/conversation/test_core.py tests/unit/conversation/test_ollama.py`

Expected: no whitespace errors; only the intended policy and test changes.
