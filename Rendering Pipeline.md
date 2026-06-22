> Auto-generated from `graphics/RENDERING_PIPELINE.md` in the docs repo.

> Auto-generated from `docs/graphics/RENDERING_PIPELINE.md` in the docs repo.

---
title: "Rendering Pipeline"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Rendering Pipeline

**Project:** Beetle Studio  
**Owner:** James Park (Graphics Engineer) — with Mooned Dev (CEO) on core architecture  
**Reviewers:** Mooned Dev, Daniel Kim (Effects), Sophie Williams (Codec)  
**ISO Standards:** ISO/IEC 12207:2017 (development), ISO/IEC 25010:2023 (functional suitability, performance efficiency)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | DX12/Vulkan render graph and shader pipeline overview |
| **Diátaxis form** | Explanation |
| **Primary audience** | James Park, Mooned Dev, Daniel Kim, Sophie Williams |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes the Beetle Studio rendering pipeline. Per **ISO/IEC 12207:2017**, the software design must define internal interfaces between subsystems. The rendering pipeline is the interface between the codec output (decoded frames) and the preview viewport. It must satisfy **ISO/IEC 25010:2023**'s performance efficiency requirements.
## Contents

- [Pipeline Architecture](#pipeline-architecture)
- [Render Graph](#render-graph)
  - [Pass Types](#pass-types)
- [DirectX 12 Backend](#directx-12-backend)
  - [Device Setup](#device-setup)
  - [Frame Presentation](#frame-presentation)
  - [Memory Management](#memory-management)
- [Shader System](#shader-system)
  - [HLSL Shader Compilation](#hlsl-shader-compilation)
  - [Key Shaders](#key-shaders)
- [Color Management](#color-management)
  - [Supported Color Spaces](#supported-color-spaces)
  - [LUT Support](#lut-support)
- [Frame Pacing](#frame-pacing)
- [Performance Targets](#performance-targets)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      RENDERING PIPELINE                          │
│                                                                  │
│  Decoded Frame ──► Color Pipeline ──► Effect Chain ──► Compositor │
│  (FrameBuffer)      (LUT, HDR)      (GPU shaders)        │
│       │                                  │                   │
│       │                                  ▼                   │
│       │                          ┌──────────────┐            │
│       │                          │  Render      │            │
│       │                          │  Graph       │            │
│       │                          │  (DX12/      │            │
│       │                          │   Vulkan)    │            │
│       │                          └──────┬───────┘            │
│       │                                 │                     │
│       │                                 ▼                     │
│       │                          ┌──────────────┐            │
│       └─────────────────────────►│  Viewport     │            │
│                                  │  Compositor   │            │
│                                  └──────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

---

## Render Graph

Beetle Studio uses a **render graph** to manage GPU resources and dependencies. The graph:

- **Nodes** = render passes (color correction, effects, UI overlay, viewport)
- **Edges** = data dependencies (pass A outputs → pass B inputs)
- **Automatic resource management** = render targets allocated on demand, freed when no longer needed

### Pass Types

| Pass | Input | Output | Notes |
|---|---|---|---|
| **ColorCorrection** | Decoded frame | Color-managed frame | Applies LUT, color space conversion |
| **EffectChain** | Previous pass output | Composite frame | Each effect is a sub-pass |
| **ViewportComposite** | Timeline composite | Final frame | Adds safe-area guides, rulers |
| **UIRender** | Qt6 surface tree | UI texture (R8G8B8A8_UNorm or B8G8R8A8_UNorm) | Qt6 `QQuickRenderControl` renders the widget tree into an offscreen `VkImage` / `ID3D12Resource`. UIRender is a sub-pass of `Present`: the UI texture is composited on top of the timeline frame in a fullscreen triangle. This keeps Qt's hit-testing and accessibility model intact while letting the renderer own the final composite. DPI scale = `DPI / 96`, capped at 2.0x. |
| **Present** | Composite | Screen | Frame pacing + vsync |

---

## DirectX 12 Backend

### Device Setup

- **D3D12 device** — direct to primary GPU (enumerate adapters, pick highest-performance discrete GPU)
- **Command queue** — 3 separate queues: Graphics, Compute, Copy
- **Descriptor heap** — CBV/SRV/UAV and sampler heaps pre-allocated
- **Fence** — frame synchronization with CPU

### Frame Presentation

```
Wait for previous frame fence
CPU records commands
Submit command list
Signal current frame fence
Present
```

### Memory Management

- **Upload heap** — staging buffers for texture uploads (short-lived)
- **Default heap** — GPU-resident textures (persistent)
- **Readback heap** — GPU → CPU transfers (for exports)
- **Video memory budget** — detect available VRAM; warn if > 85% utilized

---

## Shader System

### HLSL Shader Compilation

- **DXC compiler** — compile HLSL → DXIL at build time
- **Runtime reflection** — load shader metadata at runtime for UI (exposure, range)
- **Hot reload** — during development, reload shaders without restarting app

### Key Shaders

| Shader | Purpose | Inputs |
|---|---|---|
| `ColorCorrection.hlsl` | Color wheels, curves, LUT | frame, lut_texture, parameters |
| `Blur.hlsl` | Gaussian blur (separable) | frame, kernel_size, direction |
| `Sharpen.hlsl` | Unsharp mask sharpening | frame, amount |
| `Warp.hlsl` | Lens distortion correction | frame, distortion_params |
| `Composite.hlsl` | Blend two layers | layer_a, layer_b, blend_mode |
| `ChromaKey.hlsl` | Green screen / blue screen | frame, key_color, tolerance |
| `Output.hlsl` | Color space → output display | frame, output_colorspace |

---

## Color Management

Per **ISO/IEC 25010:2023**, functional suitability includes correct color representation.

### Supported Color Spaces

| Color Space | Use Case | Bit Depth |
|---|---|---|
| **sRGB / Rec.709** | Standard SDR content | 8-bit |
| **DCI-P3** | Wide-gamut displays | 10-bit |
| **Rec.2020 / BT.2020** | HDR content | 10/12-bit |
| **ACES** | Professional color workflow | Floating point |

### LUT Support

- `.cube` LUT files (Adobe, DaVinci Resolve compatible)
- 1D and 3D LUT formats
- Applied before effect chain

---

## Frame Pacing

- **Target refresh rate** — query display via DXGI, lock to 60 Hz or higher
- **Triple buffering** — prevent stutter during GPU-bound scenarios
- **Latency mode** — `DXGI_PRESENT_ALLOW_TEARING` for minimum input lag
- **Benchmark** — < 16.67 ms frame time for 60 FPS (performance target)

---

## Performance Targets

| Metric | Target | Measured By |
|---|---|---|
| Preview FPS (1080p, 5 effects) | ≥ 60 FPS | RenderDoc / PIX |
| Preview FPS (4K, 3 effects) | ≥ 30 FPS | RenderDoc / PIX |
| Frame latency (decode → preview) | < 33 ms | Custom instrumentation |
| GPU memory (4K project, idle) | < 500 MB | DX12 memory budget API |
| Shader compile time (cold start) | < 2 s | Build log |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 12207:2017 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1.3 (Design), ISO/IEC 25010:2023 (Performance Efficiency, Functional Suitability)*



---

## References

### Internal Documents

_No internal documents referenced._

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | James Park | Initial version |
| 1.0.1 | June 2026 | James Park | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On rendering architecture change
- **Reviewer:** James Park (Graphics Engineer) — with Mooned Dev (CEO) on core architecture
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type