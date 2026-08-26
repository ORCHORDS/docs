---
title: "WAI-ARIA Multi-Thumb Slider Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Multi-Thumb Slider Pattern

## Purpose

Provide public implementation guidance for sliders with two or more independently focusable thumbs using the WAI-ARIA Authoring Practices Guide multi-thumb slider pattern.

## Pattern baseline

Each thumb is a slider with its own accessible name, current value, minimum, and maximum. The relationship between thumb values may constrain the permitted range of one thumb based on another thumb’s current value.

## Keyboard interaction

Each thumb follows the slider keyboard model, including arrow keys and optional `Home`, `End`, `Page Up`, and `Page Down` behavior. Every thumb remains in a stable page tab order regardless of its visual position or value.

## Implementation guidance

- Give each thumb a distinct accessible name that explains the value it controls.
- Keep dynamic `aria-valuemin` and `aria-valuemax` constraints synchronized when thumbs cannot cross.
- Keep tab order stable even if thumbs visually pass or overlap.
- Ensure visual layering does not make one thumb impossible to operate.
- Thoroughly test touch-based assistive technologies because W3C notes support limitations for slider gestures on some devices.

## Verification

Confirm that every thumb is independently keyboard reachable, current values and bounds are accurate, constraints update correctly, tab order is stable, and the range can be adjusted using keyboard and representative touch assistive technologies.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Slider (Multi-Thumb) Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/slider-multithumb/
