# CSS Starting Style and Discrete Entry/Exit Transitions

**Issue:** Elements entering from `display:none` or leaving the top layer often pop in or disappear before opacity or transform transitions complete.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Define the visible end state in the ordinary rule and the entry state with `@starting-style`. Add discrete properties such as `display` and, for top-layer elements, `overlay` to the transition list with `allow-discrete`. Animate opacity or transform for the visual effect while discrete flipping keeps the element rendered for the appropriate interval.

For popovers and dialogs, keep native semantics, focus management, escape behavior, and backdrop behavior. Put the `@starting-style` rule after an equal-specificity open-state rule when cascade order requires it. Provide a no-animation result that remains correct when unsupported.

## Verification

Exercise first insertion, repeated open/close, removal during animation, rapid toggles, nested top-layer elements, and cancellation. Verify `display` becomes non-interactive at the correct point, focus never lands in hidden content, and the backdrop does not vanish early. Test reduced motion, forced colors, zoom, and representative browsers.

## Gotchas

`@starting-style` supplies a starting value; it does not trigger a transition. `allow-discrete` is required for discrete transitions. Broad `transition:all` can animate unintended properties and cause layout work; list properties explicitly.

## Sources

- [MDN @starting-style](https://developer.mozilla.org/en-US/docs/Web/CSS/@starting-style)
- [MDN transition-behavior](https://developer.mozilla.org/en-US/docs/Web/CSS/transition-behavior)
- [CSS Transitions Level 2](https://drafts.csswg.org/css-transitions-2/)
