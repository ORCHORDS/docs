# CSS ::details-content disclosure transitions

**Issue:** A native details disclosure is replaced with custom JavaScript solely to animate its content, losing built-in semantics and keyboard behavior.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** progressive enhancement; support varies

CSS Pseudo-Elements defines `::details-content` to style the content wrapper of a `details` element. Keep native `summary` activation and open state as the baseline, then enhance presentation.

**Source:** [CSS Pseudo-Elements Level 4 — ::details-content](https://drafts.csswg.org/css-pseudo-4/#details-content-pseudo)

## Controls

- use a properly labelled first `summary`;
- ensure content works without the pseudo-element;
- combine animations with reduced-motion policy;
- avoid fixed heights that clip localization or zoom;
- keep focusable descendants unavailable only when actually closed.

## Verification

Test keyboard, touch, screen reader, nested disclosures, dynamic content, rapid toggle, deep links, print, reduced motion, long translations, and unsupported engines.

## Gotchas

Animation does not change disclosure semantics. Closed content and focus behavior remain user-agent controlled. New pseudo-element support must not be inferred from generic details support.
