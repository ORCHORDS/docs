# stripe-metered-billing

**Issue:** Implementing metered (pay-per-use) billing with Stripe legacy usage records
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You bill based on actual usage (API calls, seats, GB) reported at the end of each period using the legacy subscriptionItems usage record API.

## Pattern / Solution
```typescript
// Report usage
await stripe.subscriptionItems.createUsageRecord(subscriptionItemId, {
  quantity: unitsUsed,
  timestamp: Math.floor(Date.now() / 1000),
  action: 'increment', // or 'set'
});

// Price config (via dashboard):
// billing_scheme: 'per_unit', usage_type: 'metered', aggregate_usage: 'sum'
```

## Gotchas
- `action: 'set'` replaces the current period total; `'increment'` adds to it
- Usage records cannot be deleted — report corrections with `action: 'set'`
- Metered prices cannot be used in Checkout `mode: 'payment'`; use `mode: 'subscription'`
- Use an idempotency key on usage reports to prevent double-counting on retries
- Consider the newer Billing Meter API for new projects

## Related
- `stripe-usage-based-billing.md`
- `stripe-subscription-lifecycle.md`
