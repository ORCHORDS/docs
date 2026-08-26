---
title: "WAI-ARIA Alert Dialog Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Alert Dialog Pattern

## Purpose

Provide public implementation guidance for important, interruptive dialogs using the WAI-ARIA Authoring Practices Guide alert dialog pattern.

## Pattern baseline

An alert dialog is a modal dialog used for a brief, important message that requires a user response before work continues.

Accessible implementations should:

- use `role="alertdialog"` for the dialog container when the interaction genuinely requires immediate attention and response;
- provide a meaningful accessible name with `aria-labelledby` or `aria-label`;
- provide a concise accessible description of the alert message when appropriate;
- move keyboard focus into the dialog when it opens;
- contain the tab sequence within the modal dialog;
- restore focus to a logical location when the dialog closes.

## Interaction guidance

The dialog should follow the modal-dialog keyboard model, including `Tab`, `Shift+Tab`, and dismissal behavior where dismissal is permitted. For destructive or difficult-to-reverse decisions, initial focus may appropriately be placed on the least destructive action.

## Implementation guidance

1. Reserve alert dialogs for genuinely important interruptions rather than routine information.
2. Keep the message concise enough to understand with the dialog name and focused control.
3. Provide clearly named actions whose consequences are understandable before activation.
4. Do not mark content as an alert dialog if users can continue interacting with background content.
5. Test initial focus, focus containment, action labels, and focus restoration.

## Verification

Confirm that assistive technology announces the alert-dialog context and message, keyboard focus is placed within the dialog, users cannot tab into inactive background content, and the default focus choice does not encourage accidental destructive action.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Alert and Message Dialogs Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/alertdialog/
