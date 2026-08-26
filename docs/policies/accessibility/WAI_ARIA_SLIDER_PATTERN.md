---
title: "WAI-ARIA Slider Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Slider Pattern

## Purpose

Provide public implementation guidance for single-value slider widgets using the WAI-ARIA Authoring Practices Guide slider pattern.

## Pattern baseline

A slider lets users choose a value within a bounded range by moving a thumb along a track.

Accessible implementations should:

- prefer a native range input when it meets the requirement;
- expose custom controls with `role="slider"`;
- provide an accessible name;
- expose `aria-valuemin`, `aria-valuemax`, and `aria-valuenow`;
- expose `aria-valuetext` when the numeric value alone is not meaningful;
- set orientation correctly when the slider is vertical.

## Keyboard interaction

Arrow keys increment or decrement the value. `Home` and `End` move to minimum and maximum values. `Page Up` and `Page Down` may provide larger author-defined changes.

## Implementation guidance

1. Use native `<input type="range">` where practical.
2. Keep the visual thumb position synchronized with the programmatic value.
3. Choose increments that reflect the underlying data and user task.
4. Ensure touch and pointer interaction do not replace keyboard operation.
5. Test value announcements at minimum, maximum, and intermediate positions.

## Verification

Confirm that keyboard users can reach and adjust the slider, assistive technology receives the current value and bounds, visible and programmatic values agree, and the control remains operable without fine pointer movements.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Slider Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/slider/
