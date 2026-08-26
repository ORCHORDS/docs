# Screen Wake Lock visibility lifecycle

**Issue:** A recipe, scanner, or presentation requests a screen wake lock once and assumes it remains active. The user agent can release it on visibility loss, low power, policy changes, or other system conditions, leaving the UI's “keep awake” state false.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** draft API; use progressive enhancement

## Controls and implementation

Request `navigator.wakeLock.request("screen")` only in a secure, visible document and after a clear user choice. Retain the sentinel, listen for its `release` event, and reflect actual state in the UI. On visibility returning to `visible`, reacquire only if the user's intent is still active; never loop aggressively after denial.

Release explicitly when the task ends, the route changes, or the component unmounts. Bound duration, explain battery impact, and respect Permissions Policy for embedded content. Provide a non-wake-lock fallback such as a visible instruction or tap-to-resume flow.

## Verification

Test permission denial, unsupported API, tab hide/show, screen lock, power saver, low battery, iframe policy, route navigation, repeated toggles, multiple sentinels, and user-agent initiated release. Confirm state never claims the screen is protected after release.

## Gotchas

Acquisition is advisory: the platform may be unable or unwilling to keep the screen on. A screen wake lock does not keep JavaScript, networking, or background processing alive and should not be used as a substitute for durable jobs.

## Sources

- W3C, [Screen Wake Lock API](https://www.w3.org/TR/screen-wake-lock/)
- W3C, [Permissions Policy](https://www.w3.org/TR/permissions-policy-1/)
