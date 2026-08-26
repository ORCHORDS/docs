# webhook-delivery-is-not-guaranteed

**Issue:** Systems that treat webhook delivery as guaranteed miss events when the receiving endpoint is unavailable
**Date:** 2026-08-11
**Status:** documented

## What happened
A billing system relied on Stripe webhooks to mark invoices as paid. During a 20-minute deployment gap (new pods starting, old pods stopping), the webhook receiver returned 500 errors. Stripe retried several times and then stopped. Dozens of invoices were never marked as paid. Customers were incorrectly blocked from the service.

## The lesson
Webhooks are fire-and-forget from the sender's perspective. Delivery is best-effort with limited retries. Design webhook consumers to handle re-delivery (idempotency) and separately implement a reconciliation job that polls the provider's API to catch any missed events.

## Why it matters
Webhook consumers go down. Network partitions happen. Providers have retry policies that expire. Any system that relies solely on webhooks for state transitions will silently lose events during normal operational events like deployments.

## How to apply
- [ ] Make all webhook handlers idempotent — processing the same event twice must be safe.
- [ ] Persist received webhook events to a table before processing, so you have a record of what arrived.
- [ ] Build a reconciliation job that polls the provider API (e.g., Stripe invoice list) and compares to local state, fixing discrepancies.
- [ ] Return HTTP 200 immediately after persisting the event; process asynchronously to avoid timeouts.
- [ ] Monitor webhook receiver error rates and alert on sustained 4xx/5xx responses.

## Related
- `idempotency-keys-for-all-payment-calls.md`
- `queue-consumers-must-be-idempotent.md`
