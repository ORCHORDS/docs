# Android App Functions Execution Boundaries

**Issue:** Exposing app capabilities through App Functions lets system agents invoke actions outside the normal UI path, which can bypass confirmation, authorization, or tenant context if treated like an ordinary method call.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Expose only narrow, user-understandable functions with typed parameters and deterministic validation. At execution, resolve the current signed-in identity and tenant inside the app; never trust caller-supplied identity or object ownership. Separate read-only discovery from mutations and require an in-app confirmation or system-supported approval for destructive, financial, privacy-sensitive, or externally visible actions.

Honor the `CancellationSignal`, bound execution time and result size, and return typed errors without secrets or stack traces. Make retried mutations idempotent. Allow users and administrators to disable functions and ensure disabled state is checked at invocation time.

Treat function metadata as public capability description: exclude secrets, internal endpoints, and sensitive object examples. Apply ordinary audit, rate limiting, abuse detection, and data-retention policy.

## Verification

Test enabled/disabled/default state, unauthenticated user, wrong tenant, malformed and oversized parameters, cancellation before/during execution, repeated invocation, concurrent mutation, process death, offline mode, and confirmation denial. Verify equivalent UI/API authorization and inspect returned/logged data for leakage.

## Gotchas

A trusted platform caller is not proof the requested business action is authorized. App Functions availability varies by platform. Do not expose a generic “execute command” or unrestricted search function.

## Sources

- [Android AppFunctionManager](https://developer.android.com/reference/android/app/appfunctions/AppFunctionManager)
- [Android App Functions package](https://developer.android.com/reference/android/app/appfunctions/package-summary)
