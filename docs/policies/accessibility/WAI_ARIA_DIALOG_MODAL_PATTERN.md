---
title: "WAI-ARIA Modal Dialog Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Modal Dialog Pattern

## Purpose

Provide public implementation guidance for modal dialogs using the WAI-ARIA Authoring Practices Guide dialog modal pattern.

## Pattern baseline

A modal dialog is a window overlaid on the primary content that requires interaction or dismissal before users continue with content outside the dialog.

Accessible implementations should:

- expose the dialog container with `role="dialog"` or `role="alertdialog"` when the alert-dialog pattern is appropriate;
- set `aria-modal="true"` only when content outside the dialog is actually unavailable for interaction;
- provide an accessible name with `aria-labelledby` or `aria-label`;
- place keyboard focus inside the dialog when it opens;
- keep keyboard focus within the modal while it remains open;
- return focus to the invoking control, or another logical location, when it closes.

## Keyboard interaction

- `Tab` and `Shift+Tab` move focus among focusable elements inside the dialog and wrap within it.
- `Escape` closes the dialog where dismissal is permitted.

## Implementation guidance

1. Include a visible close or cancel control when users need an explicit dismissal mechanism.
2. Choose initial focus based on task context rather than always focusing the first interactive element.
3. Avoid marking a dialog modal unless background content is both visually and programmatically unavailable.
4. Keep the dialog in a logical DOM relationship and ensure its accessible name is concise and meaningful.
5. Test focus placement, focus containment, dismissal, and focus restoration with keyboard and assistive technology.

## Verification

Confirm that focus never escapes to inactive background content, the dialog has a meaningful accessible name, `aria-modal` reflects actual behavior, and closing the dialog restores focus predictably.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Dialog (Modal) Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
