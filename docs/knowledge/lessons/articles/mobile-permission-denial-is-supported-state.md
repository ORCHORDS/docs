# Mobile permission denial is a supported product state

**Issue:** A feature treats permission denial as an exception, repeatedly prompts, or leaves the user in a dead-end screen.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

Design every runtime permission as a state machine: not determined, granted with possible scope, denied, restricted, and later revoked. The core experience must either degrade usefully or explain why the feature cannot operate.

**Sources:** [Android permissions best practices](https://developer.android.com/training/permissions/usage-notes) · [Apple protecting user privacy](https://developer.apple.com/documentation/uikit/protecting-the-user-s-privacy)

## Apply

- ask in context after a user action and request the narrowest capability;
- separate approximate/limited/selected access from full access;
- keep a manual input/import path when feasible;
- stop collection immediately when access is revoked;
- send users to settings only with a clear reason and without loops;
- keep server entitlements independent from local permission UI.

## Verify

Test first request, denial, permanent denial, limited selection, one-time grant, revocation in settings, OS upgrade, parental/enterprise restriction, and account switch. Analytics must record coarse states without sensitive permission-derived data.

## Gotchas

A previously granted permission can disappear while the app is inactive. A rationale screen is not consent. Avoid dark patterns that make denial appear to break unrelated functionality.
