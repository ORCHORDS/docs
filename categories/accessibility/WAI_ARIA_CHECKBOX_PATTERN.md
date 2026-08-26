---
title: "WAI-ARIA Checkbox Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Checkbox Pattern

## Purpose

Provide public implementation guidance for two-state and mixed-state checkbox widgets using the WAI-ARIA Authoring Practices Guide checkbox pattern.

## Pattern baseline

Checkboxes represent binary choices and, where appropriate, a third mixed state for a group-level control.

Accessible implementations should:

- prefer a native HTML checkbox when native semantics meet the interaction need;
- expose custom checkbox widgets with `role="checkbox"`;
- provide a meaningful accessible label;
- use `aria-checked="true"` for checked, `false` for unchecked, and `mixed` for a partially checked tri-state control;
- keep visual and programmatic state synchronized after every activation.

## Keyboard interaction

When a checkbox has focus, `Space` changes its state. Additional keyboard commands should not be invented unless another established component pattern is being implemented.

## Grouping guidance

Where a set of checkboxes forms a logical group, provide a group label using native grouping semantics or an appropriate ARIA group relationship. Additional descriptive text may be associated with the checkbox or group using `aria-describedby` when it adds useful context.

## Implementation guidance

1. Use native `<input type="checkbox">` wherever practical.
2. Ensure custom controls are focusable and operable with `Space`.
3. Do not communicate checked or mixed state by color or iconography alone.
4. If a group-level tri-state checkbox controls child options, update the parent state whenever child selections change.
5. Test disabled, required, validation, and mixed-state behavior where those states are used.

## Verification

Confirm that the accessible label is meaningful, keyboard activation changes state once per action, assistive technology receives the current checked state, and group-level mixed state accurately represents child selections.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Checkbox Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/checkbox/
