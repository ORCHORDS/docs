# Stripe Thin Events: Fetch and Idempotent Processing

**Issue:** Stripe API v2 thin events intentionally omit a full resource snapshot, so handlers that assume `data.object` contains final business state can make incomplete or stale decisions.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Register an event destination with the intended scope, payload mode, API version, and minimum event-type allowlist. Verify the webhook signature against the unmodified raw request body using the endpoint-specific secret and an official Stripe library.

For a thin event, parse it as an `EventNotification`, branch on its type, and call the supported related-object or full-event fetch method when the handler needs current data. Carry the event `context` into organization-level API requests; helper fetch methods may do this automatically, but unrelated calls require the correct Stripe context.

Persist the event identifier before side effects. Make processing idempotent, return 2xx quickly after durable acceptance, and move slow work to a retryable queue. Authorize business transitions from fetched resource state plus local invariants, not delivery order.

## Verification

Use Stripe CLI thin-event forwarding and sandbox event destinations. Test valid, bad-signature, duplicate, reordered, unknown-new-type, missing-related-object, fetch-timeout, and redelivery cases. Prove an older event cannot revert fulfilled or refunded state and replaying the same event causes no second side effect.

## Gotchas

Snapshot and thin handlers use different payload assumptions and CLI forwarding flags. SDKs can receive a valid event type newer than their generated classes; handle unknown notifications safely and upgrade deliberately. Do not log signing secrets or full sensitive payloads.

## Sources

- [Stripe webhook documentation](https://docs.stripe.com/webhooks)
- [Stripe event destinations and event types](https://docs.stripe.com/event-destinations)
- [Stripe webhook signature guidance](https://docs.stripe.com/webhooks/signature)
