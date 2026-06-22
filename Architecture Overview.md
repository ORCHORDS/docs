> Auto-generated from `engineering/ARCHITECTURE_OVERVIEW.md` in the docs repo.

> Auto-generated from `docs/engineering/ARCHITECTURE_OVERVIEW.md` in the docs repo.

---
title: "Architecture Overview"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Architecture Overview

**Project:** Beetle Studio  
**Owner:** Kirk Beka (CTO) — system design; Mooned Dev — engine architecture  
**Reviewers:** All engineering leads  
**ISO Standards:** ISO/IEC 12207:2017 (system design), ISO/IEC 25010:2023 (compatibility, maintainability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | High-level system architecture, module boundaries, data flow |
| **Diátaxis form** | Explanation |
| **Primary audience** | All engineers, Kirk Beka, Mooned Dev, new hires |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes the high-level system architecture of Beetle Studio. Per **ISO/IEC 12207:2017 section 6.1.3**, the software design process must produce a system architecture that satisfies system requirements while supporting maintainability and evolvability -- both central to **ISO/IEC 25010:2023**.
## Contents

- [Module Architecture](#module-architecture)
- [Core Modules](#core-modules)
  - [Engine — Rendering (`BeetleEngine`)](#engine-rendering-beetleengine)
  - [Engine — Codec (`BeetleCodec`)](#engine-codec-beetlecodec)
  - [Engine — Effects (`BeetleEffects`)](#engine-effects-beetleeffects)
  - [Audio Engine (`BeetleAudio`)](#audio-engine-beetleaudio)
- [Key Abstractions](#key-abstractions)
  - [Frame Buffer Abstraction](#frame-buffer-abstraction)
  - [Timeline Data Model](#timeline-data-model)
- [Data Flow](#data-flow)
- [Cross-Platform Strategy](#cross-platform-strategy)
- [Platform Abstraction](#platform-abstraction)
- [Dependency Constraints](#dependency-constraints)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Module Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           BEETLE STUDIO                                 │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                         UI LAYER (Qt6)                          │    │
│  │  MainWindow │ TimelinePanel │ EffectsPanel │ PreviewViewport    │    │
│  │  ProjectBrowser │ AudioMixer │ ExportDialog │ PropertiesPanel   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      APPLICATION LAYER                         │    │
│  │  ProjectManager │ UndoSystem │ SelectionManager │ ShortcutMgr  │    │
│  │  PluginHost │ SettingsManager │ ExportQueue │ ClipboardManager │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                    │
│       ┌────────────────────────────┼────────────────────────────┐       │
│       │                            │                            │       │
│       ▼                            ▼                            ▼       │
│  ┌──────────┐              ┌──────────┐               ┌──────────┐     │
│  │  ENGINE  │              │  ENGINE  │               │  ENGINE  │     │
│  │          │              │          │               │          │     │
│  │  Render  │              │  Codec   │               │  Effects │     │
│  │  Pipeline│◄────────────►│  Pipeline│◄────────────►│  Pipeline│     │
│  │ (DX12/   │   frame      │ (FFmpeg) │  decoded      │ (GPU     │     │
│  │  Vulkan) │   buffer     │          │  frames       │  shaders)│     │
│  └──────────┘              └──────────┘               └──────────┘     │
│       │                                                        │        │
│       │                           ┌──────────┐                  │        │
│       │                           │  Audio   │                  │        │
│       │                           │  Engine  │◄─────────────────┘        │
│       │                           │ (VST/    │                           │
│       │                           │  WASAPI) │                           │
│       └───────────────────────────┴──────────┴───────────────────┘        │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      PLATFORM LAYER                              │    │
│  │  FileSystem │ ThreadPool │ MemoryManager │ PlatformDialogs      │    │
│  │  HIDInput │ NetworkMonitor │ CrashHandler                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    CLOUD LAYER (Firebase)                        │    │
│  │  AuthService │ SyncService │ StorageService │ LicenseService     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Modules

### Engine — Rendering (`BeetleEngine`)
**Owner:** Mooned Dev, James Park

The rendering engine sits at the heart of Beetle Studio. It manages the GPU pipeline, shader compilation, frame pacing, and the viewport compositor.

- **DX12 backend** — primary Windows rendering path
- **Vulkan backend** — cross-platform future path
- **Shader system** — HLSL for DX12, GLSL for Vulkan; shared shader IR via SPIRV-Cross where possible
- **Frame pacing** — locked to display refresh rate; triple buffering
- **Render graph** — dependency-ordered render passes with automatic resource management

### Engine — Codec (`BeetleCodec`)
**Owner:** Sophie Williams

Handles all video and audio decoding and encoding via FFmpeg.

- **Demuxing** — MP4, MOV, MKV, AVI, WebM and others
- **Software decoding** — H.264, HEVC, ProRes, AV1, VP9
- **Hardware decoding** — NVDEC (NVIDIA), QSV (Intel), VCN (AMD)
- **Hardware encoding** — NVENC, QSV, VCE
- **Audio decoding** — AAC, MP3, WAV, FLAC, OGG

### Engine — Effects (`BeetleEffects`)
**Owner:** Daniel Kim

GPU-accelerated visual effects and compositing.

- **Effect chain** — ordered list of effects applied per clip
- **Layer compositing** — blend modes, masks, mattes, track matte
- **Color pipeline** — color wheels, curves, LUT application, HDR
- **Plugin host** — OpenFX v1.4 compatibility layer

### Audio Engine (`BeetleAudio`)
**Owner:** Ryan Foster

Multi-track audio playback, mixing, and effects.

- **Audio units** — per-clip audio processing
- **Mixer** — volume, pan, bus routing, solo/mute
- **VST hosting** — VST2 and VST3 plugin compatibility
- **Output** — WASAPI (exclusive/shared) and ASIO
- **Sync** — A/V sync lock to video playhead

---

## Key Abstractions

### Frame Buffer Abstraction

All engines work through a common frame buffer interface:

```cpp
struct FrameBuffer {
    uint32_t width;
    uint32_t height;
    PixelFormat format;          // RGBA, YUV422, YUV420, etc.
    ColorSpace colorSpace;       // Rec.709, DCI-P3, Rec.2020
    uint64_t timestamp;          // Presentation timestamp in nanoseconds
    std::span<const uint8_t> data;
};
```

This allows the codec to output frames regardless of source format, and the render engine to consume them without format-specific logic.

### Timeline Data Model

See [`timeline/DATA_MODEL.md`](../timeline/DATA_MODEL.md) for the full data structure.

---

## Data Flow

```
Media File
    │
    ▼
┌──────────────────┐
│  FFmpeg (Codec)  │  → Decode frame
└────────┬─────────┘
         │ FrameBuffer (decoded)
         ▼
┌──────────────────┐
│  Color Pipeline  │  → Apply color space / LUT
└────────┬─────────┘
         │ FrameBuffer (color-managed)
         ▼
┌──────────────────┐
│  Effect Chain    │  → Apply effects (GPU shaders)
└────────┬─────────┘
         │ FrameBuffer (composited)
         ▼
┌──────────────────┐
│  Render Pipeline │  → DirectX 12 / Vulkan draw
└────────┬─────────┘
         │ Present
         ▼
   Preview Viewport
```

---

## Cross-Platform Strategy

| Layer | Windows | macOS | Linux |
|---|---|---|---|
| UI | Qt6 | Qt6 | Qt6 |
| Rendering | DX12 ✅ | Metal (future) | Vulkan (future) |
| Audio | WASAPI / ASIO | CoreAudio | ALSA / PipeWire |
| Codec | FFmpeg | FFmpeg | FFmpeg |
| Platform | Win32 | Cocoa | XDG |

Platform differences are isolated in the **Platform Layer** to minimize cross-platform changes in upper layers.

---

## Platform Abstraction

Key platform abstractions hide OS-specific implementation:

| Interface | Windows Implementation | Notes |
|---|---|---|
| `IFileSystem` | Win32 file APIs | Project files, media files |
| `IHIDInput` | Raw Input / XInput | Keyboard, mouse, gamepad |
| `IThreadPool` | Windows Thread Pool API | Engine worker threads |
| `IGPUContext` | DX12 device | Renderer ↔ GPU bridge |
| `INetworkMonitor` | WinNet APIs | Online/offline detection |

---

## Dependency Constraints

To keep modules clean and testable:

| Rule | Enforcement |
|---|---|
| UI layer cannot import Engine layer directly | Layered architecture enforced in CMake |
| Codec layer has no UI dependency | Pure data transformation |
| Effects layer works with FrameBuffer only | No external state |
| Cloud layer has no Engine dependency | Can be disabled/stubbed for offline builds |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial architecture — aligned with ISO/IEC 12207:2017 §6.1.3 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1.3 (Software Design), ISO/IEC 25010:2023 (Compatibility, Maintainability, Portability)*



---

## References

### Internal Documents

- [$title](./../timeline/DATA_MODEL.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Kirk Beka | Initial version |
| 1.0.1 | June 2026 | Kirk Beka | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On architecture change
- **Reviewer:** Kirk Beka (CTO) — system design
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type