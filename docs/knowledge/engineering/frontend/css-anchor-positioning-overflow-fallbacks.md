# CSS Anchor Positioning Overflow Fallbacks

**Issue:** Tooltips and popovers positioned beside a trigger can overflow or cover the trigger near viewport and container edges.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Give the anchor a stable `anchor-name`, associate the positioned element with `position-anchor`, and define its preferred `position-area`. Add an ordered `position-try-fallbacks` list using logical-axis tactics such as `flip-block`, `flip-inline`, their combination, position-area values, or reviewed `@position-try` rules.

Design every fallback, including arrow direction, margins, maximum size, and reading direction. If no option fully avoids overflow the browser returns to the original placement, so also constrain size and allow internal scrolling where appropriate. Retain a usable non-anchor-positioning fallback and native dialog/popover semantics.

## Verification

Move anchors to every viewport/container edge and corner; test scrolling, zoom, text expansion, RTL, vertical writing, mobile keyboard, nested scroll containers, and dynamic content growth. Confirm the overlay stays reachable, does not obscure its invoker, and focus/escape/light-dismiss behavior remains correct. Test unsupported browsers.

## Gotchas

Fallbacks are tried in order unless a try-order policy changes selection. Flipping axes without updating decorative arrows produces misleading UI. CSS placement does not solve focus or modal semantics.

## Sources

- [MDN position-try-fallbacks](https://developer.mozilla.org/en-US/docs/Web/CSS/position-try-fallbacks)
- [MDN @position-try](https://developer.mozilla.org/en-US/docs/Web/CSS/@position-try)
- [CSS Anchor Positioning specification](https://drafts.csswg.org/css-anchor-position-1/)
