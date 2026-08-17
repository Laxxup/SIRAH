# ADR-0013 — Telepresence and single camera ownership

Status: proposed (research track T0). Applies to: v0.3.x and the future
telepresence capability. Does not change current perception behavior.

## Context

SIRAH will eventually let a remote user open a browser/phone and see the
camera, hear SIRAH, optionally talk, watch perception state, and keep a
normal AI conversation — all while local autonomy (perception → evidence
→ WorldState → attention → behavior) keeps running.

The current runtime, `sirah-perceive`, `sirah-models` and future
telepresence/WebRTC/VLM code all consume camera frames. Without a
decision, every subsystem opens `/dev/video0` independently. That is
unacceptable: on a Raspberry Pi 4 a second V4L2 open can change capture
pacing, and N independent pipelines cannot be kept coherent or lifecycle
safe. It also makes "no frame backlog" impossible to guarantee.

Research reviewed Reachy Mini's media architecture (daemon-owned
`GstMediaServer`, local IPC vs remote WebRTC, capped local rate),
GStreamer `webrtcsink`/`tee`/`queue` semantics, aiortc's `MediaRelay`
webcam pattern, WebRTC ICE/STUN/TURN, Pi 4 H.264 hardware encoding
(`h264_v4l2m2m`/`v4l2h264enc`), browser codec support, WebRTC acoustic
echo cancellation and DTLS-SRTP/TURN security. Details and sources are in
the telepresence research report.

## Decision

1. **One camera owner.** The runtime owns the physical `CameraSource`.
   All in-process consumers obtain frames through `FrameBroker`
   (`src/sirah/perception/fanout.py`): each subscriber is a drop-in
   `CameraSource` with latest-frame semantics. Telepresence (WebRTC
   encoder input), perception (YuNet/MediaPipe/YOLO), VLM snapshots and
   the M4 preview all subscribe; nobody opens the camera.

2. **Freshness over throughput, always.** Each subscriber keeps exactly
   one latest-frame slot; a slow consumer drops intermediate frames
   rather than queuing them. This mirrors the proven live-camera
   behavior (`captured=226, consumed=100, dropped=125`) — the drops are
   correct. No unbounded queues, no backlog. (GStreamer equivalent:
   `appsink`/`queue` with `max-buffers` + `leaky=downstream`, as Reachy's
   `max-buffers=1, drop=True` video appsink shows.)

3. **Telepresence video and AI perception are separate pipelines fed by
   the same owner.** Remote video is camera → encode → WebRTC → browser.
   AI perception is camera → YuNet/MediaPipe/YOLO → EvidenceFilter →
   WorldState. The LLM never receives the continuous WebRTC stream; it
   consumes the compact fresh WorldState snapshot, and a VLM gets ONE
   latest fresh frame only on demand.

4. **Transport is swappable and optional.** The WebRTC transport (aiortc
   for a LAN MVP, GStreamer `webrtcsink` + `v4l2h264enc` if the Pi 4
   benchmark demands hardware encoding) is behind the same subscriber
   interface. WebRTC failure degrades telepresence only; perception,
   conversation and behavior survive. Remote media = VIEW, never CONTROL
   (VIEW vs CONTROL vs ADMIN are separate permissions).

## Camera ownership options considered

| Option | Verdict |
|---|---|
| A. Shared in-process frame broker (chosen) | One process owns the camera; all consumers in-process; zero new deps; testable with fakes; preserves latest-frame semantics. |
| B. Dedicated media daemon | More isolation but a new process + IPC for a single camera; matches Reachy's daemon only when SIRAH splits processes. Revisit if the WebRTC/GStreamer leg grows. |
| C. GStreamer owns camera with tee/appsink | Strong for the media leg (hardware H.264, webrtcsink) but pulls GStreamer into the critical perception path and fights SIRAH's pure-asyncio core. |
| D. aiortc relay | This is the *transport*, not the owner; `MediaRelay` shares the source track but encodes per peer. Doesn't solve who reads the camera. |

## Consequences

- Perception, gesture and telepresence can run at independent rates from
  one capture device; a slow consumer never delays another.
- No frame ever accumulates; memory is bounded per subscriber.
- The foundational refactor is small, committed and regression-tested
  (`test_fanout.py`), and needs no new dependencies.
- WebRTC/audio/VLM work stays optional behind extras; nothing merges
  into the runtime architecture until benchmarks justify it.

## Open questions (deferred to T-track)

- aiortc vs GStreamer `webrtcsink` for the remote leg (decide at T3/T6
  after a LAN video-only prototype and a Pi 4 encoding benchmark).
- Audio full-duplex/echo strategy (T8/T9): video-only telepresence ships
  before bidirectional audio.
- Signaling + auth (T7): LAN MVP documents trust; Internet requires
  authenticated signaling, DTLS-SRTP (default), ephemeral TURN
  credentials, VIEW≠CONTROL.
