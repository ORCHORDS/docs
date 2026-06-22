> Auto-generated from `Vst Sdk Integration.md` in the docs repo.

> Auto-generated from `Vst Sdk Integration.md` in the docs repo.

> Auto-generated from `Vst Sdk Integration.md` in the docs repo.

> Auto-generated from `Vst Sdk Integration.md` in the docs repo.

> Auto-generated from `Vst Sdk Integration.md` in the docs repo.

> Auto-generated from `docs/audio/VST_SDK_INTEGRATION.md` in the docs repo.

---
title: "VST SDK Integration"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# VST SDK Integration

**Project:** Beetle Studio  
**Owner:** Ryan Foster (Audio Systems Engineer)  
**Reviewers:** Kirk Beka (CTO), Daniel Kim (Effects)  
**ISO Standards:** ISO/IEC 12207:2017 (development), ISO/IEC 25010:2023 (functional suitability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | VST hosting, delay compensation, and audio sync |
| **Diátaxis form** | Reference |
| **Primary audience** | Ryan Foster, Kirk Beka, Daniel Kim |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes how Beetle Studio integrates VST (Virtual Studio Technology) plugins for audio effects processing. Per **ISO/IEC 12207:2017 §6.1**, interface specifications must be documented. The VST SDK integration is Beetle Studio's primary audio effects extensibility mechanism.

Reference: [VST SDK Documentation](https://developer.steinberg.net/)

## Contents

- [Supported VST Versions](#supported-vst-versions)
- [Audio Architecture](#audio-architecture)
- [Plugin Scanning](#plugin-scanning)
- [VST 3 Processing Model](#vst-3-processing-model)
  - [Signal Flow](#signal-flow)
- [Plugin Delay Compensation](#plugin-delay-compensation)
  - [Latency Budget](#latency-budget)
- [Supported Parameter Types](#supported-parameter-types)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Supported VST Versions

| Version | Support | Notes |
|---|---|---|
| **VST 2.x** | ✅ Supported | Widely compatible, most plugins |
| **VST 3.x** | ✅ Supported | Modern standard; recommended for new plugins |
| **VST 1.x** | ❌ Not supported | Deprecated |

---

## Audio Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BEETLE STUDIO AUDIO                      │
│                                                              │
│  Timeline Audio ──► Bus Mixer ──► VST Plugin Chain ──► Output │
│  (per-clip)       │                                         │
│                   │                                         │
│              ┌────┴────┐                                   │
│              │  VST    │                                   │
│              │  Host    │◄──── VST Plugin A                │
│              │  Engine  │◄──── VST Plugin B                │
│              │          │◄──── VST Plugin C                │
│              └──────────┘                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Plugin Scanning

At startup, Beetle Studio scans configured plugin directories:

| Platform | Default Paths |
|---|---|
| **Windows** | `%PROGRAMFILES%\VSTPlugins`, `%PROGRAMFILES(X86)%\VSTPlugins`, `%APPDATA%\VSTPlugins` |

> **Note:** macOS and Linux paths are reserved for planned cross-platform support.

| **macOS** | `/Library/Audio/Plug-Ins/VST`, `~/Library/Audio/Plug-Ins/VST` |
| **Linux** | `~/.vst`, `/usr/lib/vst`, `/usr/local/lib/vst` |

Scanned file types: `.vst`, `.vst3`, `.dll`, `.so`, `.dylib`

---

## VST 3 Processing Model

VST 3 uses an audio processing model:

```cpp
// Process audio through VST 3 plugin
process_data = {
    inputs:  audioBuffers,       // Per-track audio
    outputs: processedBuffers,   // After plugin processing
    numSamples: blockSize,      // Typically 256–1024 samples
    sampleRate: 48000,          // Project sample rate
};

// Plugin processes audio in-place
plugin->process(process_data);
```

### Signal Flow

1. Timeline audio → routed to track bus
2. Bus → VST plugin chain (in order)
3. Each plugin processes its audio input
4. Output buses → master bus
5. Master bus → audio output device (WASAPI / ASIO)

---

## Plugin Delay Compensation

Per **ISO/IEC 25010:2023**, functional suitability includes accurate audio timing.

VST plugins introduce latency (group delay). To maintain audio/video sync:

| Feature | Description |
|---|---|
| **Fixed delay reporting** | Plugin reports its latency via `IAudioProcessor::getLatencySamples()` |
| **Automatic compensation** | Audio output delayed by max plugin latency in chain |
| **Video sync** | Video playhead adjusted to match compensated audio position |
| **Manual offset** | Per-plugin user-adjustable delay for hardware outboard gear |

### Latency Budget

| Source | Typical Latency |
|---|---|
| Audio interface (ASIO) | 5–20 ms (buffer size dependent) |
| VST plugin (effect) | 0–256 samples |
| VST instrument (synth) | 0–1024 samples |
| **Total acceptable** | < 10 ms for lip-sync |

---

## Supported Parameter Types

| VST Parameter | Beetle Studio Mapping | Animatable? |
|---|---|---|
| `kParamReal` | Float slider | ✅ Yes |
| `kParamBoolean` | Checkbox | ❌ No |
| `kParamString` | Text input | ❌ No |
| `kParamEnumerated` | Dropdown | ❌ No |
| Program changes | Preset slots | ❌ No |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 12207:2017 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Design), ISO/IEC 25010:2023 (Functional Suitability)*



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
| 1.0.0 | June 2026 | Ryan Foster | Initial version |
| 1.0.1 | June 2026 | Ryan Foster | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On VST SDK major version
- **Reviewer:** Ryan Foster (Audio Systems Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type