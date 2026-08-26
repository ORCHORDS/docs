# stripe-usage-based-billing

**Issue:** Designing usage-based billing with the Stripe Billing Meter API
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe introduced the Billing Meter API to replace legacy usage records with a more robust event ingestion pipeline with deduplication and aggregation built in.

## Pattern / Solution
```typescript
// Emit a meter event
await stripe.billing.meterEvents.create({
  event_name: 'api_request',
  payload: {
    stripe_customer_id: customerId,
    value: '1',
  },
  identifier: `req_${requestId}`, // idempotency
});

// Meter configured in Dashboard: aggregate by sum, reset monthly
```

## Gotchas
- Events are immutable — plan your event schema before going live
- Meter events have a short ingestion delay before appearing in the dashboard
- Use `identifier` field for idempotent deduplication on retries
- Legacy `subscriptionItems.createUsageRecord` still works but prefer Billing Meter for new projects

## Related
- `stripe-metered-billing.md`
- `stripe-tiered-pricing.md`
