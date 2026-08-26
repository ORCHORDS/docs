---
title: "WAI-ARIA Tooltip Pattern"
owner: "Accessibility Lead"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Tooltip Pattern

## Purpose

Provide cautious guidance for tooltip behavior based on the W3C WAI-ARIA Authoring Practices Guide.

## Pattern status

W3C APG marks this tooltip pattern as work in progress and notes that it does not yet have task-force consensus. Treat it as guidance under review, not as a finalized consensus pattern.

## Guidance

- Use role `tooltip` on the tooltip container.
- Associate the trigger with the tooltip using `aria-describedby` when the tooltip supplies additional descriptive information.
- Keep keyboard focus on the trigger; tooltips themselves should not receive focus.
- Support `Escape` to dismiss the tooltip.
- Ensure pointer users can keep the tooltip visible while moving over the trigger or tooltip as appropriate.
- Do not place interactive controls inside a tooltip; use a non-modal dialog pattern for interactive popovers.

## Verification

Test keyboard focus, pointer hover, dismissal, accessible description, timing, and persistence behavior with representative assistive technologies.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Tooltip Pattern** (work in progress): https://www.w3.org/WAI/ARIA/apg/patterns/tooltip/
