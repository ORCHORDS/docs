# Viewport Width Does Not Identify Input Modality

**Issue:** A narrow viewport is not proof of touch input, and a wide viewport is not proof of mouse and keyboard. Hybrid laptops, tablets with trackpads, accessibility devices, TVs, and windowed desktop layouts cross those assumptions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Use viewport conditions for layout and capability signals for interaction enhancement, while keeping essential actions operable by touch, pointer, and keyboard. Device labels such as “mobile” and “desktop” are unreliable proxies for what a user can do.

## Controls

- Make every essential action available without hover.
- Preserve keyboard focus order, visible focus, and semantic activation independently of pointer media queries.
- Use `pointer` and `hover` for the primary pointing device and `any-pointer` or `any-hover` only as evidence that an additional device exists.
- Size targets for coarse input without shrinking them merely because a fine secondary pointer is present.
- React to capability-query changes during a session; peripherals can be attached or removed.
- Keep layout breakpoints based on content needs rather than named device classes.
- Do not use capability queries as authorization, analytics identity, or a source of accessibility truth.

## Verification

- Run the same responsive layouts with touch-only, mouse-only, keyboard-only, stylus, and mixed touch-plus-mouse input.
- Attach and remove a pointer while the page is open and verify essential controls remain reachable.
- Test zoom, split-screen, landscape, and narrow desktop windows.
- Assert hover-revealed content is also available through focus and activation.

## Gotchas

`pointer` and `hover` describe a primary pointing device, not keyboards. `any-hover: hover` does not mean hover is convenient for the user’s current interaction. JavaScript user-agent detection cannot repair an inaccessible interaction design.

## Official sources

- [W3C Media Queries Level 5: interaction media features](https://www.w3.org/TR/mediaqueries-5/#mf-interaction)
- [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/)
