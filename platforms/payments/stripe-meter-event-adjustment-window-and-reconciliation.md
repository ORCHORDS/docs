# Stripe Meter Event Adjustment Window and Reconciliation

**Issue:** Incorrect usage events can overbill customers, but cancellation is asynchronous, identifier-specific, limited to recent events, and cannot rewrite an already finalized invoice.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Assign every meter event a durable unique identifier and store it beside the source usage record, customer, event name, timestamp, value, and ingestion result.
- Validate usage before submission and make retries idempotent. An adjustment should reference the original identifier, not a newly computed guess.
- Detect anomalies quickly enough for Stripe's documented 24-hour cancellation window. Route older errors to a separate credit-note, refund, or customer-support workflow.
- Treat a meter event adjustment as asynchronous. Poll or consume its resulting state until `complete`; do not mark internal usage corrected merely because creation succeeded.
- Restrict adjustment creation to an audited service role. Require a reason, source record, actor, and approval policy proportional to financial impact.
- Reconcile raw usage, accepted events, pending adjustments, completed adjustments, invoice previews, and finalized invoices.
- If using negative usage quantities as an alternative correction, enforce business bounds and remember the cycle result floors at zero.

## Verification

1. Test cancellation of a recent event, an unknown identifier, an event older than 24 hours, duplicate adjustment requests, and a finalized invoice.
2. Confirm correction workers survive retries without canceling unrelated usage.
3. Confirm customer-visible totals match internal ledgers before finalization.
4. Alert on pending adjustments that exceed the normal processing window.

## Gotchas

- Canceling usage already included in a finalized invoice does not correct that invoice.
- A successful API response may still represent a pending adjustment.
- Negative usage and cancellation have different audit and billing consequences.

## Sources

- [Stripe — Configure usage meters and fix incorrect usage](https://docs.stripe.com/billing/subscriptions/usage-based/meters/configure)
- [Stripe API — Meter Event Adjustment object](https://docs.stripe.com/api/v2/billing/meter-event-adjustments/object)
