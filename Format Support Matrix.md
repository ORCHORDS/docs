> Auto-generated from `Format Support Matrix.md` in the docs repo.

> Auto-generated from `Format Support Matrix.md` in the docs repo.

> Auto-generated from `Format Support Matrix.md` in the docs repo.

> Auto-generated from `Format Support Matrix.md` in the docs repo.

> Auto-generated from `Format Support Matrix.md` in the docs repo.

> Auto-generated from `Format Support Matrix.md` in the docs repo.

> Auto-generated from `Format Support Matrix.md` in the docs repo.

> Auto-generated from `docs/codecs/FORMAT_SUPPORT_MATRIX.md` in the docs repo.

---
title: "Format Support Matrix"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Format Support Matrix

**Project:** Beetle Studio  
**Owner:** Sophie Williams (Video Codec Engineer)  
**Reviewers:** Kirk Beka (CTO), James Park (Graphics)  
**ISO Standards:** ISO/IEC 12207:2017 (development), ISO/IEC 25010:2023 (functional suitability, compatibility)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Supported video and audio codecs with hardware encoder notes |
| **Diátaxis form** | Reference |
| **Primary audience** | Sophie Williams, Kirk Beka, James Park, all users |
| **Secondary audience** | Future maintainers and reviewers of this document |


## Overview

This document lists all media formats, codecs, and container types supported by Beetle Studio, including import and export capabilities.

---

## Contents

- [Scope & Audience](#scope-audience)
- [Overview](#overview)
- [Video Codecs](#video-codecs)
  - [Decoding](#decoding)
  - [Encoding](#encoding)
- [Audio Codecs](#audio-codecs)
- [Container Formats](#container-formats)
- [Seeking Behavior](#seeking-behavior)
- [Hardware Acceleration](#hardware-acceleration)
  - [NVIDIA (NVENC / NVDEC)](#nvidia-nvenc-nvdec)
  - [Intel (Quick Sync Video)](#intel-quick-sync-video)
  - [AMD (VCE / RDNA)](#amd-vce-rdna)
- [Version History](#version-history)
- [References](#references)
  - [Internal Documents](#internal-documents)
  - [Standards & Frameworks](#standards-frameworks)
- [Document Maintenance](#document-maintenance)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

## Video Codecs

### Decoding

| Codec | Container | Hardware Decoding | Max Resolution | Profile |
|---|---|---|---|---|
| **H.264 / AVC** | MP4, MOV, MKV, AVI | NVIDIA NVDEC ✅ | 8K | Baseline → High 10 |
| **HEVC / H.265** | MP4, MOV, MKV | NVIDIA NVDEC ✅, Intel QSV ✅ | 8K | Main → Main 10 |
| **VP9** | WebM, MKV | Limited | 4K | Profile 0–2 |
| **AV1** | MP4, MKV, WebM | Hardware (new GPUs) | 8K | Main, High |
| **ProRes 422** | MOV | Decode via Apple hw (future) | 8K | LT, Proxy, Standard, HQ, 4444 |
| **ProRes 4444** | MOV | Decode via Apple hw (future) | 8K | 4444, XQ |
| **MPEG-4 Part 2** | MP4, AVI | Software only | 1080p | Simple → Advanced |
| **DNxHD / DNxHR** | MOV, MXF | Software only | 4K | 36 → 444 |
| **RED (R3D)** | R3D | Software only (GPU assist) | 6K | 4K-JPEG 2K, 4K-F, 4K-X |
| **ARRI RAW (ALEXA)** | ARX, MOV | Software only | 4.5K | Classic, Mini |

### Encoding

| Codec | Container | Hardware Encoding | Max Bitrate | Notes |
|---|---|---|---|---|
| **H.264 / AVC** | MP4 | NVENC ✅, QSV ✅, VCE ✅ | 250 Mbps | ABR, CBR, CRF modes |
| **HEVC / H.265** | MP4 | NVENC ✅, QSV ✅ | 200 Mbps | Main, Main 10 |
| **AV1** | MP4, WebM | NVENC AV1 (RTX 40xx+) | 150 Mbps | Best compression |
| **ProRes 422** | MOV | Software only | 440 Mbps | Professional delivery |
| **ProRes 4444** | MOV | Software only | 660 Mbps | With alpha support |
| **DNxHD** | MOV, MXF | Software only | 185 Mbps | MXF for broadcast |

---

## Audio Codecs

| Codec | Extensions | Notes |
|---|---|---|
| **AAC-LC / HE-AAC** | MP4, MOV, MKV, WebM | Primary web distribution |
| **MP3** | MP3, AVI, MKV | Universal compatibility |
| **PCM / WAV** | WAV, AIFF | Uncompressed; fast decode |
| **FLAC** | FLAC, MKV | Lossless; fast decode |
| **Opus** | WebM, MKV | Low-latency streaming |
| **AC3 / E-AC3** | AC3, E-AC3 | DVD/Blu-ray compatibility |
| **Dolby Atmos** | MP4, MOV | Metadata passthrough |

---

## Container Formats

| Container | Video | Audio | Subtitles | Chapters | Notes |
|---|---|---|---|---|---|
| **MP4** | ✅ | ✅ | ✅ | ✅ | Universal; recommended export |
| **MOV** | ✅ | ✅ | ✅ | ✅ | Apple ProRes, recommended for editing |
| **MKV** | ✅ | ✅ | ✅ | ✅ | Best codec flexibility |
| **WebM** | ✅ | ✅ | ✅ | ❌ | Web-optimized; VP9/AV1 |
| **AVI** | ✅ | ✅ | ✅ | ✅ | Legacy; limited codec support |
| **MXF** | ✅ | ✅ | ✅ | ✅ | Broadcast/professional |
| **MPEG-TS** | ✅ | ✅ | ✅ | ✅ | Streaming, broadcast |

---

## Seeking Behavior

| Scenario | Approach | Accuracy Target |
|---|---|---|
| **Normal scrub** | Decode from nearest keyframe | ± 1 frame |
| **Fast scrub** | Decode from nearest I-frame | ± 1 GOP |
| **Frame-accurate seek** | Demux + decode to exact frame | ± 0 frames (exact) |
| **Reverse playback** | Bidirectional decode | Same accuracy as forward |
| **Timecode seek** | Direct timecode-to-frame mapping | Frame-perfect |

---

## Hardware Acceleration

### NVIDIA (NVENC / NVDEC)

| GPU Generation | Encode | Decode | Notes |
|---|---|---|---|
| RTX 20xx+ | ✅ H.264, HEVC, AV1 | ✅ H.264, HEVC, AV1 | AV1 encode starts RTX 40xx |
| GTX 16xx | ✅ H.264, HEVC | ✅ H.264, HEVC | No AV1 encode |

### Intel (Quick Sync Video)

| GPU | Encode | Decode | Notes |
|---|---|---|---|
| Iris Xe+ | ✅ H.264, HEVC | ✅ H.264, HEVC, VP9 | 11th Gen+ |
| UHD 600 | ✅ H.264, HEVC | ✅ H.264, HEVC, VP9 | 10th Gen and older |

### AMD (VCE / RDNA)

| GPU | Encode | Decode | Notes |
|---|---|---|---|
| RDNA2 (RX 6000 series) | ✅ H.264, HEVC | ✅ H.264, HEVC | AV1 decode only |
| RDNA3 (RX 7000 series) | ✅ H.264, HEVC, AV1 | ✅ H.264, HEVC, AV1 | AV1 encode supported |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial matrix — aligned with ISO/IEC 25010:2023 functional suitability and compatibility |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Design), ISO/IEC 25010:2023 (Functional Suitability, Compatibility)*



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
| 1.0.0 | June 2026 | Sophie Williams | Initial version |
| 1.0.1 | June 2026 | Sophie Williams | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On each new codec support
- **Reviewer:** Sophie Williams (Video Codec Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type