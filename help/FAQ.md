---
title: "Frequently Asked Questions"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Frequently Asked Questions

**Project:** Mr.Orchords  
**Owner:** Mr.Orchords (Technical Writer)  
**Reviewers:** Mr.Orchords (CTO), Mr.Orchords (CEO)
**ISO Standards:** ISO/IEC 25010:2023 (usability, accessibility)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Frequently asked questions across all user and dev topics |
| **Diátaxis form** | Reference |
| **Primary audience** | All users, Mr.Orchords, Mr.Orchords |
| **Secondary audience** | Future maintainers and reviewers of this document |

---

## Overview

This document answers the most common questions about Mr.Orchords. Topics are grouped by area: general, projects and files, editing, effects, audio, export, account and cloud, and troubleshooting. If you have a question not covered here, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md) or contact support.

## Contents

- [General](#general)
  - [What is Mr.Orchords?](#what-is-mrorchords)
  - [What are the system requirements?](#what-are-the-system-requirements)
  - [Is Mr.Orchords free?](#is-mrorchords-free)
- [Projects & Files](#projects-files)
  - [What video formats does Mr.Orchords support?](#what-video-formats-does-mrorchords-support)
  - [Where does Mr.Orchords save my projects?](#where-does-mrorchords-save-my-projects)
  - [Can I recover a project if it crashes?](#can-i-recover-a-project-if-it-crashes)
- [Editing](#editing)
  - [How do I add transitions between clips?](#how-do-i-add-transitions-between-clips)
  - [How do I change the speed of a clip?](#how-do-i-change-the-speed-of-a-clip)
  - [Can I edit in 4K or HDR?](#can-i-edit-in-4k-or-hdr)
- [Effects](#effects)
  - [How do I install third-party effects?](#how-do-i-install-third-party-effects)
  - [How do I use a LUT file?](#how-do-i-use-a-lut-file)
- [Audio](#audio)
  - [How do I use VST plugins?](#how-do-i-use-vst-plugins)
- [Export](#export)
  - [What export format should I use?](#what-export-format-should-i-use)
  - [How long does export take?](#how-long-does-export-take)
- [Account & Cloud](#account-cloud)
  - [How does cloud sync work?](#how-does-cloud-sync-work)
  - [Can I share projects with other users?](#can-i-share-projects-with-other-users)
- [Troubleshooting](#troubleshooting)
  - [Preview playback is stuttering](#preview-playback-is-stuttering)
  - [Mr.Orchords crashes on startup](#mrorchords-crashes-on-startup)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

## General

### What is Mr.Orchords?

Mr.Orchords is a professional video editor for Windows. It offers GPU-accelerated editing, a multi-track timeline, professional color grading, VST audio effects, OpenFX plugin support, and FFmpeg-based codec support for virtually every video format.

### What are the system requirements?

See the User Guide — [`USER_GUIDE.md`](../user/USER_GUIDE.md). Minimum: Windows 10 (1903+), DirectX 12 GPU, 8 GB RAM. Recommended: Windows 11, NVIDIA RTX GPU, 32 GB RAM.

### Is Mr.Orchords free?

Mr.Orchords offers a free trial with no time limit and all features enabled. After the trial, a license is required for export. Pricing is available at [www.orchords.com/pricing](https://www.orchords.com/pricing).

---

## Projects & Files

### What video formats does Mr.Orchords support?

See the Format Support Matrix — [`FORMAT_SUPPORT_MATRIX.md`](../codecs/FORMAT_SUPPORT_MATRIX.md). In short: H.264, HEVC, AV1, VP9, ProRes, DNxHD, R3D, ARRI RAW, and more — all formats supported by FFmpeg and common professional codecs.

### Where does Mr.Orchords save my projects?

- **Default location:** `%USERPROFILE%\Documents\Mr.Orchords\Projects\`
- **Cloud sync:** If signed in, projects are automatically synced to your Mr.Orchords account
- **Custom location:** You can save anywhere via **File → Save As**

### Can I recover a project if it crashes?

Mr.Orchords auto-saves every 60 seconds. After a crash:
1. Launch Mr.Orchords
2. **File → Open Recent** — your project should appear
3. Choose **Recover Project** when prompted

---

## Editing

### How do I add transitions between clips?

1. Place two clips adjacent on the Timeline
2. Select the **Effects Panel → Transitions**
3. Drag a transition (e.g., **Cross Dissolve**) onto the junction between two clips
4. Adjust duration in the **Properties Panel**

### How do I change the speed of a clip?

1. **Right-click** the clip on the Timeline
2. Select **Speed / Duration**
3. Enter a speed percentage (e.g., `50%` for half speed, `200%` for double speed)
4. Or check **Maintain Pitch** to keep audio at normal pitch while video speed changes

### Can I edit in 4K or HDR?

Yes. Mr.Orchords supports:
- **Resolution:** Up to 8K (limited by system RAM and GPU VRAM)
- **HDR:** Rec.2020, DCI-P3, and HLG with proper color management

To enable HDR: **Edit → Project Settings → Color Space → Rec.2020 PQ (HDR)**

---

## Effects

### How do I install third-party effects?

1. Download an OpenFX plugin (`.ofx` or `.vst3`)
2. Copy to your plugin folder (shown in **Edit → Preferences → Plugins**)
3. Restart Mr.Orchords
4. The effect appears in the **Effects Panel**

For more: [`OPENFX_PLUGIN_GUIDE.md`](../OPENFX_PLUGIN_GUIDE.md)

### How do I use a LUT file?

1. Select a clip on the Timeline
2. Open **Effects → Color Correction → LUT**
3. Click **Load LUT** and select your `.cube` file
4. Adjust intensity in the Properties Panel

---

## Audio

### How do I use VST plugins?

1. Ensure the plugin is installed in your VST folder
2. In Mr.Orchords, select an audio clip or track
3. Open **Effects Panel → Audio → VST** and select your plugin
4. Adjust parameters in the **Properties Panel**

---

## Export

### What export format should I use?

| Use Case | Recommended |
|---|---|
| **YouTube / Vimeo** | MP4, H.264, 8–20 Mbps |
| **Archive / Master** | MOV, ProRes 422 HQ |
| **Social media** | MP4, H.264, 4–8 Mbps |
| **HDR delivery** | MOV, HEVC, Rec.2020 |
| **GIF** | MP4 → GIF converter built in |

### How long does export take?

Export time depends on:
- **Project complexity** — effects, color grading, multi-track
- **Output codec** — ProRes is faster than real-time; AV1 is slower
- **Hardware** — hardware encoding (NVENC/Quick Sync) is 3–10× faster than software

As a rough guide: 1 minute of edited video typically exports in 1–3 minutes on a modern GPU.

---

## Account & Cloud

### How does cloud sync work?

Sign in with Google or email. Your projects save to the cloud automatically every time you save. You can work offline — changes sync when you're back online.

### Can I share projects with other users?

Not yet — project sharing is on the roadmap for a future update. For now, export your project as a file and share it manually.

---

## Troubleshooting

### Preview playback is stuttering

See [`TROUBLESHOOTING.md`](../help/TROUBLESHOOTING.md). Most stuttering is resolved by reducing preview resolution (1/4 or 1/8) or closing other GPU applications.

### Mr.Orchords crashes on startup

See [`TROUBLESHOOTING.md`](../help/TROUBLESHOOTING.md). Try resetting user settings or updating GPU drivers.

---

*Grounded in: ISO/IEC 25010:2023 (Usability, Functional Suitability)*



---

## References

### Internal Documents

- [$title](./../codecs/FORMAT_SUPPORT_MATRIX.md)
- [$title](./../help/TROUBLESHOOTING.md)
- [$title](./../OPENFX_PLUGIN_GUIDE.md)
- [$title](./../user/USER_GUIDE.md)
- [$title](./TROUBLESHOOTING.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Mr.Orchords | Initial version |
| 1.0.1 | June 2026 | Mr.Orchords | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Monthly
- **Reviewer:** Mr.Orchords (Technical Writer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type