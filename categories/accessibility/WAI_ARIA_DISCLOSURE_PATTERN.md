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

Provide implementation guidance for a control that shows or hides a section of content using the W3C WAI-ARIA Authoring Practices Guide disclosure pattern.

## Pattern baseline

A disclosure consists of a button and content whose visibility is controlled by that button. The control communicates whether the associated content is expanded or collapsed.

## Keyboard interaction

- **Enter** activates the disclosure control.
- **Space** activates the disclosure control.

## Roles, states, and properties

The control should normally be a native `button` element.

- Use `aria-expanded="true"` when the controlled content is visible.
- Use `aria-expanded="false"` when it is hidden.
- Use `aria-controls` when useful to identify the controlled region.

## Implementation guidance

- Keep the accessible name of the control stable enough that users understand what is being expanded or collapsed.
- Do not rely on a visual icon alone to communicate state.
- Preserve a logical reading and focus order when content is revealed.
- Avoid moving focus automatically unless the interaction specifically requires it.
- Ensure the collapsed content is not exposed as interactive content to keyboard users.

## Verification

Test activation with keyboard-only interaction and a screen reader. Confirm that the expanded state is announced and that hidden interactive descendants cannot receive focus while collapsed.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Disclosure Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
