# Dialog closedby Dismissal Policy

**Issue:** A modal closes through Escape, mobile back, outside click, or code without a declared policy, so destructive/unsaved workflows dismiss accidentally while simple dialogs require excessive custom handlers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented
**Compatibility:** `closedby` has limited availability; progressive enhancement is required.

## Control pattern

Declare the native `<dialog>` dismissal contract with `closedby`: `any` permits light dismiss and platform close requests, `closerequest` permits platform/developer close but not outside-click light dismiss, and `none` permits only developer mechanisms. Choose from workflow risk, not visual design.

Use `showModal()` for modal semantics. Route vetoable programmatic closure through `requestClose()` and handle `cancel` for unsaved-state confirmation; use `close()` only when bypassing cancellation is intentional. Always provide a visible accessible action and restore focus. Feature-detect `closedBy` and implement an equivalent fallback without double-handling events.

## Verification

Test outside pointer/touch, Escape, Android back, visible cancel/confirm buttons, form method=dialog, `requestClose()`, nested top-layer elements, unsaved-state veto, assistive technology, modeless dialogs, and unsupported browsers. Confirm the documented action set matches the chosen value.

## Gotchas

Missing/invalid `closedby` is Auto: modal dialogs behave like `closerequest`, modeless dialogs like `none`. Manually removing `open` bypasses normal close behavior. `closedby="none"` without an operable close control traps users. This attribute does not replace focus design or validation.

## Sources

- [WHATWG HTML — dialog closedby](https://html.spec.whatwg.org/dev/interactive-elements.html#the-dialog-element)
- [MDN HTMLDialogElement.closedBy](https://developer.mozilla.org/en-US/docs/Web/API/HTMLDialogElement/closedBy)
