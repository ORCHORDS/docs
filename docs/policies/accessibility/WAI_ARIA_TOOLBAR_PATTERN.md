---
title: "WAI-ARIA Toolbar Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Toolbar Pattern

## Purpose

Provide public implementation guidance for grouped controls using the WAI-ARIA Authoring Practices Guide toolbar pattern.

## Pattern baseline

A toolbar groups related controls such as buttons, menu buttons, checkboxes, or links. When custom composite keyboard behavior is used, `role="toolbar"` communicates the group and roving focus can reduce the number of page tab stops.

## Keyboard interaction

For a horizontal toolbar, `Left Arrow` and `Right Arrow` normally move among controls. For a vertical toolbar, `Up Arrow` and `Down Arrow` normally provide navigation. `Tab` enters and leaves the toolbar rather than stopping on every control when roving focus is implemented.

## Implementation guidance

- Use a toolbar when controls form a meaningful group, not merely for visual layout.
- Provide an accessible name when multiple toolbars need to be distinguished.
- Avoid placing controls in a toolbar when their own operation requires the same arrow keys used for toolbar navigation unless conflicts are deliberately resolved.
- Keep focus order predictable when controls become disabled, hidden, or added dynamically.
- Preserve each contained control’s own semantics and state.

## Verification

Confirm that users can enter and leave the toolbar with `Tab`, navigate controls with the documented arrow keys, operate each control without key conflicts, and perceive a meaningful toolbar label when necessary.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Toolbar Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/toolbar/
