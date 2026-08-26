# Sanitizer API Safe HTML Insertion

**Issue:** Assigning user-controlled markup through `innerHTML` or an unsafe parser creates XSS, DOM clobbering, spoofing, and clickjacking surfaces.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

When supported, use `Element.setHTML()`, `ShadowRoot.setHTML()`, or `Document.parseHTML()` for untrusted markup. These safe methods apply sanitization and remove XSS-unsafe elements/attributes even if a custom configuration attempts to allow them. Reuse a reviewed `Sanitizer` instance for a stable allowlist.

Keep allowed elements and attributes minimal for the product feature. Validate URLs and protocols separately, add link rel policies, and combine with Content Security Policy and Trusted Types as defense in depth. For unsupported browsers, use a maintained sanitizer with the same policy; do not silently fall back to `innerHTML`.

Reserve methods named `*Unsafe` for already trusted, policy-controlled markup and make that trust boundary explicit in code review.

## Verification

Use a maintained XSS corpus covering script elements, event attributes, SVG/MathML, malformed nesting, foreign content, javascript/data URLs, DOM clobbering names, mutation-XSS, and custom elements. Compare native and fallback policies and test browser upgrades. Confirm intended rich text and accessibility semantics survive.

## Gotchas

Sanitization is not contextual authorization and does not make arbitrary URLs safe. A configuration mixing allow and remove forms can be invalid. Native support is limited, so feature detection is mandatory.

## Sources

- [MDN Element.setHTML](https://developer.mozilla.org/en-US/docs/Web/API/Element/setHTML)
- [MDN Sanitizer](https://developer.mozilla.org/en-US/docs/Web/API/Sanitizer)
- [HTML Sanitizer API specification](https://wicg.github.io/sanitizer-api/)
