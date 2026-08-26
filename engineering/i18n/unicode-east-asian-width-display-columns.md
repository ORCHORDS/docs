# Unicode East Asian Width and display columns

**Issue:** A terminal, table, or monospace layout assumes every Unicode scalar occupies one column, misaligning CJK text, fullwidth forms, emoji, and combining sequences.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

UAX #11 assigns East_Asian_Width properties for interoperability and legacy layout. It is input to a display-width policy, not a universal pixel or terminal-cell measurement.

**Source:** [Unicode Standard Annex #11: East Asian Width](https://unicode.org/reports/tr11/)

## Controls

- segment grapheme clusters before assigning display cells;
- pin the Unicode data version used by server and client;
- define how Ambiguous characters behave per environment/locale;
- handle combining marks, emoji presentation, ZWJ sequences, and control characters separately;
- prefer actual font/layout measurement for proportional graphical interfaces.

## Verification

Fixtures cover narrow, wide, fullwidth, halfwidth, ambiguous, combining, emoji, and unassigned code points. Compare supported terminal targets and ensure truncation never splits a grapheme cluster or escape sequence.

## Gotchas

East_Asian_Width is not equivalent to `wcwidth` across implementations. Emoji width is environment-dependent. Property assignments can evolve with Unicode versions.
