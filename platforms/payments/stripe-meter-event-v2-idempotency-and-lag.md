# Stripe Meter Event v2 Idempotency and Processing Lag

**Issue:** Usage events can be accepted synchronously yet aggregated asynchronously, while duplicate or late producer events inflate billing if identifiers and correction policy are weak.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Map each meter event name to one reviewed meter and send the exact customer/value payload keys configured there. Generate a globally unique, stable identifier from the source usage event; Stripe documents uniqueness enforcement within a rolling window, so keep a durable internal deduplication ledger beyond that provider window.

Treat a successful API response as validation/acceptance, not immediate invoice visibility. Preserve event time, ingestion time, source sequence, quantity in an exact numeric representation, and tenant/customer mapping. For sustained rates beyond the synchronous endpoint's documented limit, use Stripe's meter event stream rather than uncontrolled retry concurrency.

Queue submissions, retry only retryable failures with the same identifier, and reconcile source totals to Stripe meter summaries before invoice finalization. Define an explicit cancellation/correction path; never send a negative or compensating event unless the configured meter semantics and API support it.

## Verification

Test duplicate identifier, same payload/new identifier, malformed mapping, wrong customer, clock skew, late event, timeout after acceptance, rate throttling, async aggregation lag, correction, and replay after 24 hours. Prove invoice quantities match the source ledger across billing boundaries.

## Gotchas

Synchronous validation is not synchronous aggregation. Provider dedupe windows do not replace permanent source idempotency. Usage payloads are financial records; keep secrets and customer-sensitive detail out of identifiers.

## Sources

- [Stripe v2 meter event API](https://docs.stripe.com/api/v2/billing/meter_events/create)
- [Stripe meter event streams](https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage-api)
- [Stripe usage-based billing](https://docs.stripe.com/billing/subscriptions/usage-based)
