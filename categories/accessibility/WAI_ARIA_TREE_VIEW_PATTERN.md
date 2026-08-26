---
title: "WAI-ARIA Tree View Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Tree View Pattern

## Purpose

Provide public implementation guidance for hierarchical tree widgets using the WAI-ARIA Authoring Practices Guide tree view pattern.

## Pattern baseline

A tree view presents hierarchical items that can be expanded or collapsed and navigated with directional keys.

Accessible implementations should:

- expose the container with `role="tree"`;
- expose items with `role="treeitem"`;
- represent nested groups with `role="group"` where needed;
- expose expansion state with `aria-expanded` on parent items;
- expose selection state consistently when selection is supported;
- keep only the active tree item in the normal tab sequence when roving focus is used.

## Keyboard interaction

`Down Arrow` and `Up Arrow` move among visible items. `Right Arrow` opens a closed parent or moves to its first child, while `Left Arrow` closes an open parent or moves to its parent. `Home` and `End` may move to the first and last visible items, and type-ahead is recommended for larger trees.

## Implementation guidance

1. Keep visual indentation consistent with the programmatic hierarchy.
2. Do not expose collapsed descendants as focusable or visible tree items.
3. Distinguish focus, expansion, and selection states.
4. Use clear accessible names for every tree item.
5. Test deep nesting, dynamically loaded children, and empty branches.

## Verification

Confirm directional navigation, expansion and collapse behavior, focus placement, selection state, and hierarchy announcements with keyboard and representative assistive technologies.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Tree View Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/treeview/
