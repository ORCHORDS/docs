---
title: "WAI-ARIA Combobox Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Combobox Pattern

## Purpose

Provide public implementation guidance for editable and select-only combobox widgets using the WAI-ARIA Authoring Practices Guide combobox pattern.

## Pattern baseline

A combobox is an input widget with an associated popup that presents allowed or suggested values. The popup may use listbox, grid, tree, or dialog semantics.

Accessible implementations should:

- expose the input with `role="combobox"` where native semantics do not already provide the required behavior;
- keep `aria-expanded` synchronized with popup visibility;
- associate the combobox with its popup using `aria-controls` when appropriate;
- expose the popup role accurately and set `aria-haspopup` when the popup type is not the implicit listbox;
- preserve browser text-editing behavior for editable comboboxes;
- manage active suggestion state without moving DOM focus unnecessarily when `aria-activedescendant` is used.

## Keyboard interaction

Common interactions include `Down Arrow` to move toward popup choices, `Escape` to dismiss the popup, `Enter` to accept a selected suggestion, and standard text-editing keys for editable inputs. Optional key behavior should match the popup type and documented interaction model.

## Implementation guidance

1. Prefer native controls when they meet the product requirement.
2. Do not intercept standard text editing keys with JavaScript.
3. Keep visual selection, `aria-selected`, and the active descendant relationship synchronized.
4. Ensure popup opening and closing does not unexpectedly change the current value.
5. Test editable, select-only, empty-result, required, and dismissal states.

## Verification

Confirm that the accessible name and current value are both perceivable, popup state is announced correctly, keyboard navigation follows the selected popup model, and dismissing suggestions does not trap or lose focus.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Combobox Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/combobox/
