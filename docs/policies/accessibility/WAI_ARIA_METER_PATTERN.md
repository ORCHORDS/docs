---
title: "WAI-ARIA Meter Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Meter Pattern

## Purpose

Provide guidance for presenting a numeric value within a meaningful bounded range.

## Pattern baseline

Use a meter for measurements such as battery level, fuel level, or utilization where a meaningful minimum and maximum exist. Do not use a meter for task progress; use a progress indicator instead.

## Roles and properties

- Use native HTML `meter` where practical or an element with role `meter`.
- Provide `aria-valuenow`, `aria-valuemin`, and `aria-valuemax` as appropriate.
- Use `aria-valuetext` when a numeric percentage alone would not communicate the value meaningfully.
- Give the meter an accessible name with visible labeling, `aria-labelledby`, or `aria-label`.

## Verification

Confirm the current value remains within the declared range and that assistive technologies announce both the meter's purpose and a meaningful value.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Meter Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/meter/
