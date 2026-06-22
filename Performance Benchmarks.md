> Auto-generated from `Performance Benchmarks.md` in the docs repo.

> Auto-generated from `Performance Benchmarks.md` in the docs repo.

> Auto-generated from `PERFORMANCE_BENCHMARKS.md` in the docs repo.

> Auto-generated from `docs/PERFORMANCE_BENCHMARKS.md` in the docs repo.

---
title: "Performance Benchmarks"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Performance Benchmarks

**Project:** Beetle Studio  

**Owner:** James Park (Graphics Engineer — GPU), Sophie Williams (Codec Specialist — encode/decode), Lisa Martinez (QA Lead — measurement)  
**Reviewers:** Kirk Beka (CTO)  
**ISO Standards:** ISO/IEC 25010:2023 (performance efficiency, time behavior, resource utilization)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Performance targets, measurement methodology, and benchmark results |
| **Diátaxis form** | Reference |
| **Primary audience** | James Park, Sophie Williams, Lisa Martinez, Kirk Beka |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines Beetle Studio's performance targets, measurement methodology, and benchmarks. Per **ISO/IEC 25010:2023**, performance efficiency — specifically **time behavior** (response and processing times) and **resource utilization** — is a primary software product quality characteristic that must be measured and tracked.

Benchmarks are measured by **Lisa Martinez (QA Lead)** at every alpha and beta release, and reviewed by **James Park** and **Kirk Beka**.

## Contents

- [Performance Targets](#performance-targets)
  - [Preview Playback](#preview-playback)
  - [Video Encoding](#video-encoding)
  - [Audio](#audio)
  - [Memory Usage](#memory-usage)
- [Measurement Methodology](#measurement-methodology)
  - [Test Hardware](#test-hardware)
  - [Test Media](#test-media)
  - [Tools](#tools)
- [Regression Policy](#regression-policy)
- [Web Performance (Core Web Vitals)](#web-performance-core-web-vitals)
  - [Targets (Google "Good" thresholds)](#targets-google-good-thresholds)
  - [Bundle Size Budgets](#bundle-size-budgets)
  - [Hosting & Edge](#hosting-edge)
  - [Performance Regression Policy](#performance-regression-policy)
  - [Performance Test Pipeline (web)](#performance-test-pipeline-web)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---


---


---

## Performance Targets

### Preview Playback

| Scenario | Target | Method |
|---|---|---|
| 1080p / 30fps — no effects | ≥ 60 FPS | Playback stress test |
| 1080p / 30fps — 3 effects | ≥ 60 FPS | Effects enabled, timeline playback |
| 4K / 30fps — no effects | ≥ 30 FPS | 4K media only |
| 4K / 30fps — 3 effects | ≥ 24 FPS | 4K + 3 effects |
| Scrubbing (1080p) | < 100ms latency | Time from drag to frame update |

### Video Encoding

| Codec | Resolution | Target (NVIDIA RTX 3060) | Target (Intel i7-12700) |
|---|---|---|---|
| H.264 | 1080p / 30fps | ≥ 3× realtime | ≥ 1.5× realtime |
| H.264 | 4K / 30fps | ≥ 1× realtime | ≥ 0.5× realtime |
| HEVC | 1080p / 30fps | ≥ 2× realtime | ≥ 1× realtime |
| AV1 | 1080p / 30fps | ≥ 1× realtime | ≥ 0.3× realtime |
| ProRes 422 | 4K / 30fps | ≥ 0.8× realtime | ≥ 0.4× realtime |

*Realtime = encode speed matches playback speed (1× = encodes 30 frames in 1 second)*

### Audio

| Metric | Target |
|---|---|
| Playback latency | < 10 ms (ASIO/WASAPI exclusive) |
| Audio/video sync drift | 0 frames over 10-minute playback |
| Audio export time | ≤ 1.5× realtime (stereo, 44.1 kHz) |

### Memory Usage

| Scenario | Target (Peak RSS) |
|---|---|
| Idle (no project) | < 200 MB |
| 1080p project (10 clips, no playback) | < 1 GB |
| 1080p project (10 clips, playing) | < 2 GB |
| 4K project (10 clips, playing) | < 4 GB |
| GPU VRAM (1080p, playing) | < 1 GB |

---

## Measurement Methodology

### Test Hardware

| Configuration | Spec |
|---|---|
| **Minimum spec machine** | Intel i5-9400, 8 GB RAM, GTX 1660 Super, SSD |
| **Recommended spec machine** | Intel i7-12700K, 32 GB RAM, RTX 3060, NVMe SSD |
| **High-end spec machine** | Intel i9-13900K, 64 GB RAM, RTX 4090, NVMe SSD |

### Test Media

Standard test clips for reproducibility:
- `test_1080p_30fps.mp4` — H.264, 10 seconds, 1920×1080 @ 30fps
- `test_4k_30fps.mov` — ProRes 422, 10 seconds, 3840×2160 @ 30fps
- `test_audio_44k.wav` — 44.1 kHz stereo, 60 seconds

### Tools

| Metric | Tool |
|---|---|
| FPS | Internal Beetle Studio frame timing (logged to `performance.log`) |
| Encode speed | FFmpeg benchmark + custom timer |
| Memory | Windows Task Manager + Beetle Studio internal profiling |
| GPU profiling | RenderDoc (James Park) / PIX (Microsoft GDK) |
| Latency | Custom instrumentation logging in milliseconds |

---

## Regression Policy

Per **ISO/IEC 25010:2023**, performance regression is a quality defect.

| Regression | Severity | Action |
|---|---|---|
| Any target misses by ≥ 20% | High | Blocker for release |
| Any target misses by 5–20% | Medium | Investigate; acceptable if root cause is external |
| Any target misses by < 5% | Low | Document and monitor |

---

## Web Performance (Core Web Vitals)

Performance targets for the marketing website (`mooned.dev`) and user-facing web apps. Measured via **Lighthouse CI** in the web pipeline and **CrUX** (Chrome User Experience Report) for real-user data.

### Targets (Google "Good" thresholds)

| Metric | Target | Hard gate | Measurement |
|---|---|---|---|
| **LCP** (Largest Contentful Paint) | < 2.5 s | Yes | Lighthouse, CrUX |
| **CLS** (Cumulative Layout Shift) | < 0.1 | Yes | Lighthouse, CrUX |
| **INP** (Interaction to Next Paint) | < 200 ms | Yes | Lighthouse, CrUX |
| **TTFB** (Time to First Byte) | < 800 ms | Yes | Synthetic, RUM |
| **TBT** (Total Blocking Time) | < 200 ms | Yes | Lighthouse |
| **FCP** (First Contentful Paint) | < 1.8 s | Yes | Lighthouse |
| **Speed Index** | < 3.4 s | No | Lighthouse |

### Bundle Size Budgets

| Resource | Budget (gzip) | Tool | Gate |
|---|---|---|---|
| Initial JS | < 200 KB | `size-limit` | Yes |
| Initial CSS | < 50 KB | `size-limit` | Yes |
| Web fonts | < 100 KB total | Manual | Yes |
| Above-fold images | < 150 KB total | Lighthouse | No |
| Total page weight | < 1.5 MB | Lighthouse | No |

### Hosting & Edge

- **Edge cache:** Cloudflare (full-page cache for marketing, bypass for auth)
- **Image optimization:** WebP + AVIF, responsive `srcset`
- **CDN headers:** `Cache-Control: public, max-age=31536000, immutable` for static assets
- **HTTP/3** enabled at edge
- **Compression:** Brotli at origin + Cloudflare

### Performance Regression Policy

| Regression | Severity | Action |
|---|---|---|
| LCP/CLS/INP crosses "Needs Improvement" threshold | High | Blocker for release |
| Any metric regresses by >= 20% vs baseline | High | Blocker for release |
| Any metric regresses by 5-20% | Medium | Investigate; acceptable if root cause is documented |
| Bundle size exceeds budget | High | Blocker for release |

### Performance Test Pipeline (web)

| Stage | Tool | Frequency |
|---|---|---|
| `size-limit` check | `size-limit` | Every PR |
| Lighthouse CI | `@lhci/cli` | Every PR, every deploy |
| CrUX field data | Google CrUX API | Weekly |
| Real User Monitoring (RUM) | Cloudflare Analytics | Continuous |
| Synthetic monitor | Checkly (or similar) | Every 5 min from 3 regions |

For accessibility, browser compatibility, and visual regression testing of the web, see [ACCESSIBILITY_COMPLIANCE.md Website Design Testing](./ACCESSIBILITY_COMPLIANCE.md#website-design-testing).

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial benchmarks — aligned with ISO/IEC 25010:2023 performance efficiency |

---

*Grounded in: ISO/IEC 25010:2023 — Performance Efficiency (Time Behavior, Resource Utilization)*



---

## References

### Internal Documents

- [$title](././ACCESSIBILITY_COMPLIANCE.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | James Park, Lisa Martinez, Sophie Williams | Initial version |
| 1.0.1 | June 2026 | James Park, Lisa Martinez, Sophie Williams | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On each alpha/beta release
- **Reviewer:** James Park (Graphics — GPU)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type