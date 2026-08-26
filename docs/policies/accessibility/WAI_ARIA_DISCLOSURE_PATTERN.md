---
title: "WAI-ARIA Disclosure Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Disclosure Pattern

## Purpose

Provide public implementation guidance for a control that shows or hides associated content using the WAI-ARIA Authoring Practices Guide disclosure pattern.

## Pattern baseline

A disclosure control is typically a button that toggles visibility of a section of content.

For an accessible implementation:

- use a native button where possible;
- expose `aria-expanded="true"` when the controlled content is visible and `false` when it is hidden;
- use `aria-controls` when it usefully identifies the controlled region;
- keep the accessible state synchronized with the visible state;
- preserve a logical reading and focus order when content is revealed or hidden.

## Keyboard interaction

When focus is on the disclosure button:

- `Enter` activates the control;
- `Space` activates the control.

Additional keyboard behavior should not be added unless the component is implementing a different established pattern.

## Implementation guidance

1. Use visible text or an otherwise meaningful accessible name for the control.
2. Do not rely on icon direction alone to communicate expanded or collapsed state.
3. Do not move focus automatically merely because content becomes visible unless the interaction requires it.
4. Ensure hidden content is actually unavailable to interaction when collapsed.
5. Test state synchronization after mouse, touch, and keyboard activation.

## Verification

Confirm that the button is keyboard operable, `aria-expanded` always matches the rendered state, revealed content remains in a sensible reading order, and collapsing the disclosure does not leave focus trapped in hidden content.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Disclosure (Show/Hide) Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
