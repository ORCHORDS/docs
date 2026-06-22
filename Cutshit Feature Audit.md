> Auto-generated from `Cutshit Feature Audit.md` in the docs repo.

> Auto-generated from `docs/product/CUTSHIT_FEATURE_AUDIT.md` in the docs repo.

---
title: "CutShit v2.0 Feature Audit — Beetle Studio V1 Gap Analysis"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# CutShit v2.0 Feature Audit — Beetle Studio V1 Gap Analysis

Audited from cutshit.net on 2026-06-20.

## CutShit Feature Set (Complete)

| # | Feature | Description |
|---|---------|-------------|
| 1 | Frame-accurate trim | Cut on exact frame, magnetic snapping, multi-clip on one track |
| 2 | Multi-track timeline | 4K, no length cap, no resolution cap, proxy previews, smooth scrubbing |
| 3 | One-click export | YouTube, TikTok, Shorts, Reels presets baked in |
| 4 | Hardware encode | NVENC / QSV / AMF on by default |
| 5 | Live Studio (NEW v2.0) | OBS-parity streaming: scenes, sources (camera, display, image, text, browser), transitions, chroma key, color correction, audio mixer, OBS scene collection import |
| 6 | Auto-captions | Local Whisper transcription, 40+ caption styles, per-word highlighting, no cloud |
| 7 | Screen + webcam recording | PiP overlays, drag-to-resize, drop-shadow, rounded masks, no external app |
| 8 | Voice-over & noise | Push-to-talk recording, AI noise reduction, auto loudness to -14 LUFS |
| 9 | Royalty-free BGM | 200+ tracks sorted by mood, auto-duck under speech, no strikes |
| 10 | Node fleet | Rent idle GPU, earn render credits, distributed exports, peer network |
| 11 | 100% local-first | No cloud uploads, AI on-device, no account needed to edit |
| 12 | No watermark | Free or paid, never any watermark |
| 13 | Android app | Mobile editing via Google Play (early access) |
| 14 | Offline mode | Works completely offline |
| 15 | One-time pricing | $49.99 lifetime, no subscription |

---

## Beetle Studio V1 — What We Already Have

| Feature | Status | Notes |
|---------|--------|-------|
| Panel system (Timeline, Preview, Properties, Console, Audio, Effects, Color) | UI drawn | Win32 GDI panels exist but are non-functional (hardcoded drawing) |
| Effects list (8 effects) | UI drawn | Visual only — no processing pipeline behind it |
| Audio channels (5 channels) | UI drawn | Visual only — no audio engine |
| GPU detection (DXGI) | Working | Detects GPU at startup |
| Firebase Auth (Google sign-in) | Backend ready | Auth provider configured, not wired to UI |
| Firestore token system | Backend ready | Database + security rules deployed, not wired |
| DX12 + Vulkan renderers | Headers created | Bot-generated .h/.cpp files exist, not compiled/integrated |
| FFmpeg codec pipeline | Headers created | Bot-generated, not integrated |
| Timeline engine | Headers created | Bot-generated, not integrated |
| Audio engine + VST host | Headers created | Bot-generated, not integrated |
| OpenFX plugin host | Headers created | Bot-generated, not integrated |
| Marketing website (public/index.html) | Exists | Basic landing page |
| CI/CD workflows | Exists | Forgejo Actions (PR-triggered) |
| Build system (CMakeLists.txt) | Exists | Basic cmake config |

---

## What We Need to Add for V1 (from CutShit audit)

### PRIORITY 1 — Core editing (must-have to compete)

| Feature | CutShit Has | Beetle Studio Status | Work Needed |
|---------|-------------|---------------------|-------------|
| Frame-accurate trimming | Yes | Fake UI only | Wire timeline clicks to real clip trim logic in main.cpp |
| Magnetic snapping | Yes | No | Add snap-to-edge logic in timeline mouse handling |
| Multi-track timeline | Yes | Single-track drawing | Extend g_panels timeline to support N tracks with clip objects |
| 4K timeline + proxy previews | Yes | No | Add proxy generation on import, resolution-independent timeline |
| Smooth scrubbing | Yes | No | Implement frame-seeking with decode cache |
| One-click export presets | Yes | No | Add export dialog with YouTube/TikTok/Shorts/Reels presets |
| Hardware encode (NVENC/QSV/AMF) | Yes | Headers only | Integrate FFmpeg with hardware encoder detection and selection |

### PRIORITY 2 — AI & capture (differentiator features)

| Feature | CutShit Has | Beetle Studio Status | Work Needed |
|---------|-------------|---------------------|-------------|
| Auto-captions (local Whisper) | Yes — 40+ styles, per-word highlighting | No | Integrate TranscriberPipeline.py (Demucs + Whisper + chapters + JSONL), add caption track type, style editor |
| AI noise reduction | Yes | No | Integrate RNNoise or similar, add to audio pipeline |
| Voice-over recording | Yes — push-to-talk, -14 LUFS auto-loudness | No | Add WASAPI recording, loudness normalization |
| Screen recording | Yes — with webcam PiP | No | Add DXGI Desktop Duplication capture |
| Webcam capture + PiP | Yes — drag-to-resize, drop-shadow, rounded masks | No | Add DirectShow/MediaFoundation webcam, PiP compositor |

### PRIORITY 3 — Audio & media

| Feature | CutShit Has | Beetle Studio Status | Work Needed |
|---------|-------------|---------------------|-------------|
| Royalty-free BGM library | Yes — 200+ tracks, mood-sorted | No | Bundle or stream a BGM library, add browse/preview UI |
| Auto-duck under speech | Yes | No | Implement sidechain-style volume automation |
| Audio mixer | Yes (in Live Studio) | Fake UI | Wire audio channel faders to real mixing engine |

### PRIORITY 4 — Live streaming (v2 differentiator, consider for V1)

| Feature | CutShit Has | Beetle Studio Status | Work Needed |
|---------|-------------|---------------------|-------------|
| Live Studio (OBS-parity) | Yes — scenes, sources, transitions, chroma key | No | Major feature — RTMP/SRT output, scene compositor, source manager |
| OBS scene import | Yes | No | Parse OBS JSON scene collections |
| Stream to Twitch/YouTube/Kick | Yes | No | RTMP push with stream key management |
| Chroma key | Yes | No | GPU-based chroma key shader |

### PRIORITY 5 — Platform & distribution

| Feature | CutShit Has | Beetle Studio Status | Work Needed |
|---------|-------------|---------------------|-------------|
| Node fleet (GPU rental) | Yes — distributed renders | No | P2P render distribution — major infrastructure |
| Android app | Yes (Google Play) | No | Separate Android project (not V1) |
| 100% offline mode | Yes | Partially (Firebase needs internet) | Add offline-first with sync-when-connected |
| No account needed to edit | Yes | No (Firebase auth required) | Allow anonymous local editing, auth only for cloud/tokens |

---

## V1 Action Items (Recommended)

Based on this audit, these are the features Beetle Studio MUST ship in V1 to be competitive with CutShit:

1. **Real frame-accurate timeline editing** — trim, split, magnetic snap, multi-track
2. **Hardware-accelerated export** — NVENC/QSV/AMF with platform presets (YouTube, TikTok, Shorts, Reels)
3. **Local AI captions** — transcriber pipeline integration (v1.3.0: chapter detection, JSONL streaming, diarization), styled caption overlays
4. **Audio engine** — real mixer, voice-over recording, noise reduction
5. **Screen + webcam capture** — DXGI duplication + DirectShow, PiP compositing
6. **No watermark policy** — already planned
7. **Offline editing without account** — let users edit locally, auth only for premium/cloud
8. **One-time pricing model** — already planned via token system, consider $49.99 lifetime tier

### Nice-to-have for V1 (stretch):
- Royalty-free BGM library with auto-duck
- Live streaming studio (OBS-parity)
- Chroma key in effects pipeline

### Post-V1:
- Node fleet / distributed rendering
- Android app
- OBS scene import
