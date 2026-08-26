---
title: "WAI-ARIA Window Splitter Pattern"
owner: "Accessibility Lead"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Window Splitter Pattern

## Purpose

Provide cautious implementation guidance for adjustable separators between window panes.

## Pattern status

W3C APG notes that this pattern is not yet fully reviewed because a complete matching example is still pending. Treat it as guidance under review rather than a finalized consensus pattern.

## Guidance

- Use a focusable element with role `separator` for an adjustable splitter.
- Expose `aria-valuenow`, `aria-valuemin`, and `aria-valuemax` for the splitter position.
- Label the splitter with `aria-labelledby` or `aria-label`.
- Use `aria-controls` to identify the primary pane.
- Provide documented keyboard controls for resizing and optional minimum/maximum positioning.
- Keep focus visible while resizing.

## Verification

Test keyboard resizing, focus, announced value changes, labeling, minimum/maximum behavior, and pane relationships with assistive technology.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Window Splitter Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/windowsplitter/
