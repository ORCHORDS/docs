---
title: "WAI-ARIA Spinbutton Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Spinbutton Pattern

## Purpose

Provide public implementation guidance for inputs restricted to a discrete numeric or enumerated range using the WAI-ARIA Authoring Practices Guide spinbutton pattern.

## Pattern baseline

A spinbutton typically combines a text-editable value with increment and decrement behavior. The focusable element uses `role="spinbutton"` when native semantics are insufficient and exposes current and permitted values with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and, where useful, `aria-valuetext`.

## Keyboard interaction

`Up Arrow` increases the value and `Down Arrow` decreases it. `Page Up` and `Page Down` may apply larger changes. `Home` and `End` may move to minimum and maximum values where useful. Standard platform text-editing keys must continue to work when direct text entry is supported.

## Implementation guidance

- Prefer native numeric or other suitable HTML input controls when they meet the interaction need.
- Do not capture keys in JavaScript in ways that break browser-provided text editing.
- Keep visible text, programmatic value, and range constraints synchronized.
- Validate typed values without unexpectedly moving focus.
- Test boundary values, invalid input, keyboard adjustment, and touch assistive technologies.

## Verification

Confirm that the current value and range are exposed accurately, arrow-key changes respect bounds, standard text editing remains usable, and visual and programmatic values never diverge.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Spinbutton Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/spinbutton/
