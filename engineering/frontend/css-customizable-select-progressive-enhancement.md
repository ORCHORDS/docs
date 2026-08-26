# CSS customizable select with progressive enhancement

**Issue:** Replacing native selects with scripted widgets often loses keyboard, form, accessibility, and platform behavior; the emerging customizable-select model is not universally available.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep a real `<select>` as the form control. Opt in with `appearance: base-select` only inside a feature/support strategy.
- Use the permitted `<button><selectedcontent></selectedcontent></button>` structure and style the picker through `::picker(select)`; preserve a plain native fallback.
- Keep option values stable and server-validate submitted values. Decorative content must not become the only source of an option's accessible name.
- Do not implement a second conflicting keyboard model. Test the browser-provided focus, selection, typeahead, Escape, and form-reset behavior.
- Gate visual enhancements with feature queries or tested browser cohorts, and monitor fallback use.

## Verification

1. Submit, reset, disable, mark required, and restore history/autofill states with and without customization support.
2. Navigate entirely by keyboard and with multiple screen-reader/browser pairs.
3. Test zoom, forced colors, reduced motion, RTL, long translations, mobile touch, and picker viewport edges.
4. Confirm dynamic option changes update `selectedcontent` and the posted value.
5. Run cross-browser visual tests while treating unsupported engines as native-select success, not failure.

## Gotchas

Customizable selects remain limited/experimental in some engines. Styling the closed control and its picker requires different selectors. Rich option markup can create layout or naming surprises. A polyfill that hides the native control may be less reliable than progressive enhancement.

## Sources

- [MDN: Customizable select elements](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Customizable_select)
- [WHATWG HTML: the select element](https://html.spec.whatwg.org/multipage/form-elements.html#the-select-element)
