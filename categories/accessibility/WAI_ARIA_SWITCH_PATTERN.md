---
title: "WAI-ARIA Switch Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Switch Pattern

## Purpose

Provide public implementation guidance for binary on/off controls using the WAI-ARIA Authoring Practices Guide switch pattern.

## Pattern baseline

A switch represents exactly two states: on and off. A custom implementation uses `role="switch"`, provides an accessible label, and exposes its state with `aria-checked="true"` or `aria-checked="false"`.

## Interaction guidance

The switch must be keyboard operable. `Space` toggles the state; implementations may also support `Enter` when consistent with the host control and user expectations.

## Implementation guidance

- Choose switch semantics only when on/off terminology fits the user task better than checked/unchecked.
- Keep the visible state and `aria-checked` synchronized.
- Do not change the accessible label when the state changes; expose state through the control semantics.
- Group related switches with a meaningful group label where useful.
- Prefer a native checkbox when it provides the needed interaction and semantics.

## Verification

Confirm the switch has a stable meaningful accessible name, keyboard activation changes state exactly once, assistive technology announces on/off state, and the visual state matches the programmatic state.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Switch Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/switch/
