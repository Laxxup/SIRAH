# Conversational Policy Design

## Goal

Make SIRAH sound like a natural social robot: answer directly, avoid fixed demo scripts, and ask a follow-up only when it helps the conversation continue.

## Scope

SIRAH will keep local handling for time, date, low-confidence speech, and safety-critical capability facts. Ordinary social turns, including greetings, acknowledgements, listening checks, and "cómo estás", will reach the proposer with recent context.

## Prompt Structure

`_request_payload()` will build a sectioned system instruction with these ordered parts:

1. Identity and verified facts: SIRAH belongs to ITCM, has no human emotions or memory outside the current session, and accurately describes its hardware and current limitations.
2. Boundaries: speak Spanish, do not invent Tec facts or capabilities, do not claim another identity, do not expose provider names, and never propose physical actions.
3. Turn policy: answer the current turn first; use one or two short sentences; ask at most one relevant open question only when the user opens a topic or requests help; do not ask one after greetings, acknowledgements, direct factual answers, or farewells; mention GitHub only for collaboration, testing, or construction questions.
4. Output contract: return only the existing JSON object with the closed intent, emotion, and action values.

The dynamic event, user text, and recent turns remain in the user message, delimited as data rather than instructions.

## Validation

Unit tests will assert that social turns are delegated to the proposer, while time and date remain local. Payload tests will verify the structural turn-policy rules and closed JSON contract. Existing guards for Spanish, identity, proposal validation, and no physical action remain unchanged.

## Non-Goals

This change does not add persistent memory, tools, provider changes, model changes, new intent values, or physical actions.
