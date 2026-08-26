# CSS field-sizing content for form controls

**Issue:** A form uses JavaScript measurement to resize inputs and textareas, causing layout loops, hydration differences, and broken zoom behavior.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** progressive enhancement; support varies

CSS UI defines `field-sizing: content` so selected form controls can size from their contents. Use it within explicit minimum and maximum constraints; content-sized fields must not destabilize the page or become unusably small when empty.

**Source:** [CSS Basic User Interface Level 4 — field-sizing](https://drafts.csswg.org/css-ui-4/#field-sizing)

## Controls

- set logical `min-inline-size`, `max-inline-size`, and textarea block limits;
- retain a placeholder-independent minimum;
- allow overflow or scrolling once the maximum is reached;
- apply only where growing controls improve task completion;
- provide stable fallback dimensions before the declaration.

## Verification

Cover empty, placeholder, long unbroken, multiline, RTL, IME composition, pasted text, validation messages, zoom, font swap, and unsupported browsers. Check neighboring controls do not jump beyond the layout budget.

## Gotchas

Intrinsic sizing is not input validation. Placeholder and replaced-control behavior can vary. Resizing on every character may still cause surrounding layout work, so measure complex forms.
