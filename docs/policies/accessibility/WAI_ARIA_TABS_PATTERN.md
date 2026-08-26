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

Provide public implementation guidance for tabbed interfaces using the WAI-ARIA Authoring Practices Guide tabs pattern.

## Pattern baseline

A tabs component presents a set of tab controls and associated tab panels. One tab is active at a time unless the design explicitly supports multiple active panels.

Accessible implementations should:

- place tab controls in a container with `role="tablist"`;
- expose each tab with `role="tab"`;
- expose each associated panel with `role="tabpanel"`;
- use `aria-selected` to identify the active tab;
- associate tabs and panels with `aria-controls` and `aria-labelledby` where appropriate;
- manage focus so keyboard users can navigate predictably.

## Keyboard interaction

Common keyboard behavior includes:

- `Left Arrow` and `Right Arrow` to move among horizontal tabs;
- `Up Arrow` and `Down Arrow` for vertical orientation when implemented;
- `Home` and `End` optionally move to the first and last tab;
- `Enter` or `Space` activate a focused tab when manual activation is used.

Automatic activation is appropriate only when tab-panel content can be displayed without noticeable delay.

## Implementation guidance

1. Keep only the active tab in the normal tab sequence when using roving focus.
2. Keep `aria-selected` synchronized with the visible panel.
3. Ensure inactive panels are not exposed as active content.
4. Avoid automatic activation when loading or rendering a panel causes perceptible latency.
5. Test arrow-key movement, tab order, focus visibility, and panel association.

## Verification

Confirm that tabs have unique accessible names, keyboard navigation follows the documented orientation, selection state matches the visible panel, and focus remains predictable when activation changes.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Tabs Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/tabs/
