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

Provide implementation guidance for accessible modal dialogs using the W3C WAI-ARIA Authoring Practices Guide.

## Pattern baseline

A modal dialog contains content and controls that require interaction before users return to the rest of the page. While open, content outside the dialog is inert from the user’s interaction perspective.

## Keyboard interaction

- **Tab** and **Shift+Tab** move focus among focusable elements within the dialog.
- Focus remains contained within the dialog while it is modal.
- **Escape** closes the dialog when dismissal is supported.

## Roles, states, and properties

- The dialog container uses role `dialog`.
- Use `aria-modal="true"` for a modal dialog.
- Provide an accessible name using `aria-labelledby` or `aria-label`.
- Use `aria-describedby` only when the referenced descriptive content is appropriate to announce as a single description.

## Focus management

- Move focus into the dialog when it opens.
- Choose the initial focus target based on the dialog’s content and task, not simply the first focusable element in every case.
- When the dialog closes, normally return focus to the element that opened it unless workflow context makes another destination more logical.

## Implementation guidance

- Include a visible close control when users are expected to dismiss the dialog.
- Prevent keyboard interaction with content outside the modal.
- Do not mark a dialog modal unless interaction outside it is actually unavailable.
- Keep destructive or irreversible actions clearly distinguished from ordinary dismissal.

## Verification

Test opening, focus containment, reading order, accessible naming, dismissal, and focus restoration using keyboard-only interaction and a screen reader.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Dialog (Modal) Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
