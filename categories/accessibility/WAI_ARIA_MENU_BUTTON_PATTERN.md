# WAI-ARIA APG — Menu Button Pattern

## Purpose

Provide implementation guidance for menu buttons that expose a menu of actions or navigation choices while preserving keyboard and assistive-technology support.

## Pattern summary

A menu button is a button that opens a menu. W3C's ARIA Authoring Practices Guide (APG) describes keyboard behavior and ARIA relationships for the trigger and the menu it controls.

## Keyboard interaction

With focus on the menu button:

- `Enter` opens the menu and places focus on the first menu item.
- `Space` opens the menu and places focus on the first menu item.
- `Down Arrow` may open the menu and move focus to the first menu item.
- `Up Arrow` may open the menu and move focus to the last menu item.

Once the menu is open, use the keyboard interaction defined by the Menu and Menubar pattern.

## Roles, states, and properties

The trigger should expose button semantics. It should indicate that it opens a menu using `aria-haspopup="menu"` or `aria-haspopup="true"`.

Use `aria-expanded="true"` while the menu is displayed and `aria-expanded="false"` while it is hidden. `aria-controls` may be used to reference the controlled menu.

The popup container uses the `menu` role, with menu items using appropriate menu item roles.

## Implementation guidance

1. Prefer semantic HTML buttons for the trigger where possible.
2. Keep focus movement deterministic when opening and closing the menu.
3. Return focus to the invoking control when dismissal requires it.
4. Keep visible state and `aria-expanded` synchronized.
5. Test keyboard behavior, high-contrast rendering, screen-reader announcements, and mobile/touch combinations.
6. Do not treat APG examples as production-ready without compatibility testing.

## Verification

Verify operation with keyboard only, at least one major screen reader, browser zoom, high-contrast or forced-colors settings where applicable, and pointer/touch interaction.

## Sources

- W3C WAI, **Menu Button Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/
- W3C WAI, **Menu and Menubar Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/menubar/
