# CSS user-valid and user-invalid feedback

**Issue:** Styling every required empty field with `:invalid` paints a new form as erroneous before the person interacts. Replacing validation with color-only `:user-invalid` styling then hides actionable text from assistive technology.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Use native constraints and labels as the validation source. Apply `:user-invalid` and `:user-valid` only as progressive visual enhancement after significant interaction; keep a conservative fallback for engines without support. Do not make success styling mandatory, because user-agent timing is intentionally flexible.

On submission, render a text error associated through `aria-describedby` or `aria-errormessage`, set `aria-invalid` from the same validation result, focus an error summary or the first invalid field according to the product contract, and preserve entered values. Use icons or text in addition to color and maintain focus/forced-colors contrast.

## Verification

Test untouched required fields, typing then blur, correction, form reset, programmatic value changes, submit attempts, custom controls, autofill, screen readers, keyboard-only use, forced colors, zoom, and engines without the selectors. Confirm server errors use the same perceivable error path.

## Gotchas

Selectors expose a user-agent interaction state; they do not validate business rules or announce errors. Exact matching can vary before submission, so application correctness must not depend on the moment the pseudo-class starts matching.

## Sources

- W3C CSSWG, [Selectors Level 4: user-interaction pseudo-classes](https://www.w3.org/TR/selectors-4/#user-pseudos)
- WHATWG, [HTML Living Standard: constraint validation](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#constraint-validation)
