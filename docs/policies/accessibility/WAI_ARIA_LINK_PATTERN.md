---
title: "WAI-ARIA Link Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Link Pattern

## Purpose

Provide guidance for accessible links and link-like widgets.

## Pattern baseline

Prefer a native HTML anchor with an `href` whenever navigation is intended. Native links automatically provide expected browser semantics and behaviors.

## Guidance

- Use native links for navigation where practical.
- If role `link` is applied to a non-anchor element, implement expected keyboard and activation behavior explicitly.
- `Enter` activates the link.
- Ensure the accessible name communicates the destination or purpose in context.
- Preserve browser conventions such as focus visibility and destination behavior unless there is a strong, tested reason not to.

## Verification

Test keyboard activation, focus indication, accessible naming, and expected navigation behavior with assistive technology.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Link Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/link/
