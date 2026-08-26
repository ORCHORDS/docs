# User activation: transient and sticky gating

**Issue:** A frontend assumes any click-like event permanently unlocks privileged browser APIs. Popup, fullscreen, clipboard, media, and file-picker calls then fail inconsistently because user activation has multiple states, may expire, and can be consumed.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Platform model

The HTML Living Standard tracks two useful states on `navigator.userActivation`:

- `isActive` reports transient activation. It is short-lived and can be consumed by an activation-consuming API.
- `hasBeenActive` reports sticky activation: whether activation has occurred in the relevant window's history. It is not proof that a transient-gated call is currently allowed.

An activation-triggering input is defined by the platform. Synthetic events created by script do not create trusted user activation. A framework's “onClick” abstraction therefore cannot be treated as the security signal; read the browser state and invoke the gated API inside the actual trusted interaction path.

## Implementation pattern

1. Put the gated call directly in the user event handler. Do not await unrelated network work, enqueue a task, or hand control to a timer before calling it.
2. Perform asynchronous preparation before the user acts when possible. The gesture should authorize the final browser call, not start a long preparation chain.
3. Check `navigator.userActivation?.isActive` only as diagnostics or a fast guard. The API call remains authoritative and can still reject.
4. Catch the API's exact exception/rejection and keep the UI recoverable. Show a retry control that creates a new genuine activation.
5. If several calls need transient activation, do not assume one gesture supports all of them. Order the essential call first and verify each target API's consumption rules.
6. Scope state to the current browsing context. Cross-origin frames and activation propagation follow HTML rules; never manufacture a parent/child boolean as a substitute.
7. Keep activation separate from business consent and authorization. A click proves neither an authenticated identity nor permission to perform a server-side action.

## Example

```js
button.addEventListener("click", async (event) => {
  if (!event.isTrusted) return;

  try {
    await navigator.clipboard.writeText(preparedText);
    showCopied();
  } catch (error) {
    showActivationRetry(error);
  }
});
```

Prepare `preparedText` before this handler. Do not fetch it first inside the click handler and assume activation will survive.

## Verification

Test mouse, keyboard, touch, assistive activation, a synthetic event, a delayed task, nested frames, repeated calls, and a call after another consuming API. Assert both success and recoverable rejection. Record API name, activation state at invocation, context origin relationship, and exception class—never clipboard or file contents.

## Gotchas

- Sticky activation is not a reusable transient token.
- A trusted event does not guarantee that every API recognizes that event type as activation.
- Browser support and consumption behavior differ by API; feature-detect and test target browsers.
- Retrying automatically without a new gesture can create a rejection loop.

## Sources

- [HTML Living Standard — Tracking user activation](https://html.spec.whatwg.org/multipage/interaction.html#tracking-user-activation)
