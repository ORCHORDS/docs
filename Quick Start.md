> Auto-generated from `docs/user/QUICK_START.md` in the docs repo.

---
title: "Quick Start Guide"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Quick Start Guide

**Project:** Beetle Studio  
**Owner:** Tom Anderson (Technical Writer)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)
**ISO Standards:** ISO/IEC 25010:2023 (usability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | First-project tutorial (10-minute hands-on walkthrough) |
| **Diátaxis form** | Tutorial |
| **Primary audience** | New Beetle Studio users |
| **Secondary audience** | Future maintainers and reviewers of this document |

---

## Overview

This guide walks you through creating your first video edit from scratch. By the end, you'll have imported media, assembled a timeline, applied an effect, and exported a finished video. **What you'll need:** A short video file (MP4, MOV, or MKV) on your computer.

## Contents

- [Your First Project in 10 Minutes](#your-first-project-in-10-minutes)
- [Step 1: Create a New Project (30 seconds)](#step-1-create-a-new-project-30-seconds)
- [Step 2: Import Your Media (1 minute)](#step-2-import-your-media-1-minute)
- [Step 3: Add Clips to the Timeline (2 minutes)](#step-3-add-clips-to-the-timeline-2-minutes)
- [Step 4: Make Your First Edit (3 minutes)](#step-4-make-your-first-edit-3-minutes)
  - [Trim the clip](#trim-the-clip)
  - [Split the clip](#split-the-clip)
  - [Delete a section](#delete-a-section)
- [Step 5: Add a Color Grade (2 minutes)](#step-5-add-a-color-grade-2-minutes)
- [Step 6: Export Your Video (2 minutes)](#step-6-export-your-video-2-minutes)
- [What to Do Next](#what-to-do-next)
- [Common Beginner Mistakes](#common-beginner-mistakes)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

## Your First Project in 10 Minutes

---

## Step 1: Create a New Project (30 seconds)

1. Launch **Beetle Studio**
2. Click **New Project** (or press `Ctrl+N`)
3. Name your project: `My First Edit`
4. Choose your settings — for this guide, select **1080p / 30fps**
5. Click **Create**

> **Tip:** The Project Browser appears on the left, and the Timeline appears at the bottom.

---

## Step 2: Import Your Media (1 minute)

1. Click the **Import Media** button in the Project Browser
2. Navigate to your video file
3. Click **Open**
4. Your file appears in the Project Browser

> **Tip:** You can also drag files directly from Windows Explorer into the Project Browser.

---

## Step 3: Add Clips to the Timeline (2 minutes)

1. **Single click** the video file in the Project Browser to select it
2. **Double-click** to preview it in the Viewport
3. **Drag** the file from the Project Browser onto the Timeline
4. The clip appears on Video Track 1 (V1)

> **Tip:** The Timeline auto-scrolls as you drag. The playhead (red vertical line) shows where the clip will land.

---

## Step 4: Make Your First Edit (3 minutes)

### Trim the clip

1. Hover over the **left edge** of the clip — the cursor changes to a trim cursor
2. **Drag right** to trim away the beginning
3. **Drag left** on the **right edge** to trim the end

### Split the clip

1. Move the **playhead** (red line) to the point where you want to cut
2. Press **`S`** — the clip is split into two parts

### Delete a section

1. Move the playhead to the start of the section you want to remove
2. Press **`S`** to split
3. Move the playhead to the end of the section
4. Press **`S`** to split again
5. **Click** the middle piece to select it
6. Press **`Delete`**

> **Tip:** Press **`Ctrl+Z`** to undo any mistake — Beetle Studio's undo system is unlimited.

---

## Step 5: Add a Color Grade (2 minutes)

1. **Click** the clip on the Timeline to select it
2. Open the **Effects Panel** (right side)
3. Click **Color Correction**
4. **Double-click** **Color Wheels**
5. In the **Properties Panel**, drag the **Master Exposure** slider to `+0.3`
6. Try dragging the **Shadows** wheel toward blue for a cinematic look

> **Tip:** Every effect change is undoable. Experiment freely — you can always step back.

---

## Step 6: Export Your Video (2 minutes)

1. Press **`Ctrl+Shift+E`** (or **File → Export**)
2. Choose **MP4** format with **H.264** codec
3. Set quality to **High**
4. Click **Choose Location** and pick where to save the file
5. Click **Export**

The progress bar shows export status. When it's done, click **Open** to view your finished video.

---

## What to Do Next

| Learn More | See |
|---|---|
| Timeline multi-track editing | [`USER_GUIDE.md`](./USER_GUIDE.md) |
| Keyboard shortcuts | [`KEYBOARD_SHORTCUTS.md`](./KEYBOARD_SHORTCUTS.md) |
| Transitions and effects | [`USER_GUIDE.md`](./USER_GUIDE.md) |
| Troubleshooting | [`help/TROUBLESHOOTING.md`](../help/TROUBLESHOOTING.md) |

---

## Common Beginner Mistakes

| Mistake | Solution |
|---|---|
| Playhead is at the end — can't see my edit | Press `Home` to go to start |
| Clip won't snap | Press `N` to toggle snap on |
| Audio is out of sync | Check clip in-points haven't drifted |
| Effect looks wrong | Press `Ctrl+Shift+R` to reset to defaults |
| Can't find my export | Check the folder selected in Export Settings |

---

*Grounded in: ISO/IEC 25010:2023 (Usability, Learnability)*



---

## References

### Internal Documents

- [$title](./../help/TROUBLESHOOTING.md)
- [$title](././KEYBOARD_SHORTCUTS.md)
- [$title](././USER_GUIDE.md)

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