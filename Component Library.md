> Auto-generated from `Component Library.md` in the docs repo.

> Auto-generated from `Component Library.md` in the docs repo.

> Auto-generated from `docs/ui/COMPONENT_LIBRARY.md` in the docs repo.

---
title: "UI Component Library"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# UI Component Library

**Project:** Beetle Studio  
**Owner:** Alex Chen (Lead UI/UX Engineer)  
**Reviewers:** Nina Patel (UX Designer), Kirk Beka (CTO)  
**ISO Standards:** ISO/IEC 12207:2017 (development), ISO 9241 (ergonomics, usability), ISO/IEC 25010:2023 (usability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Qt6 widget patterns, DPI handling, and keyboard shortcuts |
| **Diátaxis form** | Reference |
| **Primary audience** | Alex Chen, Nina Patel, all UI contributors |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes the Beetle Studio UI component library. Per **ISO/IEC 12207:2017 section 6.1.3**, the UI must be designed with documented component specifications. Per **ISO 9241** and **ISO/IEC 25010:2023**, usability is a primary quality characteristic.
## Contents

- [Technology Stack](#technology-stack)
- [Core Components](#core-components)
  - [Panel System](#panel-system)
  - [Timeline Component](#timeline-component)
- [DPI & Multi-Monitor Support](#dpi-multi-monitor-support)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Theming](#theming)
- [Accessibility](#accessibility)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| **Framework** | Qt6 (QMainWindow, QWidget) | Primary; QML for new components |
| **Styling** | Qt Style Sheets (QSS) | Consistent dark theme |
| **Animation** | Qt Animation Framework | Smooth transitions |
| **Layout** | QLayout (QVBox/QHBox/Grid) | DPI-aware layouts |
| **Fonts** | Segoe UI Variable (Windows) | Scalable, variable-weight |

---

## Core Components

### Panel System

Beetle Studio uses a **docking panel** layout:

| Panel | Purpose | Default Position |
|---|---|---|
| **Project Browser** | Media asset management | Left dock |
| **Timeline** | Clip editing | Bottom dock |
| **Preview Viewport** | Video preview | Center |
| **Effects** | Effect browser + stack | Right dock |
| **Properties** | Clip/effect properties | Right dock (tabbed with Effects) |
| **Audio Mixer** | Track levels, pan | Bottom (tabbed with Timeline) |

Panels are draggable, dockable, and floatable. Layouts are user-saveable.

### Timeline Component

The timeline is the most complex UI element:

| Sub-Component | Description |
|---|---|
| **Track header** | Track name, type icon, mute/solo/lock |
| **Playhead** | Red vertical line, draggable |
| **Clip** | Visual representation; colored by type |
| **Trim handles** | Left/right edge drag handles |
| **Effect badges** | Small icons indicating applied effects |
| **Ruler** | Timecode ruler; click to seek |
| **Scrollbar** | Horizontal + vertical; zoom with mouse wheel |

---

## DPI & Multi-Monitor Support

| Requirement | Implementation |
|---|---|
| **DPI scaling** | Qt6's built-in DPI scaling; `setHighDpiScaling(true)` |
| **Font size** | Logical pixels — scales with system DPI |
| **Icons** | SVG icons rendered at multiple sizes |
| **Multi-monitor** | Each monitor's DPI independently respected |
| **Tested resolutions** | 1920×1080, 2560×1440, 3840×2160 |

---

## Keyboard Shortcuts

All shortcuts are managed by a centralized `ShortcutManager` (per [`VERSIONING_POLICY.md`](../releases/VERSIONING_POLICY.md)):

```cpp
// Register shortcuts in one central location — never hardcode
ShortcutManager::instance().register(
    "timeline.split",
    QKeySequence(Qt::Key_S),
    "Split clip at playhead"
);
ShortcutManager::instance().register(
    "timeline.toggleSnap",
    QKeySequence(Qt::Key_N),
    "Toggle snap to grid"
);
```

Full shortcut reference: [`user/KEYBOARD_SHORTCUTS.md`](../user/KEYBOARD_SHORTCUTS.md)

---

## Theming

Beetle Studio uses a **dark theme** as the default (professional video editing convention — reduces eye strain during long sessions):

```css
/* beetleshell.qss — main application theme */
QMainWindow {
    background-color: #1E1E1E;
    color: #CCCCCC;
}

QToolBar {
    background-color: #252526;
    border: none;
}

QPanel {
    background-color: #252526;
}

QSlider::groove:horizontal {
    border: 1px solid #3E3E42;
    height: 4px;
    background: #3E3E42;
    border-radius: 2px;
}
```

---

## Accessibility

Per **ISO 9241-171** and **ISO/IEC 25010:2023**, the UI must support users with diverse abilities:

| Feature | Implementation | WCAG Level |
|---|---|---|
| **Keyboard navigation** | All panels, menus, and dialogs keyboard-navigable | AA |
| **Screen reader** | Qt accessibility APIs — ARIA-like labels on all controls | AA |
| **Color contrast** | Text ≥ 4.5:1 contrast ratio on dark background | AA |
| **Focus indicators** | Visible focus ring on all interactive elements | AA |
| **Reduce motion** | Respects OS `prefers-reduced-motion` setting | AA |

See [`ACCESSIBILITY_COMPLIANCE.md`](../ACCESSIBILITY_COMPLIANCE.md) for the full accessibility specification.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO 9241, ISO/IEC 12207:2017, ISO/IEC 25010:2023 |

---

*Grounded in: ISO 9241 (Ergonomics of Human System Interaction), ISO/IEC 12207:2017 §6.1.3, ISO/IEC 25010:2023 (Usability)*



---

## References

### Internal Documents

- [$title](./../ACCESSIBILITY_COMPLIANCE.md)
- [$title](./../user/KEYBOARD_SHORTCUTS.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Alex Chen | Initial version |
| 1.0.1 | June 2026 | Alex Chen | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Alex Chen (Lead UI/UX Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type