# Form-associated custom elements lifecycle

**Issue:** A custom input looks correct and handles clicks, but it is absent from FormData, ignores form reset and disabled state, bypasses constraint validation, or loses state during restoration. Wrapping it in a hidden input fixes one path while creating duplicate names and lifecycle drift elsewhere.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

The HTML standard lets an autonomous custom element participate in a form through ElementInternals. Use this for reusable controls whose value, validity, labels, form ownership, reset behavior, and state restoration must match native form semantics.

Prefer a native input whenever it meets the product need. A form-associated custom element inherits a substantial accessibility and lifecycle contract; it is not merely a serialization hook.

## Controls and implementation

1. Declare static formAssociated = true on the element class before definition, and call attachInternals once per instance.
2. Keep a single canonical internal value. Call internals.setFormValue whenever that value changes. Pass a second state value only when restoration needs more detail than submission.
3. Use FormData as the form value when one control intentionally submits multiple name/value pairs. Do not also maintain a hidden-input mirror.
4. Implement formAssociatedCallback to react when form ownership changes, including association through a form attribute rather than DOM ancestry.
5. Implement formDisabledCallback and combine its value with the element's own disabled semantics. Disabled form controls must not submit or remain interactable.
6. Implement formResetCallback by restoring the author-defined default, not an arbitrary empty value. Do not emit a user-change event merely because reset ran.
7. Implement formStateRestoreCallback for browser restoration and autocomplete modes. Validate restored state before applying it and keep submission value synchronized.
8. Use internals.setValidity with a meaningful message and anchor when invalid. Clear validity when the condition is resolved; do not rely only on CSS.
9. Provide an accessible name, role, states, keyboard interaction, focus behavior, and label handling equivalent to the native control pattern. ElementInternals can expose semantics but does not invent the UX.

## Verification

Test FormData construction, native submit, requestSubmit, reset, fieldset disabled inheritance, explicit form association, moving between forms, duplicate names, multiple values, required/invalid states, reportValidity, browser restoration, and element upgrade after parsing.

Run keyboard and assistive-technology checks with visible and programmatic labels. Verify a disabled instance neither submits nor responds, and that fallback behavior remains usable when custom-element support or JavaScript initialization fails.

## Gotchas

- Calling setFormValue does not validate or sanitize the value automatically.
- The name comes from the custom element; a missing name means no successful control entry.
- Customized built-in elements have different support constraints; this pattern targets autonomous custom elements.
- Shadow DOM styling and focus delegation do not replace form semantics.

## Official sources

- [WHATWG HTML — Form-associated custom elements](https://html.spec.whatwg.org/multipage/custom-elements.html#custom-elements-face-example)
- [WHATWG HTML — ElementInternals](https://html.spec.whatwg.org/multipage/custom-elements.html#the-elementinternals-interface)
