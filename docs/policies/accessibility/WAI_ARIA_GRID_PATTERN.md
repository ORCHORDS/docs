---
title: "WAI-ARIA Grid Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Grid Pattern

## Purpose

Provide public implementation guidance for interactive grids using the WAI-ARIA Authoring Practices Guide grid pattern.

## Pattern baseline

A grid is a composite widget that supports directional keyboard navigation among cells or interactive elements. It may represent tabular data or a layout collection.

Accessible implementations should:

- use `role="grid"` only when composite keyboard navigation is actually implemented;
- expose rows and cells with appropriate row, gridcell, rowheader, or columnheader semantics;
- include only one managed grid location in the page tab sequence at a time;
- provide author-managed arrow-key navigation inside the grid;
- expose selection state only when the grid supports selection.

## Keyboard interaction

Arrow keys move among grid cells. `Home`, `End`, `Page Up`, and `Page Down` may provide row or viewport navigation, while `Control+Home` and `Control+End` may move to grid boundaries in data-grid implementations.

## Implementation guidance

1. Use a native table for static tabular content that does not need composite interaction.
2. Ensure every cell that users must perceive while in application-style navigation is focusable or labels a focusable cell.
3. Separate grid-navigation commands from editing commands inside editable cells.
4. Keep visual position, DOM order, and assistive-technology reading order aligned.
5. Document and test selection behavior independently from focus movement.

## Verification

Confirm that users can enter and leave the grid with `Tab`, navigate cells predictably with directional keys, reach all relevant content, distinguish focus from selection, and operate controls embedded in cells without losing grid context.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Grid Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/grid/
