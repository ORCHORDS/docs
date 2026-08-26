---
title: "WAI-ARIA Listbox Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Listbox Pattern

## Purpose

Provide public implementation guidance for single-select and multi-select listboxes using the WAI-ARIA Authoring Practices Guide listbox pattern.

## Pattern baseline

A listbox presents a set of options and allows one or more selections.

Accessible implementations should:

- expose the container with `role="listbox"` when native controls are insufficient;
- expose children with `role="option"`;
- provide an accessible name for the listbox;
- set `aria-multiselectable="true"` when multiple selection is supported;
- expose option selection consistently with `aria-selected` or `aria-checked` according to the chosen model;
- keep focus and selection semantics distinct where the interaction requires it.

## Keyboard interaction

Arrow keys move focus among options. `Home` and `End` are strongly recommended for longer lists. Type-ahead is recommended, especially when many options are present. Multi-select implementations should document and consistently apply their selection model.

## Implementation guidance

1. Prefer native `<select>` when it satisfies the requirement.
2. Avoid embedding interactive controls inside listbox options; use another pattern such as grid when options contain independent controls.
3. Keep option names concise and distinguishable.
4. Do not make selection follow focus unless that behavior is appropriate and tested.
5. Ensure dynamically loaded options expose correct set position information when needed.

## Verification

Confirm accessible naming, arrow-key navigation, selected-state exposure, multi-select behavior, type-ahead behavior, and synchronization between visual focus and programmatic state.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Listbox Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/listbox/
