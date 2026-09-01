---
title: "WCAG 2.2 Focus Appearance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# WCAG 2.2 Focus Appearance

## Normative target
WCAG 2.2 SC **2.4.13 Focus Appearance** is **Level AAA**, not AA. For an unfocused-to-focused state change, the visible indicator must satisfy both size and contrast. Its area must be at least the area of a **2 CSS pixel thick perimeter** of the unfocused component, and the same pixels must change at least **3:1** between focused and unfocused states. An alternative passes if the indicator area is at least as large as the component and has 3:1 contrast against the same pixels in the unfocused state.

Exceptions apply when the appearance is determined by the user agent and not modified by the author, or when author-modified appearance cannot be adjusted because of platform limitations. SC 1.4.11 remains relevant to contrast against adjacent colors; satisfying only that criterion does not prove 2.4.13.

## Geometry and implementation
For a rectangular control of width W and height H, use the area of a 2 CSS pixel thick line drawn along the component boundary as the reference. Following the WCAG Understanding examples, that perimeter area is `2*(2W+2H)`, or `4W+4H` CSS square pixels; do not add exterior corner squares to the required area. For example, a 90-by-30 CSS pixel control has a 480-square-pixel reference area. A short underline often fails this area requirement. A continuous 2px outline normally supplies a straightforward baseline, although its rendered corner geometry still needs measurement against the reference rather than an assumed bounding-box formula. Avoid clipping it with `overflow:hidden`; use an inset ring only after calculating area and contrast. Multi-color indicators may aggregate only pixels meeting the required change.

Use `:focus-visible` without removing the fallback outline for environments that do not support the selector. In forced-colors mode, allow system colors and avoid `forced-color-adjust:none` unless separately verified. Component libraries should define ring width, offset, and tokens centrally.

## Measurement test
Capture the component before and after keyboard focus at device scale 1. Classify changed pixels belonging to the indicator, calculate their CSS-pixel area, and compare against the reference perimeter. Measure relative luminance for corresponding focused and unfocused pixels and require 3:1. Test every state: default, hover, selected, invalid, disabled-adjacent, dark theme, high contrast, and 400% zoom. Check focus rings at container edges for clipping.

Evidence must include dimensions, required area, measured qualifying area, contrast samples, screenshots, browser, theme, and CSS declarations. Common false passes measure the ring against the page instead of the same pixel’s unfocused color, count anti-aliased low-contrast pixels, or label this AAA criterion as an AA obligation.

## Sources
- [WCAG 2.2 — SC 2.4.13](https://www.w3.org/TR/WCAG22/#focus-appearance)
- [Understanding Focus Appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html)
