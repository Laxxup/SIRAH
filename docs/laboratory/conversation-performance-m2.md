# M2 — Conversation Performance: Phase 1 Research + Measurement Plan

> Status: Phase 1 (research + measurement only). No production code is changed
> by this document. It records the stabilized baseline, a per-stage measurement
> procedure, the current-bottleneck analysis, and a prioritized plan for M2.
>
> Branch under which this milestone runs: `feature/conversation-performance`.

## 1. Baseline confirmation

| Gate | Result |
|---|---|
| Branch | `feature/conversation-performance` (confirmed via `git branch --show-current`) |
| Full pytest suite | 413 passed |
| Contract suite | 95 passed |
| ruff | All checks passed |
| mypy | Success, 69 source files |
| Untracked tooling files | `.opencode/`, `opencode.json`, `AGENTS.md`, `.python-version`, `clean-local-artifacts.sh`, `exclude-opencode-worktrees.sh`, `sync-opencode-worktrees.sh` untouched |

No local SIRAH env, no recorded sessions, and no running Ollama instance were
found on this development machine, so live measurements must be executed by the
operator on the lab laptop and on the Raspberry Pi 4B using the procedures in
this document. Static baseline values below are read from the stabilized code.

## 2. Current conversation pipeline (as implemented)

```
capture (16 kHz mono, 512-frame blocks = 32 ms)
  -> Silero ONNX VAD per chunk (threshold 0.5)
  -> turn buffering (pre_roll 300 ms, max_turn 15 s, max_queue 512 chunks)
  -> end-of-speech (end_silence_ms 700)
  -> _close_turn -> PROCESSING
  -> STT (Faster-Whisper local, int8 CPU base | Groq whisper-large-v3-turbo)
  -> ConversationCore.respond
        _local() fast path (name/time/date/capabilities)
        Ollama /api/chat non-streaming single-flight, budget 10
        Spanish/identity repair -> second proposal (double round-trip)
        strict JSON validator (closed Intent/Emotion/Action schema)
  -> TTS (Edge streaming via ffmpeg | Kokoro local | Azure)
        FallbackTTS: Edge -> Kokoro
  -> PCMPlayer / SoundDevicePCMPlayer (stream path latency=0.3 s buffer)
  -> post_playback_guard_ms 500 before VAD resumes
```

`--lab` already emits per-stage markers via `TurnTiming`:

- `Fin de voz detectado` — `continuous.py:252`
- `STT <provider>: iniciando` / `listo` — `continuous.py:260-262`
- `Ollama: iniciando` / `respuesta lista` — `session.py:84-86`
- `TTS: iniciando` / `primer PCM listo` / `Altavoz: iniciando` /
  `Altavoz: reproducción terminada` — `session.py:88-99`, `session.py:150-167`
- `Respuesta: silenciosa` — `session.py:101`
- Recovery/`RECOVERING` and capture queue metrics — `cli/conversation.py:417`,
  `cli/conversation.py:467-470`

### Static latency budget (from code, current configuration)

| Stage | Configured/expected | Evidence |
|---|---|---|
| end_silence wait | 700 ms + up to one 32 ms chunk | `continuous.py:38-50`, `continuous.py:223` |
| endpoint -> STT start | ~one scheduling point | `continuous.py:237-256` |
| STT (Groq, short turn) | ~180-400 ms incl. TLS/upload (research) | `groq_stt.py:42-71`, 2026 benchmarks |
| STT (local base int8) | laptop ~200-800 ms; Pi 4 ~1-3 s (est.) | `stt.py:41-72` |
| LLM non-streaming | 1-3 s cloud; prefill dominated; repair adds 1x more | `ollama.py:284-306`, `core.py:46-49` |
| TTS Edge first PCM | ~300-800 ms incl. new WebSocket+TLS | `edge_tts.py:67-75` |
| Playback start | up to 300 ms buffer + device | `playback.py:302` |
| post-playback guard | 500 ms before next turn | `continuous.py:270` |
| E2E (end of speech -> first audio) | ≈ 2.5-5 s | sum of above |

Matches the original release audit's 2.5-5 s estimate.

## 3. Measurement procedure (run on lab laptop, then Pi 4B)

Always restart the process between conditions. Record p50/p95/p99. Use the
existing `docs/laboratory/voice-latency-baseline.md` protocol (30 normal turns,
10 long turns 10-15 s, 20 Ctrl-C interrupts, 20 barge-in attempts).

### 3.1 VAD / endpointing

- Keep `SIRAH_VAD_END_SILENCE_MS` at the swept values `500, 550, 600, 650, 700`
  and record the `Fin de voz detectado` -> `STT <provider>: iniciando` delta
  (endpoint->STT overhead) and `Fin de voz -> STT listo` (turn closure + STT).
- Acceptance: the lowest value that never clips final words and does not worsen
  transcripts. Log any "discardes" (dropped frames).
- Sweep `SIRAH_POST_PLAYBACK_GUARD_MS` `200, 350, 500`; measure time from
  `Altavoz: reproducción terminada` to the next `Fin de voz detectado`.

### 3.2 STT

- Groq: `sirah-conversation listen --live --stt-provider groq --lab`; read
  `STT Groq: iniciando -> listo`. If the `x-groq-openai-usage-ms` header is
  exposed by the transport under test, record it to split inference vs network.
- Local: `--stt-provider local`; record the same marker. On Pi, capture
  `SIRAH_WHISPER_COMPUTE_TYPE=int8`, `SIRAH_WHISPER_MODEL=base`.
- Record transcript quality regressions (no transcript content is stored).

### 3.3 LLM

- Run `sirah-conversation ollama-stream-probe --live --context-limit 0/4/12`
  (four runs each). Record `first_event_ms`, `first_content_ms`, `total_ms`,
  `prompt_tokens`, `output_tokens` (already implemented, `ollama.py:77-128`).
- Repeat with `--think default / false / low`. Compare p50.
- Count repair/double proposals via `--lab` `diagnóstico:` lines
  (`propuesta descartada`) and the Spanish/identity repair path in
  `core.py:46-49`.
- With a local model, additionally test `keep_alive` residency: record
  `load_duration` differences between turns (probe response includes
  `load_duration`, `prompt_eval_duration`, `eval_duration`).

### 3.4 TTS

- `sirah-conversation tts-check --live --provider edge --lab` -> first PCM
  latency (`TTS edge: iniciando` -> `primer PCM listo`).
- Same for `--provider local` (Kokoro) and Azure. Compare.
- With the Edge connector-reuse experiment (M2 MEDIUM-RISK), compare first PCM
  on turn 2+ after one idle interval vs turn 1.

### 3.5 Playback

- `--lab` `Altavoz: iniciando` -> first audible sample. Sweep the output
  latency buffer `0.10 / 0.20 / 0.30` (needs the small parameter exposure in M2)
  and record underruns/clicks on the lab speaker and via BlueALSA on the Pi.

### 3.6 End-to-end

- `Fin de voz detectado` -> `Altavoz: iniciando` (first audio) and
  `Fin de voz -> Altavoz: reproducción terminada` (full turn). p50/p95/p99.
- Barge-in interrupt latency: `Ctrl-C`/voice interrupt -> silence.

## 4. Research summary (current techniques, verified)

- **Ollama** (`/api/chat`): streaming is the default; `stream:false` returns a
  single object; `keep_alive` controls model residency; `think` accepts
  `low/medium/high/max`; `options.num_predict` caps generation;
  `format:"json"`/schema enforces grammar **but Ollama Cloud does not support
  structured outputs** (docs + ollama/ollama#12362) and gpt-oss (both local and
  cloud) has known Harmony-channel/structured-output issues (ollama/ollama
  #11691). Response carries `load_duration`, `prompt_eval_count`,
  `prompt_eval_duration`, `eval_count`, `eval_duration` — usable to split
  prefill vs decode.
- **Groq STT**: `stream=True` is **not supported** on
  `/audio/transcriptions`; short-clip latency ~180-260 ms (2026 benchmarks);
  `wav` recommended for lower latency (already used); `language` improves
  latency/accuracy (already `es`); `x-groq-openai-usage-ms` header splits
  inference vs network; free tier 30 req/min with 429 needing retry.
- **edge-tts 7.2.8**: `Communicate(..., connector=aiohttp.BaseConnector)` is
  exposed — a shared aiohttp connector can be reused across syntheses to avoid
  a new WebSocket+TLS handshake per turn; `boundary="SentenceBoundary"`
  provides sentence metadata (offset/duration) enabling sentence-aware
  buffering; aiohttp is already a transitive dependency.
- **faster-whisper 1.2.1**: `vad_filter=True` + `vad_parameters` skips
  non-speech (the buffered end-silence/pre-roll region), `cpu_threads` /
  `num_workers` tune intra/inter-threading on CPU, `beam_size=1` already used,
  `language="es"` already set (no auto-detect).

## 5. Optimization candidates

Legend for RECOMMENDATION: KEEP (no change now), TEST (small, isolated,
measurable experiment), REJECT (not worth it).

### 5.1 VAD / endpointing

**C1 — Reduce `end_silence_ms`**
- CURRENT BOTTLENECK: every turn waits a fixed 700 ms of silence before closing.
- EVIDENCE: `continuous.py:223`; `ContinuousSessionConfig.end_silence_ms=700`.
- PROPOSED TECHNIQUE: sweep 500-650 ms; pick lowest value that does not clip.
- EXPECTED BENEFIT: 100-200 ms off every turn.
- HOW TO BENCHMARK: 3.1 sweep; transcript quality comparison.
- RELIABILITY RISK: clipped final words; slightly worse STT.
- COMPLEXITY: none (env var exists).
- RASPBERRY PI IMPACT: same relative gain.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

**C2 — Adaptive endpointing (speech-dependent silence)**
- CURRENT BOTTLENECK: fixed silence regardless of utterance length/cadence.
- PROPOSED TECHNIQUE: scale `end_silence_ms` with speech duration (e.g., longer
  turns allow longer silence; short commands close faster).
- EXPECTED BENEFIT: removes fixed wait on short turns.
- HOW TO BENCHMARK: 3.1 sweep with a recorded set of short/long utterances.
- RELIABILITY RISK: false closures on pauses mid-thought; recovery already
  bounded but extra recoveries would be user-visible.
- COMPLEXITY: medium (VAD policy logic).
- RASPBERRY PI IMPACT: none beyond tuning.
- CONTRACT IMPACT: none.
- RECOMMENDATION: EXPERIMENTAL.

**C3 — Semantic/turn endpointing via LLM**
- REJECTED: puts an LLM call on the hot path before speech is even complete;
  adds latency/cost/risk without proof; partial transcripts (C14) would be a
  prerequisite and are themselves experimental.
- RECOMMENDATION: REJECT.

**C4 — Reduce post-playback guard**
- CURRENT BOTTLENECK: `_guard_until = now + 500 ms` blocks VAD and drops early
  speech right after playback (`continuous.py:270`, `continuous.py:187-189`).
- PROPOSED TECHNIQUE: lower default to 200-350 ms; confirm no self-trigger on
  the final speaker.
- EXPECTED BENEFIT: faster next-turn responsiveness (does not shorten the
  current turn).
- HOW TO BENCHMARK: 3.1 guard sweep.
- RELIABILITY RISK: SIRAH's own trailing audio could open a spurious turn
  (no AEC); keep a floor.
- COMPLEXITY: none (env var exists).
- RASPBERRY PI IMPACT: none.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

### 5.2 STT

**C5 — Groq connection reuse**
- CURRENT BOTTLENECK: `urllib.request.urlopen` opens a fresh TCP+TLS connection
  per turn (`groq_stt.py:102-108`).
- PROPOSED TECHNIQUE: persistent HTTP client (stdlib `http.client` keep-alive
  or a shared `httpx.AsyncClient`) with graceful retry on stale connections.
- EXPECTED BENEFIT: ~30-100 ms/turn, more on high-RTT links.
- HOW TO BENCHMARK: 3.2 Groq marker; also split via `x-groq-openai-usage-ms`.
- RELIABILITY RISK: server may close idle keep-alives; must fall back to a new
  connection. Do not weaken the existing timeout/error contract
  (`ConversationTimeout`/`RemoteError` paths).
- COMPLEXITY: medium (new transport).
- RASPBERRY PI IMPACT: neutral (network bound).
- CONTRACT IMPACT: none (protocol unchanged; transport internal).
- RECOMMENDATION: TEST.

**C6 — Faster-Whisper local tuning**
- CURRENT BOTTLENECK: on Pi 4, local base int8 transcribes short turns in
  ~1-3 s and is the largest local-path risk.
- PROPOSED TECHNIQUE: `vad_filter=True` aligned with SIRAH's VAD region
  (drops buffered silence), `cpu_threads` set to Pi's 4 cores, optional
  `tiny` model A/B.
- EXPECTED BENEFIT: 20-40% faster local STT.
- HOW TO BENCHMARK: 3.2 local marker on Pi.
- RELIABILITY RISK: `vad_filter` parameters must match SIRAH's segmentation or
  early words could be dropped; `tiny` lowers accuracy.
- COMPLEXITY: low-medium.
- RASPBERRY PI IMPACT: direct win if it holds.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

**C7 — Partial/early STT (pseudo-streaming)**
- PROPOSED TECHNIQUE: re-POST trailing audio to Groq batch every ~700 ms for a
  partial transcript preview (pattern seen in fono's `groq_streaming.rs`), or
  run local Whisper on trailing audio before `end_silence` elapses.
- EXPECTED BENEFIT: hides some of the fixed `end_silence` wait; enables
  "speaking while user finishes".
- RELIABILITY RISK: extra API cost + rate-limit pressure (30 req/min free
  tier), partial texts that must never reach the LLM until validated, in-flight
  ordering hazards, cancellation interplay.
- COMPLEXITY: high.
- RASPBERRY PI IMPACT: CPU contention between preview Whisper and other stages.
- CONTRACT IMPACT: none, provided partial text is never sent to the proposer.
- RECOMMENDATION: EXPERIMENTAL (only after C1/C5 land and the remaining budget
  is measured).

### 5.3 LLM

**C8 — Persistent HTTP / keep-alive for Ollama**
- CURRENT BOTTLENECK: `_post`/`_stream` create a new connection per request
  (`ollama.py:363-382`); ~30-100 ms on cloud RTT.
- PROPOSED TECHNIQUE: same shared persistent transport as C5.
- EXPECTED BENEFIT: one RTT saved per turn (and per repair proposal).
- HOW TO BENCHMARK: 3.3 probe before/after.
- RELIABILITY RISK: keep-alive staleness; must preserve budget/single-flight/
  timeout semantics.
- COMPLEXITY: medium (shared transport abstraction).
- RASPBERRY PI IMPACT: neutral.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

**C9 — Reduce prompt/context size**
- CURRENT BOTTLENECK: system prompt is ~600-700 tokens prefilled on every
  request; `context_limit=12` recent turns ride along
  (`ollama.py:320-343`, `core.py:34`).
- PROPOSED TECHNIQUE: trim system prompt to essential identity + JSON contract;
  verify `prompt_tokens` via probe; consider smaller `context_limit`.
- EXPECTED BENEFIT: faster prefill -> faster TTFT, especially on cloud.
- HOW TO BENCHMARK: probe `prompt_tokens` and `first_content_ms` across
  prompt variants.
- RELIABILITY RISK: over-trimming degrades Spanish/identity/repair behavior;
  keep the closed JSON contract untouched.
- COMPLEXITY: low-medium.
- RASPBERRY PI IMPACT: larger for local models (prefill is CPU-bound).
- CONTRACT IMPACT: none (validation unchanged; prompt wording only).
- RECOMMENDATION: TEST.

**C10 — Reduce repair/double-proposal frequency**
- CURRENT BOTTLENECK: a failed Spanish/identity check triggers a second full
  LLM round-trip (`core.py:46-49`) — 2x LLM latency on those turns.
- PROPOSED TECHNIQUE: harden the single prompt against failures (explicit
  Harmony "Valid channels: final" note for gpt-oss, tighter JSON instructions);
  measure repair rate before/after.
- EXPECTED BENEFIT: removes the worst-case double round-trip on a fraction of
  turns.
- HOW TO BENCHMARK: count `diagnóstico:` rejections and double proposes under
  `--lab` across 30 turns.
- RELIABILITY RISK: none if validation/fallback paths stay intact.
- COMPLEXITY: low.
- RASPBERRY PI IMPACT: neutral.
- CONTRACT IMPACT: none (validator untouched; prompt only).
- RECOMMENDATION: TEST.

**C11 — `format:"json"` for Ollama structured output**
- CURRENT BOTTLENECK: JSON validity depends on prompt discipline; malformed
  output needs tolerant extraction + possible repair (`ollama.py:164-199`).
- PROPOSED TECHNIQUE: set `format:"json"` (local models only).
- EXPECTED BENEFIT: guaranteed-valid JSON; fewer repairs; simpler parse.
- HOW TO BENCHMARK: probe `format` on/off; measure repair rate.
- RELIABILITY RISK: **Ollama Cloud does not enforce structured outputs and
  silently degrades**; gpt-oss (local and cloud) has Harmony-channel
  structured-output failures. Must be gated to local GGUF models and A/B
  validated before any default.
- COMPLEXITY: low.
- RASPBERRY PI IMPACT: local models only.
- CONTRACT IMPACT: validator contract unchanged; strictly additive.
- RECOMMENDATION: TEST (local models only, explicitly gated).

**C12 — `num_predict` cap + `keep_alive`**
- CURRENT BOTTLENECK: response length is unbounded (`num_predict=-1` up to
  8x ctx) and local model may unload between turns.
- PROPOSED TECHNIQUE: `options.num_predict ~ 128` (1-2 sentences) and
  `keep_alive` (long residency for local, `-1` for a session-local model).
- EXPECTED BENEFIT: generation always stops promptly; local second-turn TTFT
  drops by `load_duration`.
- HOW TO BENCHMARK: probe `eval_count`/`eval_duration` and turn-2 probe.
- RELIABILITY RISK: `num_predict` too low could truncate longer replies; keep
  the silent/CLARIFY fallback intact.
- COMPLEXITY: low.
- RASPBERRY PI IMPACT: keep_alive pins RAM for a local model — verify within
  8 GB budget.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

**C13 — LLM streaming (measure first, then pipeline)**
- CURRENT BOTTLENECK: non-streaming waits for the full response; TTFT may be
  much shorter than total (probe will confirm).
- PROPOSED TECHNIQUE: use `stream:true` in two steps: (1) measure TTFT vs
  total; (2) only if content arrives well before the full response, feed
  **already-validated** full JSON to TTS per-sentence so TTS overlaps the next
  sentence's generation. Never speak unvalidated streamed output.
- EXPECTED BENEFIT: perceived response drops toward first-content time.
- HOW TO BENCHMARK: 3.3 probe; then 3.6 E2E.
- RELIABILITY RISK: cancellation/generation semantics must be preserved;
  sentence splitter must not break prosody or barge-in; repair must still be
  possible pre-playback (validate the whole proposal before any speech).
- COMPLEXITY: high.
- RASPBERRY PI IMPACT: CPU contention between generation and playback (same
  process) — measure.
- CONTRACT IMPACT: strict validator still gates every utterance.
- RECOMMENDATION: EXPERIMENTAL, gated on probe results (this is the phase-1
  decision gate the docs already describe).

**C14 — LLM response caching**
- REJECTED: conversations should vary; caching breaks natural turn-to-turn
  variety and touches privacy (transcripts). TTS phrase caching (C18) is the
  safe form of caching.
- RECOMMENDATION: REJECT.

### 5.4 TTS

**C15 — Edge connector reuse**
- CURRENT BOTTLENECK: every synthesis opens a new WebSocket+TLS handshake
  (`edge_tts.py:67-75`).
- PROPOSED TECHNIQUE: pass a shared `aiohttp.TCPConnector` to
  `Communicate(..., connector=...)` (available in edge-tts 7.2.8); prewarm at
  startup; keep `FallbackTTS` and the streaming ffmpeg decode intact.
- EXPECTED BENEFIT: 20-100 ms on first PCM per turn; fewer sockets.
- HOW TO BENCHMARK: 3.4 Edge first-PCM turn 1 vs turn 2+.
- RELIABILITY RISK: WebSocket reuse may not be honored by the service; stale
  connections must fall back cleanly. `FallbackTTS` already handles provider
  failure.
- COMPLEXITY: medium.
- RASPBERRY PI IMPACT: neutral.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

**C16 — Sentence-aware streaming (Edge boundaries)**
- PROPOSED TECHNIQUE: use `boundary="SentenceBoundary"` metadata to know when
  a sentence is complete, enabling the C13 sentence pipeline for TTS while the
  audio stream stays contiguous.
- EXPECTED BENEFIT: enables C13 cleanly without a custom sentence splitter.
- HOW TO BENCHMARK: 3.4/3.6.
- RELIABILITY RISK: boundary timings depend on the service; keep as a hint.
- COMPLEXITY: low (already in edge-tts).
- RECOMMENDATION: TEST (as enabler for C13).

**C17 — Kokoro startup/runtime on Pi**
- CURRENT BOTTLENECK: local Kokoro synthesis on Pi 4 CPU is the largest local
  TTS risk; `preload()` warms the model at startup
  (`kokoro_tts.py:53-55`; `cli/conversation.py:334-341`).
- PROPOSED TECHNIQUE: measure Pi Kokoro per-sentence generation; if too slow,
  keep Kokoro strictly as Edge fallback and prefer Edge as primary on Pi.
- HOW TO BENCHMARK: `tts-check --live --provider local --lab` on Pi.
- RELIABILITY RISK: none (measurement only).
- COMPLEXITY: none for measurement.
- RASPBERRY PI IMPACT: primary Pi concern.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST (measurement gate for provider choice).

**C18 — TTS common-phrase PCM cache**
- PROPOSED TECHNIQUE: bounded LRU of synthesized PCM keyed by (voice, text)
  for the deterministic local responses (name/time greeting, capability lines).
  Edge and Kokoro both emit 24 kHz mono, so cached PCM is portable.
- EXPECTED BENEFIT: skips TTS entirely for frequent fixed phrases.
- HOW TO BENCHMARK: measure TTS marker for a repeated greeting.
- RELIABILITY RISK: unbounded cache would eat Pi RAM; must be capped and
  cleared on provider change.
- COMPLEXITY: medium.
- RASPBERRY PI IMPACT: RAM-bounded; cap carefully.
- CONTRACT IMPACT: none.
- RECOMMENDATION: EXPERIMENTAL.

### 5.5 Playback

**C19 — Reduce output latency buffer**
- CURRENT BOTTLENECK: `latency=0.3` in `_open_output_stream`
  (`playback.py:302`) delays first audible audio by up to 300 ms.
- PROPOSED TECHNIQUE: expose an env knob and sweep `0.10/0.20/0.30`; keep the
  highest value with no underruns.
- HOW TO BENCHMARK: 3.5 sweep on lab speaker and BlueALSA.
- RELIABILITY RISK: lower buffer -> underruns/clicks on Pi or Bluetooth.
- COMPLEXITY: low (small config exposure).
- RASPBERRY PI IMPACT: risk is highest on Pi/Bluetooth; verify.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

### 5.6 Pipeline / cross-cutting

**C20 — Prewarm all cloud connections at startup**
- PROPOSED TECHNIQUE: open the Ollama/Groq/Edge transports during
  `--listen` startup so the first turn avoids cold handshakes.
- EXPECTED BENEFIT: removes first-turn setup; pairs with C5/C8/C15.
- HOW TO BENCHMARK: first-turn 3.6 measurement.
- RELIABILITY RISK: startup failure must degrade gracefully (not crash).
- COMPLEXITY: low.
- RASPBERRY PI IMPACT: neutral.
- CONTRACT IMPACT: none.
- RECOMMENDATION: TEST.

**C21 — HTTP/2**
- REJECTED: marginal latency gain for these payloads; requires extra
  dependencies (`h2`) and complicates the transport; no evidence it beats
  keep-alive HTTP/1.1 here.
- RECOMMENDATION: REJECT.

**C22 — Overlapping stages (STT->LLM->TTS fusion)**
- Only viable after C13 measures TTFT vs total and after C1/C5 shrink the
  pre-LLM stages. Treated as the M2 capstone, not a Phase-1 change.
- RECOMMENDATION: EXPERIMENTAL (depends on C13 gate).

## 6. Classification

### QUICK WINS (tuning/config, low risk)
- C1 `end_silence_ms` sweep
- C4 post-playback guard sweep
- C9 prompt/context trim (measure prompt_tokens)
- C10 prompt hardening to cut repair rate
- C12 `num_predict` cap + `keep_alive` (local)
- C17 Kokoro-on-Pi measurement gate
- C19 playback latency sweep (small knob exposure)

### MEDIUM-RISK (code changes, gated by regression + measurement)
- C5 Groq connection reuse
- C8 Ollama persistent transport (shared with C5)
- C15 Edge connector reuse
- C6 Faster-Whisper local tuning
- C11 `format:"json"` for local models only
- C16 SentenceBoundary enabler
- C20 startup prewarm

### EXPERIMENTAL
- C2 adaptive endpointing
- C7 partial/early STT (pseudo-stream)
- C13 LLM streaming -> TTS sentence pipelining (phase-1 gate first)
- C18 TTS phrase cache
- C22 stage overlap

### REJECTED
- C3 semantic/LLM endpointing
- C14 LLM response caching
- C21 HTTP/2

## 7. Prioritized M2 plan

Order respects "measure first, then change; never speak unvalidated output;
never weaken the JSON contract; never remove recovery."

1. **Phase 1 complete** — run sections 3.1-3.6 on the lab laptop; record the
   baseline table. Confirm `first_content_ms` vs `total_ms` and the repair
   frequency (this decides whether C13 is worth building).
2. **QW batch** — C1, C4, C19 sweeps (pure tuning, no production logic change);
   lock the best values into docs/config defaults.
3. **QW prompt work** — C9, C10, C12 with `--lab` A/B and probe metrics; keep
   validator untouched.
4. **MR transport batch** — C5, C8, C15, C20 (shared persistent transport +
   connector reuse + prewarm). Add regression coverage for connection
   staleness/fallback and cancellation; rerun contract + replay suites.
5. **MR local path** — C6, C11 (local-only `format`), C16 on the Pi 4; measure
   STT/TTS deltas.
6. **EXPERIMENTAL only if gates pass** — C13 sentence pipelining (validate full
   JSON first), then C18/C2/C7 as results justify.

Risks carried forward: Pi memory/CPU for local STT+TTS, no-AEC barge-in with
lowered guards, cloud structured-output non-enforcement, keep-alive staleness.
None of these justify deleting existing recovery, cancellation, or validation
behavior.

## 8. Deliverable summary

### BASELINE
- 413 pytest / 95 contract passing; ruff + mypy clean; branch
  `feature/conversation-performance`; no production code modified in Phase 1.
- Static E2E budget: ≈2.5-5 s (end_silence 700 ms + STT + non-streaming LLM +
  Edge first PCM + 300 ms playback buffer). Live p50/p95/p99 to be captured
  with the section 3 procedures.

### BOTTLENECK RANKING
1. LLM: non-streaming full-response wait + large prefill + double proposal on
   repair (~1-3 s; up to 2x).
2. TTS: Edge first-PCM (new WebSocket/TLS per turn) (~0.3-0.8 s).
3. Playback: 300 ms output buffer + device latency.
4. STT: Groq ~0.2-0.4 s; local base int8 on Pi 4 is the worst local risk
   (~1-3 s est.).
5. VAD: fixed 700 ms end_silence + post-playback guard 500 ms (latency to the
   current turn and to the next turn, respectively).
6. Serial connection handshakes across Groq/Ollama/Edge (~0.1-0.3 s aggregate).

### QUICK WINS
C1 end_silence sweep, C4 guard sweep, C9 prompt trim, C10 repair-rate cut,
C12 num_predict/keep_alive, C17 Pi Kokoro gate, C19 playback buffer sweep.

### EXPERIMENTS
C13 streaming->sentence pipelining (after gate), C18 phrase cache,
C7 pseudo-stream STT, C2 adaptive endpointing, C22 stage overlap.

### REJECTED IDEAS
C3 LLM semantic endpointing, C14 LLM caching, C21 HTTP/2, Groq `stream=True`,
cloud `format:json` enforcement, speaking unvalidated streamed output.

### RECOMMENDED FIRST IMPLEMENTATION
Complete the Phase-1 measurement procedures (sections 3.1-3.6) on the lab
laptop to capture the real p50/p95/p99 and confirm `first_content_ms` vs
`total_ms`; then apply the QUICK-WINS batch (C1, C4, C19) and re-measure;
proceed to the transport batch (C5, C8, C15) only after those numbers are
recorded. The LLM streaming->TTS pipeline (C13) is built only if the probe
shows first-content arrives well before the full response.