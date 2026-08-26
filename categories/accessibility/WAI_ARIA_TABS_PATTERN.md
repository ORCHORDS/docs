---
title: "WAI-ARIA Tabs Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Tabs Pattern

## Purpose

Provide implementation guidance for a set of tab controls that switch between associated content panels using the W3C WAI-ARIA Authoring Practices Guide.

## Pattern baseline

A tabs interface contains a `tablist`, one or more `tab` elements, and corresponding `tabpanel` elements. One tab is selected at a time unless the design explicitly supports a different model.

## Keyboard interaction

- **Left Arrow** and **Right Arrow** move focus between tabs in a horizontal tab list.
- **Up Arrow** and **Down Arrow** may be used for vertical tab lists.
- **Home** may move focus to the first tab.
- **End** may move focus to the last tab.
- If activation is manual, **Enter** or **Space** activates the focused tab.

Automatic activation is appropriate only when the associated panel can be displayed without noticeable delay.

## Roles, states, and properties

- The container uses role `tablist`.
- Each control uses role `tab`.
- The active tab has `aria-selected="true"`; inactive tabs use `false`.
- Each tab references its panel with `aria-controls`.
- Each panel uses role `tabpanel` and references its tab with `aria-labelledby`.

## Implementation guidance

- Maintain one tab stop within the tab list using managed `tabindex`.
- Ensure hidden panels do not expose interactive descendants to keyboard users.
- Keep tab labels concise and descriptive.
- Do not use tab semantics for ordinary navigation links that lead to separate pages.

## Verification

Test arrow-key movement, activation mode, focus order, selected state, and screen-reader relationships between each tab and its panel.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Tabs Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/tabs/
