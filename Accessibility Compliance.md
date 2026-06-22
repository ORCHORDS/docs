> Auto-generated from `ACCESSIBILITY_COMPLIANCE.md` in the docs repo.

> Auto-generated from `docs/ACCESSIBILITY_COMPLIANCE.md` in the docs repo.

---
title: "Accessibility Compliance"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Accessibility Compliance

**Project:** Beetle Studio  

**Owner:** Alex Chen (UI/UX Lead - implementation), Nina Patel (UX Designer - design audit)  
**Reviewers:** Kirk Beka (CTO), Nina Patel (UX Designer)  
**ISO Standards:** ISO 9241-171 (ergonomic requirements for office work with visual display terminals), ISO/IEC 25010:2023 (usability - accessibility subcharacteristic)  
**Version:** 1.1.0  
**Last Updated:** 2026-06-20  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | WCAG 2.1 AA compliance targets and accessibility audit checklist |
| **Diátaxis form** | Reference |
| **Primary audience** | Alex Chen, Nina Patel, Kirk Beka, all UI contributors |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines the accessibility standards and compliance requirements for Beetle Studio's user interface. All UI components must meet WCAG 2.1 Level AA conformance.

## Contents

- [WCAG 2.1 AA Compliance Targets](#wcag-21-aa-compliance-targets)
- [Implementation Checklist](#implementation-checklist)
  - [Keyboard Navigation](#keyboard-navigation)
  - [Color & Contrast](#color-contrast)
  - [Screen Reader Support](#screen-reader-support)
  - [Timeline Waveform Alt Text](#timeline-waveform-alt-text)
- [Reducing Motion](#reducing-motion)
- [Audit Schedule](#audit-schedule)
- [Known Accessibility Limitations](#known-accessibility-limitations)
- [Website Design Testing](#website-design-testing)
  - [Accessibility (WCAG 2.1 AA + axe-core)](#accessibility-wcag-21-aa-axe-core)
  - [Performance (Core Web Vitals)](#performance-core-web-vitals)
  - [Browser & Device Compatibility](#browser-device-compatibility)
  - [Visual Regression](#visual-regression)
  - [Web Test Pipeline (skeleton)](#web-test-pipeline-skeleton)
  - [Bug Severity for Web Issues](#bug-severity-for-web-issues)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## WCAG 2.1 AA Compliance Targets

| WCAG Criterion | Description | Beetle Studio Target |
|---|---|---|
| 1.1.1 | Non-text content (images, icons) | All icons labeled; meaningful alt text |
| 1.3.1 | Info and relationships | Semantic structure; correct ARIA roles |
| 1.4.3 | Contrast (minimum) | Text ≥ 4.5:1 against background |
| 1.4.4 | Text resizing | UI readable up to 200% zoom |
| 2.1.1 | Keyboard accessibility | All features accessible by keyboard |
| 2.4.3 | Focus order | Logical tab order through all controls |
| 2.4.7 | Focus visible | Visible focus indicator on all interactive elements |
| 3.1.1 | Page/screen language | UI language set correctly per locale |
| 4.1.2 | Name, role, value | All controls have accessible name and role |

---

## Implementation Checklist

### Keyboard Navigation

| Feature | Keyboard Access | Notes |
|---|---|---|
| All panels | `Tab` / `Shift+Tab` | |
| Panel menus | `Alt` + underlined letter | Standard Windows convention |
| Timeline | Arrow keys for clips | Full timeline navigation |
| Playback | `Space` | Universal play/pause |
| Clips | `Enter` to select, `Delete` to remove | |
| Effects | `Tab` through effect parameters | |
| Dialog buttons | `Tab` through buttons; `Enter` to activate | |

### Color & Contrast

| Element | Foreground | Background | Contrast Ratio |
|---|---|---|---|
| Primary text | #CCCCCC | #252526 | 8.9:1 ✓ |
| Secondary text | #969696 | #1E1E1E | 5.8:1 ✓ |
| Button label | #FFFFFF | #0E639C | 7.2:1 ✓ |
| Warning text | #FFCC00 | #1E1E1E | 11.2:1 ✓ |
| Error text | #F14C4C | #1E1E1E | 5.9:1 ✓ |

### Screen Reader Support

Qt6 provides accessibility APIs. Key implementations:

| Component | ARIA Role | Keyboard Interaction |
|---|---|---|
| Timeline clip | `img` + `aria-label` | Arrow keys to navigate |
| Timeline waveform | `img` + `aria-label` (see Waveform Alt Text below) | Arrow keys to scrub |
| Playhead | `slider` | Arrow keys to scrub |
| Effect parameter | `slider` | Tab + Arrow keys |
| Menu item | `menuitem` | Standard menu navigation |
| Toolbar button | `button` | Space/Enter to activate |
| Panel | `region` | Focus enters region |

### Timeline Waveform Alt Text

The audio waveform is rendered as a non-text image (`QPainter` paths) and therefore
requires a text alternative per **WCAG 2.1 1.1.1 (Non-text Content)**.

**Implementation in `src/timeline/WaveformView.{h,cpp}`:**

1. Each `CClip` carries an accessibility description string (`m_a11yDescription`)
   built at media-import time from these signals:
   - Filename (e.g. `"interview_take_03.wav"`)
   - Duration (e.g. `"2 minutes 14 seconds"`)
   - Channel layout (e.g. `"stereo"`, `"mono"`)
   - Peak amplitude (loudness band: quiet / normal / loud / clipped)
   - Number of detected speech vs music segments (from silence detection)

2. The waveform `QWidget` exposes `accessibleName` and `accessibleDescription`
   via `QAccessibleObject` so screen readers (NVDA, Narrator, JAWS) read a
   summary like:

   > *"Interview take 3, stereo, 2 minutes 14 seconds, normal loudness,
   > 4 speech segments and 1 silence gap."*

3. When the user focuses a clip, NVDA reads the description; arrow keys
   step through clips and re-announce.

4. Custom screen-reader verbosity is provided via
   **Edit → Preferences → Accessibility → Waveform Verbosity** with four
   levels: Off, Brief (filename + duration), Normal (+ loudness),
   Detailed (+ segment breakdown).

**Test coverage:**
- `tests/accessibility/test_waveform_alt_text.cpp` — verifies each clip's
  `accessibleDescription` is non-empty, fits the contract, and updates
  when the source media changes.

---

## Reducing Motion

Per **WCAG 2.1 2.3.3**, Beetle Studio respects OS-level motion reduction:

```cpp
// Respect OS-level "Show animations in Windows" setting
QSettings settings("HKEY_CURRENT_USER\\Control Panel\\Accessibility\\ReduceMotion", QSettings::NativeFormat);
bool reduceMotion = settings.value("Active").toBool();

if (reduceMotion) {
    // Disable non-essential animations:
    // - Panel slide transitions → instant show/hide
    // - Timeline zoom animation → instant zoom
    // - Playhead smooth scrub → frame-by-frame
}
```

---

## Audit Schedule

| Audit Type | Frequency | Owner |
|---|---|---|
| Automated accessibility scan | Every release | Lisa Martinez (QA) |
| Manual keyboard navigation test | Every release | Alex Chen + QA |
| Screen reader test (NVDA, Narrator) | Every major version | QA + external volunteer |
| Color contrast audit | Every release | Nina Patel |
| Full WCAG audit | Annually | External accessibility consultant |

---

## Known Accessibility Limitations

| Limitation | Severity | Mitigation |
|---|---|---|
| Color blindness simulation | Not available in-app | Suggest OS-level tools |
| Eye-tracking input | Not supported | Future consideration |

> Note: Timeline waveform alt text (previously listed here) has been
> implemented in v1.1.0 — see [Timeline Waveform Alt Text](#timeline-waveform-alt-text).

---

## Website Design Testing

This section covers accessibility, performance, browser compatibility, and visual regression testing for the marketing website (`mooned.dev`) and any user-facing web app. The desktop app has its own checks in the sections above; this section is **web-only**.

### Accessibility (WCAG 2.1 AA + axe-core)

| Check | Tool | When | Gate |
|---|---|---|---|
| Automated axe scan | `axe-core` via Playwright | Every PR (web) | No serious/critical violations |
| Contrast checker | `axe-core` color-contrast rule | Every PR | No failures |
| Keyboard navigation | Playwright + manual script | Weekly | All interactive elements reachable |
| Screen reader smoke test | NVDA (Win) + VoiceOver (Mac) | Per release | Landmarks + headings + form labels work |
| WCAG 2.1 AA audit | Manual + `pa11y-ci` | Quarterly | Full report |

The same **WCAG 2.1 AA** target applies as the desktop app. See the [WCAG Compliance Targets](#wcag-21-aa-compliance-targets) section above for the criteria list.

### Performance (Core Web Vitals)

Measured via **Lighthouse CI** in the web pipeline. Targets align with Google's "Good" thresholds.

| Metric | Target (Good) | Tool | Frequency |
|---|---|---|---|
| **LCP** (Largest Contentful Paint) | < 2.5 s | Lighthouse + CrUX | Every PR, weekly CrUX |
| **CLS** (Cumulative Layout Shift) | < 0.1 | Lighthouse | Every PR |
| **INP** (Interaction to Next Paint) | < 200 ms | Lighthouse + RUM | Weekly |
| **TTFB** (Time to First Byte) | < 800 ms | Synthetic + RUM | Every PR |
| **TBT** (Total Blocking Time) | < 200 ms | Lighthouse | Every PR |
| **JS bundle size** (initial) | < 200 KB gzip | `size-limit` | Every PR, hard gate |
| **Lighthouse Performance score** | >= 90 | Lighthouse CI | Per deploy |

For desktop-app performance (playback, export), see [PERFORMANCE_BENCHMARKS.md](./PERFORMANCE_BENCHMARKS.md).

### Browser & Device Compatibility

| Browser | Versions supported | Tested via |
|---|---|---|
| Chrome | Latest 2 stable versions | Playwright + BrowserStack |
| Edge | Latest 2 stable versions (Chromium-based) | Playwright + BrowserStack |
| Firefox | Latest 2 stable versions | Playwright + BrowserStack |
| Safari (macOS) | Latest 2 stable versions | BrowserStack only |
| Safari (iOS) | Latest 2 stable versions | BrowserStack + manual |
| Chrome Android | Latest 2 stable versions | BrowserStack + manual |

**Breakage budget:** if a feature works in Chrome/Edge/Firefox but breaks in Safari, that is a **P1 bug** (not a "known limitation") because Safari is a supported target.

**Responsive breakpoints tested:**

| Breakpoint | Width | Notes |
|---|---|---|
| Mobile | 360, 414 px | iPhone SE + Plus |
| Tablet | 768, 1024 px | iPad portrait + landscape |
| Desktop | 1280, 1440, 1920 px | Standard + 4K |

### Visual Regression

| Tool | What it does | When |
|---|---|---|
| **Percy** (or Chromatic) | Pixel-diff against approved baseline screenshots | Every PR |
| **Playwright visual** | Local screenshot snapshots for critical pages | Per release |
| **Storybook visual** (if used) | Component-level visual diffs | Every PR |

**Process:**
1. Designer signs off on a Figma frame
2. Frame is converted to baseline screenshot in `tests/visual/baselines/`
3. Every PR runs visual diff against baseline
4. Diffs require explicit approval (reviewer + designer for marketing pages)

**Critical pages always snapshot:**

- Home (above fold + full)
- Pricing
- Features / Why Beetle Studio
- Download / Get Started
- Login
- Docs landing

### Web Test Pipeline (skeleton)

| Stage | Tool | Gate |
|---|---|---|
| Unit | Vitest | All pass |
| Component | Storybook + a11y addon | No a11y violations |
| Visual | Percy | No unapproved diffs |
| E2E | Playwright (cross-browser) | All pass on Chrome, Firefox, Safari |
| Performance | Lighthouse CI | All CWV in "Good" range |
| A11y | axe-core + pa11y-ci | Zero serious/critical |

### Bug Severity for Web Issues

| Severity | Definition | Response |
|---|---|---|
| **P0** | Site down, auth broken, checkout broken | 4 hours |
| **P1** | Major feature broken in supported browser | 1 business day |
| **P2** | Minor feature broken, workaround exists | Next sprint |
| **P3** | Cosmetic, copy, or non-supported-browser only | Backlog |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial compliance spec - aligned with WCAG 2.1 AA, ISO 9241-171, ISO/IEC 25010:2023 |
| 1.1.0 | 2026-06-20 | Alex Chen - Implemented Timeline waveform alt text (WCAG 1.1.1); removed from Known Limitations; added `WaveformView` accessibility contract and verbosity preference |

---

*Grounded in: ISO/IEC 25010:2023 (Usability subcharacteristic: Accessibility), ISO 9241-171*



---

## References

### Internal Documents

- [`./PERFORMANCE_BENCHMARKS.md`](./PERFORMANCE_BENCHMARKS.md) - Desktop performance targets
- [`../timeline/DATA_MODEL.md`](../timeline/DATA_MODEL.md) - Clip metadata used for waveform alt text

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering - Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering - Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Alex Chen, Nina Patel | Initial version |
| 1.0.1 | June 2026 | Alex Chen, Nina Patel | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |
| 1.1.0 | 2026-06-20 | Alex Chen | Implemented Timeline waveform alt text per WCAG 1.1.1; spec for WaveformView accessible description contract |

### Review Cadence

- **Next review:** On WCAG major revision
- **Reviewer:** Alex Chen (UI implementation)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type