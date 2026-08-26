# CSS if() conditional values

**Issue:** CSS Values Level 5 drafts an `if()` value function for style, media, and supports conditions inside property values. Using it as an application decision engine or without a valid fallback can make declarations disappear in unsupported or changing implementations.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation
Keep the baseline declaration first, then place the conditional value inside an exact `@supports` guard. Conditions may select presentation tokens only; authorization, feature entitlement, content inclusion, and analytics assignment stay in application logic. Include an else result and ensure every branch is type-valid for the property.

## Verification
Test every branch, no-match, unsupported parser, custom-property substitution, invalid-at-computed-value time, nested conditions, media changes, forced colors, and reduced motion. Assert the baseline remains usable.

## Gotchas
A browser can parse a function before implementing every condition form. CSS conditions are environmental presentation choices, not stable persisted state.

## Sources
- W3C CSSWG, [CSS Values and Units Level 5 — if()](https://www.w3.org/TR/css-values-5/#if-notation)
- W3C CSSWG, [CSS Conditional Rules Level 5](https://www.w3.org/TR/css-conditional-5/)
