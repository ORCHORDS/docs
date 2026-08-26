---
title: "WAI-ARIA Carousel Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Carousel Pattern

## Purpose

Provide public implementation guidance for accessible carousels and slide shows using the WAI-ARIA Authoring Practices Guide carousel pattern.

## Pattern baseline

A carousel presents a collection of items or slides one at a time or in a limited viewport, often with controls for rotation and navigation.

Accessible implementations should:

- provide clear previous and next controls when manual navigation is supported;
- provide a control to stop automatic rotation when slides advance automatically;
- stop automatic rotation when keyboard focus enters the carousel and avoid restarting unexpectedly;
- expose the carousel container and slide relationships with appropriate accessible names and semantics;
- ensure hidden slides are not exposed as active interactive content.

## Interaction guidance

Automatic movement can create significant usability problems. Users should be able to pause or stop rotation, and rotation should not compete with keyboard focus or screen-reader navigation.

## Implementation guidance

1. Prefer manual advancement unless automatic rotation serves a justified user need.
2. Give rotation, previous, next, and slide-picker controls meaningful accessible names.
3. Keep the current slide and visible state synchronized with any slide indicators.
4. Do not move keyboard focus merely because the visible slide changes.
5. Ensure controls remain keyboard reachable and focus indicators remain visible.
6. Test reduced-motion expectations and avoid rapid or unexpected transitions.

## Verification

Confirm that users can stop automatic rotation, keyboard focus is never moved or lost by slide changes, inactive slides cannot receive unintended focus, controls have meaningful names, and the currently displayed content can be determined reliably.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Carousel (Slide Show or Image Rotator) Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/carousel/
