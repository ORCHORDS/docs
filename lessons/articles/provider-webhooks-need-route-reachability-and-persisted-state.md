# provider-webhooks-need-route-reachability-and-persisted-state

**Issue:** A provider callback URL is configured, but no deployed route handles it or no persisted local state exists to validate the event.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Lesson

A webhook integration is not complete when the provider dashboard accepts a URL. The route must be present in the deployed router, reachable under the intended method/path, authenticated, and bound to state that was persisted before the provider event arrives.

This lesson comes from [example-org/example-repo commit <commit-sha>](https://github.com/example-org/example-repo).

## Apply

- register callback routes in source-controlled routing configuration;
- persist the expected intent/provider reference before accepting the event;
- add deployment tests that reach the exact method/path with a valid test payload;
- reject unknown, unsigned, and state-mismatched events;
- monitor route-level 4xx/5xx and reconciliation gaps;
- treat dashboard configuration changes as reviewed infrastructure changes.

## Verification

- The deployed callback URL resolves to the intended route.
- A known intent completes only through a valid bound event.
- An unknown event has no side effect.
- Route removal or method mismatch is detected before release.

## Related

- `payments/nowpayments-callback-payment-intent-integrity.md`
- `patterns/webhook-signing.md`
