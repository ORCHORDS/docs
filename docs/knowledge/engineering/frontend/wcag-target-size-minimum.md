---
title: "WCAG 2.2 Target Size (Minimum)"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# WCAG 2.2 Target Size (Minimum)

## Requirement and exceptions
SC **2.5.8 Target Size (Minimum)** is **Level AA**. A pointer target must be at least **24 by 24 CSS pixels**, except when one of five conditions applies: **Spacing**, **Equivalent**, **Inline**, **User agent control**, or **Essential**. This is CSS-pixel geometry, independent of device-pixel density.

The spacing exception constructs a 24 CSS pixel diameter circle centered on each undersized target’s bounding box. It passes when that circle does not intersect another target or another undersized target’s circle. An equivalent control on the same page can exempt a small duplicate. Targets within a sentence or whose size is constrained by line height use the Inline exception. Unmodified user-agent controls and legally/meaningfully essential presentations have their own exceptions.

## Implementation
Increase the interactive hit box with padding or a positioned pseudo-element attached to the control; confirm the pseudo-element actually receives pointer events for the control. Keep table action icons at 24px minimum even when the glyph is 16px. Space map markers or provide a same-page list of equivalent destinations. Do not use the spacing exception as a design target when motor errors remain likely.

## Geometry test
Use `getBoundingClientRect()` for the clickable target, not the visible icon. Pass directly when width and height are each at least 24. For an undersized target, construct its centered 24px circle and test intersection with every other target boundary and every other undersized target circle. Perform this at responsive widths, zoom, localization, and after validation messages alter layout. Include overlapping transparent hit areas and generated pseudo-elements in manual inspection.

Classify every exception explicitly and retain evidence. For Inline, show that the target lies within a sentence or text block and is constrained by non-target text. For Equivalent, identify the same-page alternative and prove equal function. For Essential, record why changing size or spacing would fundamentally alter required information.

Common failures measure only center-to-center distance, use 24 device pixels, ignore targets that appear on hover, or assume a 44px row makes its tiny inline action 44px clickable.

## Sources
- [WCAG 2.2 — SC 2.5.8](https://www.w3.org/TR/WCAG22/#target-size-minimum)
- [Understanding Target Size Minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
