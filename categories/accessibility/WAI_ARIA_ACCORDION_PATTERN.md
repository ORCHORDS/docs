---
title: "WAI-ARIA Accordion Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Accordion Pattern

## Purpose

Provide implementation guidance for accessible accordion interfaces based on the W3C WAI-ARIA Authoring Practices Guide.

## Pattern baseline

An accordion is a vertically stacked set of interactive headings that reveal or hide associated content panels.

## Keyboard interaction

- **Enter** or **Space** toggles the focused accordion header when the implementation allows that panel to change state.
- **Tab** and **Shift+Tab** move through all focusable elements in normal page order.

## Roles, states, and properties

- Each accordion header control uses a button, preferably a native `button` element.
- The button is contained in an appropriate heading element or an element with role `heading` and a suitable `aria-level`.
- Set `aria-expanded="true"` while the associated panel is visible and `false` while hidden.
- Set `aria-controls` to the ID of the associated panel.
- If an expanded panel cannot be collapsed, the controlling button may expose `aria-disabled="true"`.
- A panel may use role `region` with `aria-labelledby` when that landmark improves structure without creating excessive landmark regions.

## Implementation guidance

- Keep the heading hierarchy meaningful independent of visual styling.
- Do not place unrelated persistent controls inside the accordion heading element.
- Ensure collapsed panel content cannot remain keyboard-focusable.
- Avoid unnecessary `region` roles when many panels can be open simultaneously.

## Verification

Test each header with keyboard-only interaction and a screen reader. Confirm heading structure, expanded state, control-to-panel relationships, focus order, and hidden-panel behavior.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Accordion Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/accordion/
