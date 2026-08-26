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

Provide implementation guidance for an accessible button that opens a menu of actions or choices, based on the W3C WAI-ARIA Authoring Practices Guide (APG).

## Pattern baseline

A menu button is a button that opens a menu. The trigger remains a button, while the popup uses menu semantics and contains menu items.

## Keyboard interaction

For the menu button trigger:

- **Enter** opens the menu and places focus on the first menu item.
- **Space** opens the menu and places focus on the first menu item.
- **Down Arrow** may open the menu and place focus on the first item.
- **Up Arrow** may open the menu and place focus on the last item.

Once the menu is open, keyboard behavior should follow the applicable menu or menubar pattern, including arrow-key navigation, activation, and Escape behavior.

## Roles, states, and properties

The trigger should:

- have role `button`, usually by using a native `button` element;
- expose `aria-haspopup="menu"` or `aria-haspopup="true"`;
- expose `aria-expanded="true"` while the menu is open and `false` when closed;
- use `aria-controls` when useful to identify the popup menu relationship.

The popup should use role `menu`, and its actionable descendants should use the appropriate `menuitem`, `menuitemcheckbox`, or `menuitemradio` role.

## Implementation guidance

- Prefer a native button for the trigger.
- Move focus intentionally when the menu opens; do not leave keyboard users guessing where focus went.
- Return focus to the trigger when the menu closes when that matches the interaction flow.
- Ensure pointer, keyboard, and assistive-technology users receive equivalent menu state changes.
- Do not use menu semantics for ordinary site navigation unless the interaction genuinely behaves like an application-style menu.

## Verification

Test opening, navigating, activating, and closing the menu using keyboard-only interaction and at least one screen reader. Confirm the expanded state and popup relationship are exposed correctly.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Menu Button Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/
