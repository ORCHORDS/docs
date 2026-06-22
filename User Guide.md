> Auto-generated from `docs/user/USER_GUIDE.md` in the docs repo.

---
title: "Beetle Studio — User Guide"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Beetle Studio — User Guide

**Project:** Beetle Studio  
**Owner:** Tom Anderson (Technical Writer)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)
**ISO Standards:** ISO/IEC 25010:2023 (usability, functional suitability), ISO 9241 (ergonomics)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Comprehensive application manual for end users |
| **Diátaxis form** | Tutorial |
| **Primary audience** | All Beetle Studio users |
| **Secondary audience** | Future maintainers and reviewers of this document |

---

## Overview

This guide covers all features and workflows in Beetle Studio, from basic editing to advanced compositing and effects.

## Contents

- [Getting Started](#getting-started)
  - [System Requirements](#system-requirements)
- [The Workspace](#the-workspace)
  - [Default Layout](#default-layout)
- [Workflow](#workflow)
  - [1. Create a New Project](#1-create-a-new-project)
  - [2. Import Media](#2-import-media)
  - [3. Build Your Timeline](#3-build-your-timeline)
  - [4. Apply Effects](#4-apply-effects)
  - [5. Color Grade](#5-color-grade)
  - [6. Export](#6-export)
- [Key Panels](#key-panels)
  - [Timeline](#timeline)
  - [Preview Viewport](#preview-viewport)
  - [Effects Panel](#effects-panel)
  - [Properties Panel](#properties-panel)
- [Cloud Features](#cloud-features)
- [Help & Support](#help-support)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Getting Started

### System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **OS** | Windows 10 (1903) | Windows 11 |
| **CPU** | Intel Core i5 / AMD Ryzen 5 | Intel Core i7 / AMD Ryzen 7 |
| **RAM** | 8 GB | 32 GB |
| **GPU** | DirectX 12 capable | NVIDIA RTX 3060 or better |
| **Storage** | 2 GB free | SSD, 10 GB free |
| **Display** | 1920×1080 | 2560×1440 or 4K |

---

## The Workspace

### Default Layout

```
┌────────────────────────────────────────────────────────┐
│  Menu Bar  │ File  Edit  View  Effects  Export  Help│
├──────────┬───────────────────────────────┬────────────┤
│          │                               │            │
│ Project  │                               │  Effects   │
│ Browser  │     Preview Viewport          │  Panel     │
│          │                               │            │
│          │                               ├────────────┤
│          │                               │            │
│          │                               │ Properties │
│          │                               │  Panel     │
├──────────┴───────────────────────────────┴────────────┤
│  ▶ Timeline                                          │
│  │ V1 ▸ Clip A  ▸ Clip B                            │
│  │ V2 ▸ Overlay                                       │
│  │ A1 ▸ Audio clip                                   │
└──────────────────────────────────────────────────────┘
```

---

## Workflow

### 1. Create a New Project

1. **File → New Project** (or `Ctrl+N`)
2. Enter a project name
3. Set your project settings (resolution, frame rate, color space)
4. Click **Create**

### 2. Import Media

1. Open the **Project Browser** panel
2. Click **Import Media** or drag files from Explorer
3. Beetle Studio supports: MP4, MOV, MKV, AVI, ProRes, R3D, WAV, MP3, AAC, and more

### 3. Build Your Timeline

1. Drag media from the Project Browser to the Timeline
2. Video clips snap to the playhead or other clips
3. Drag clip edges to trim
4. Press **S** to split a clip at the playhead

### 4. Apply Effects

1. Select a clip on the Timeline
2. Browse effects in the **Effects Panel**
3. Double-click an effect to apply it
4. Adjust parameters in the **Properties Panel**

### 5. Color Grade

1. Open **Effects → Color Correction**
2. Use **Color Wheels** for quick adjustments
3. Use **Color Curves** for precision control
4. Apply **LUT** files for film looks

### 6. Export

1. **Export → Export Settings** (or `Ctrl+Shift+E`)
2. Choose your format (MP4, MOV, MKV, GIF)
3. Choose your codec (H.264, HEVC, AV1, ProRes)
4. Set resolution and quality
5. Click **Export**

---

## Key Panels

### Timeline
The heart of your edit. Drag clips, trim edges, add transitions, and arrange your story.

### Preview Viewport
See your project in real time. Press **Space** to play/pause. Drag the playhead to scrub.

### Effects Panel
Browse and search effects. Effects are organized by category: Color, Blur, Distortion, Stylize, Audio.

### Properties Panel
When a clip or effect is selected, the Properties Panel shows all available parameters.

---

## Cloud Features

With a Beetle Studio account, your projects sync automatically:

- Sign in via **File → Sign In** (Google or email)
- Projects save to the cloud automatically
- Work offline — changes sync when you're back online
- Access your projects from any Windows device

---

## Help & Support

| Resource | Access |
|---|---|
| Keyboard shortcuts | **Help → Keyboard Shortcuts** |
| Tutorials | [www.mooned.dev/tutorials](https://www.mooned.dev/tutorials) |
| Community forum | [community.mooned.dev](https://community.mooned.dev) |
| Support ticket | **Help → Contact Support** |
| Bug report | **Help → Report a Bug** |

---

*Grounded in: ISO/IEC 25010:2023 (Usability, Functional Suitability), ISO 9241 (Ergonomics)*



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
| 1.0.0 | June 2026 | Tom Anderson | Initial version |
| 1.0.1 | June 2026 | Tom Anderson | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Monthly
- **Reviewer:** Tom Anderson (Technical Writer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type