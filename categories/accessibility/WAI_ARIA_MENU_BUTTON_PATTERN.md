---
title: "WAI-ARIA Menu Button Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Menu Button Pattern

## Purpose

Provide public implementation guidance for a button that opens a menu using the WAI-ARIA Authoring Practices Guide (APG) menu button pattern.

## Pattern baseline

A menu button is a button that opens a menu. The controlling element uses button semantics and communicates that it opens a menu.

For an ARIA implementation:

- the trigger has role `button` or equivalent native button semantics;
- `aria-haspopup` is set to `menu` or `true`;
- `aria-expanded` reflects whether the menu is open;
- focus moves into the menu when it opens according to the chosen interaction model;
- menu items use appropriate menu-item roles and keyboard behavior.

## Keyboard interaction

When focus is on the menu button:

- `Enter` and `Space` open the menu and place focus in it;
- `Down Arrow` may open the menu and focus the first item;
- `Up Arrow` may open the menu and focus the last item.

Once focus is inside the menu, menu keyboard interaction rules apply, including directional navigation and `Escape` for closing and returning focus where appropriate.

## Implementation guidance

1. Prefer a native `<button>` for the trigger when possible.
2. Keep `aria-expanded` synchronized with visible state.
3. Do not expose menu roles for ordinary site navigation unless the interaction genuinely follows the menu pattern.
4. Ensure focus is visible and restored predictably when the menu closes.
5. Test with keyboard-only operation and representative assistive technologies.

## Verification

Confirm that the trigger’s accessible name is meaningful, state changes are exposed, all menu items are keyboard reachable, `Escape` behavior is predictable, and focus does not become lost when the menu closes.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Menu Button Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/
