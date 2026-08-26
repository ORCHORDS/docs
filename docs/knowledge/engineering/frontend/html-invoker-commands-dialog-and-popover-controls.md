# HTML Invoker Commands for Dialog and Popover Controls

**Issue:** Handwritten click handlers for dialogs and popovers often omit native focus, dismissal, disabled-button, and accessibility behavior.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use a real `button` with `commandfor` referencing the controlled element and a standard `command` such as `show-modal`, `close`, `request-close`, `show-popover`, `hide-popover`, or `toggle-popover`. Keep the target ID unique and stable.

Prefer `request-close` when the dialog must expose a cancelable close request rather than bypassing application confirmation. Preserve native dialog/popover semantics and provide an explicit close control inside modal content. Custom commands use the `CommandEvent` path but still require authorization and state checks in application code.

Feature-detect support and retain a small progressive-enhancement fallback. Do not attach both fallback and native handlers in a way that toggles twice.

## Verification

Test mouse, touch, keyboard activation, Escape/light-dismiss, disabled controls, removed targets, duplicate IDs, nested top-layer elements, repeated rapid commands, focus return, and unsupported browsers. Verify accessible names, initial/final focus, background inertness for modal dialogs, and cancel handling.

## Gotchas

Invoker commands reduce glue code; they do not decide whether a destructive operation is allowed. A popover is non-modal unless designed otherwise. Closing a dialog visually must also leave application state consistent.

## Sources

- [MDN Invoker Commands API](https://developer.mozilla.org/en-US/docs/Web/API/Invoker_Commands_API)
- [MDN HTMLButtonElement.command](https://developer.mozilla.org/en-US/docs/Web/API/HTMLButtonElement/command)
- [WHATWG HTML command attributes](https://html.spec.whatwg.org/multipage/form-elements.html#attr-button-command)
