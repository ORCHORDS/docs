# CSS overscroll chaining and navigation control

**Issue:** Scrolling a nested surface at its boundary unexpectedly scrolls the page or triggers browser navigation gestures, while JavaScript cancellation harms performance and accessibility.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

CSS Overscroll Behavior controls scroll chaining and boundary effects. Apply `contain` or `none` only to deliberate scroll containers and preserve expected page escape and keyboard access.

**Source:** [CSS Overscroll Behavior Module Level 1](https://www.w3.org/TR/css-overscroll-1/)

## Controls

- prefer `overscroll-behavior: contain` before suppressing all effects;
- use logical axis properties where writing modes matter;
- keep modal/dialog scroll locking coordinated with focus containment;
- do not replace native pull-to-refresh/back gestures without a complete product alternative;
- avoid non-passive event cancellation as the default solution.

## Verification

Test touch, wheel, trackpad, keyboard, assistive scrolling, nested boundaries, momentum, browser navigation gestures, RTL, and unsupported engines. Users must be able to reach and leave every scroll region.

## Gotchas

Overscroll behavior does not make an element scrollable. `none` also suppresses boundary affordances. Browser/OS gestures and root-scroller behavior can differ.
