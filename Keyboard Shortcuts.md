> Auto-generated from `user/KEYBOARD_SHORTCUTS.md` in the docs repo.

> Auto-generated from `docs/user/KEYBOARD_SHORTCUTS.md` in the docs repo.

---
title: "Keyboard Shortcuts"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Keyboard Shortcuts

**Project:** Beetle Studio  
**Owner:** Tom Anderson (Technical Writer) — maintained with Alex Chen (UI)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)
**ISO Standards:** ISO/IEC 25010:2023 (usability), ISO 9241-12 (navigation)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Complete keyboard shortcut reference |
| **Diátaxis form** | Reference |
| **Primary audience** | All Beetle Studio users |
| **Secondary audience** | Future maintainers and reviewers of this document |

---

## Overview

This document is the complete reference for every keyboard shortcut in Beetle Studio on Windows. Shortcuts are grouped by functional area. Use this document to speed up your editing workflow and to look up the key binding for any action.

## Contents

- [Global Shortcuts](#global-shortcuts)
- [Playback](#playback)
- [Timeline](#timeline)
- [Editing](#editing)
- [Effects](#effects)
- [Color](#color)
- [Audio](#audio)
- [Display](#display)
- [Customizing Shortcuts](#customizing-shortcuts)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

## Global Shortcuts

| Action | Windows | Notes |
|---|---|---|
| **New Project** | `Ctrl+N` | |
| **Open Project** | `Ctrl+O` | |
| **Save Project** | `Ctrl+S` | |
| **Save As** | `Ctrl+Shift+S` | |
| **Undo** | `Ctrl+Z` | |
| **Redo** | `Ctrl+Y` | |
| **Cut** | `Ctrl+X` | |
| **Copy** | `Ctrl+C` | |
| **Paste** | `Ctrl+V` | |
| **Delete** | `Delete` | |
| **Select All** | `Ctrl+A` | |
| **Find** | `Ctrl+F` | |
| **Export** | `Ctrl+Shift+E` | |
| **Import Media** | `Ctrl+I` | |
| **Quit** | `Alt+F4` | |
| **Preferences** | `Ctrl+,` | |

---

## Playback

| Action | Windows | Notes |
|---|---|---|
| **Play / Pause** | `Space` | |
| **Stop** | `Enter` | Return to start |
| **Go to Start** | `Home` | |
| **Go to End** | `End` | |
| **Step Forward** | `Right Arrow` | 1 frame |
| **Step Backward** | `Left Arrow` | 1 frame |
| **Go Forward 10 frames** | `Shift+Right` | |
| **Go Back 10 frames** | `Shift+Left` | |
| **Go to Next Clip** | `Down Arrow` | Jump to next edit point |
| **Go to Previous Clip** | `Up Arrow` | Jump to prev edit point |
| **Loop Playback** | `L` | Toggle loop on/off |
| **Slow Motion** | `J` (hold) | Press multiple times for faster reverse |

---

## Timeline

| Action | Windows | Notes |
|---|---|---|
| **Split Clip** | `S` | Cut at playhead |
| **Ripple Delete** | `Shift+Delete` | Delete and close gap — auto-ripples all downstream clips left to fill the gap (no `Ctrl+Z` undo needed if you change your mind) |
| **Toggle Snap** | `N` | Toggle magnetic snapping |
| **Zoom In** | `=` or `Num+` | |
| **Zoom Out** | `-` or `Num-` | |
| **Fit Timeline** | `Shift+Z` | Fit all clips in view |
| **Add Track** | `Ctrl+Shift+N` | |
| **Delete Track** | `Ctrl+Shift+Delete` | |
| **Go to Marker** | `M` | Add marker at playhead |
| **Next Marker** | `Shift+M` | |
| **Previous Marker** | `Ctrl+Shift+M` | |

---

## Editing

| Action | Windows | Notes |
|---|---|---|
| **Trim In** | `I` | Set in-point |
| **Trim Out** | `O` | Set out-point |
| **Go to In** | `Q` | |
| **Go to Out** | `W` | |
| **Lift** | `Alt+X` | Extract without closing gap — removes the selected clip and leaves a black gap in its place; downstream clips are **not** moved |
| **Splice** | `Alt+C` | Insert and close gap — pastes the clipboard clip at the playhead and ripple-shifts everything downstream to make room |
| **Rate Stretch** | `R` | Stretch clip to fit |
| **Slip** | `Y` | Move in/out points together |
| **Slide** | `U` | Move clip on track |
| **Match Frame** | `F` | Show source frame in preview |
| **Overwrite** | `F9` | Write to tape |

---

## Effects

| Action | Windows | Notes |
|---|---|---|
| **Add Effect** | `Shift+E` | Open effect browser |
| **Remove Effect** | `Alt+Shift+E` | |
| **Next Effect** | `Tab` | Select next in stack |
| **Previous Effect** | `Shift+Tab` | Select prev in stack |
| **Copy Effects** | `Ctrl+Alt+C` | |
| **Paste Effects** | `Ctrl+Alt+V` | |
| **Toggle Effect** | `E` | |
| **Reset Effect** | `Ctrl+Shift+R` | Reset to default |

---

## Color

| Action | Windows | Notes |
|---|---|---|
| **Color Wheels** | `Ctrl+Alt+Shift+C` | |
| **Color Curves** | `Ctrl+Alt+Shift+U` | |
| **HSL Adjustments** | `Ctrl+Alt+Shift+H` | |
| **LUT Browser** | `Ctrl+Alt+Shift+L` | |
| **Reset Color** | `Ctrl+Shift+C` | |

---

## Audio

| Action | Windows | Notes |
|---|---|---|
| **Mute Selected Track** | `M` (when track selected) | |
| **Solo Selected Track** | `S` (when track selected) | |
| **Audio Waveforms** | `W` (when track selected) | Toggle waveform display |
| **Record** | `R` (on armed track) | |
| **Split Audio from Video** | `Ctrl+Alt+Shift+S` | |

---

## Display

| Action | Windows | Notes |
|---|---|---|
| **Toggle Full Screen** | `F11` | |
| **Toggle Safe Areas** | `Shift+T` | |
| **Toggle Rulers** | `Ctrl+R` | |
| **Toggle Guides** | `Ctrl+Shift+G` | |
| **Show All Panels** | `Tab` (release quickly) | Restore hidden panels |

---

## Customizing Shortcuts

All shortcuts can be customized:

1. **Help → Keyboard Shortcuts**
2. Click on any shortcut to change it
3. Type the new key combination
4. Click **Save**

---

*Grounded in: ISO/IEC 25010:2023 (Usability), ISO 9241-12 (Dialogue principles)*



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

- **Next review:** On shortcut changes
- **Reviewer:** Tom Anderson (Technical Writer) — maintained with Alex Chen (UI)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type