# Stripe Thin Event Hydration and Version Migration

**Issue:** Thin events intentionally omit a full resource snapshot. Handlers that assume snapshot payloads can make decisions from absent or stale fields, while an unplanned webhook-version change can break deserialization.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Verify the webhook signature against the unmodified request body, record the event ID, and acknowledge duplicates idempotently before domain side effects.
- Route thin and snapshot payloads through explicit schemas. Do not infer payload style from whether one expected field happens to be missing.
- For thin events, retrieve the current resource through the documented API and authorize that lookup in the correct account context. Treat the event as a change notification, not a historical snapshot.
- Pin webhook endpoint API versions and keep statically typed SDK versions compatible with the payload version.
- Migrate using separate destinations and dual processing. Compare normalized outcomes without performing the same side effect twice, then cut over with a rollback window.
- Preserve event receipt time, event type, resource identifier, hydration version, and retrieval result for audit. If exact before-state matters, keep an internal ledger rather than expecting it from every thin event.
- Queue hydration with bounded retries and dead-letter handling; respond promptly so an API outage does not trigger uncontrolled webhook redelivery.

## Verification

1. Replay duplicate and out-of-order thin events and confirm exactly-once business effects.
2. Test deleted, inaccessible, and rapidly updated resources between notification and hydration.
3. Run both destinations in test mode and compare decisions, latency, and failure rates before cutover.
4. Confirm version changes are exercised in Workbench/test environments and rollback remains possible.

## Gotchas

- Hydration returns current state, which may be newer than the event.
- Thin events for some v1 resources may still be preview functionality; do not build a production dependency without confirming availability.
- Signature verification must precede parsing or body normalization.

## Sources

- [Stripe — Migrate from snapshot events to thin events](https://docs.stripe.com/webhooks/migrate-snapshot-to-thin-events)
- [Stripe — Handle webhook versioning](https://docs.stripe.com/webhooks/versioning)
- [Stripe — Accounts v2 migration and webhook events](https://docs.stripe.com/connect/accounts-v2/migrate-integration)
