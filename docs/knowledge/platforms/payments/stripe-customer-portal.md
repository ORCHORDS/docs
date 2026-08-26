# stripe-customer-portal

**Issue:** Setting up the Stripe Customer Portal for self-service subscription management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Customers need to update payment methods, download invoices, and cancel subscriptions without contacting support.

## Pattern / Solution
```typescript
// Create a portal session
const portalSession = await stripe.billingPortal.sessions.create({
  customer: customerId,
  return_url: 'https://example.com/account',
});
return Response.redirect(portalSession.url, 303);
```

Configure in Dashboard > Settings > Billing > Customer portal:
- Enable/disable plan switching
- Set cancellation options (immediate, end of period, pause)
- Configure allowed payment method types

## Gotchas
- Portal URL is single-use and expires — generate it fresh on each click
- The portal does not support custom webhooks — listen to `customer.subscription.updated` to sync state
- Cancellation behavior is set in Dashboard, not per-session; set it carefully for your business model
- Portal sessions cannot be used by customers without an existing Stripe customer ID

## Related
- `stripe-subscription-lifecycle.md`
- `stripe-cancellation-flow.md`
- `stripe-upgrade-downgrade.md`
