# stripe-connect-express

**Issue:** Onboarding sellers with Stripe Connect Express accounts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Express accounts are the fastest way to onboard sellers/vendors to your platform. Stripe hosts the onboarding flow and dashboard.

## Pattern / Solution
```typescript
// Create an Express account
const account = await stripe.accounts.create({ type: 'express' });

// Generate an onboarding link
const accountLink = await stripe.accountLinks.create({
  account: account.id,
  refresh_url: 'https://example.com/reauth',
  return_url: 'https://example.com/onboarding-complete',
  type: 'account_onboarding',
});

return Response.redirect(accountLink.url, 303);
```

Check account status after return:
```typescript
const account = await stripe.accounts.retrieve(accountId);
const isReady = account.charges_enabled && account.payouts_enabled;
```

## Gotchas
- Account links expire after a few minutes — generate fresh on each click
- `charges_enabled` and `payouts_enabled` can become false again if Stripe needs more info
- Express accounts have a Stripe-hosted dashboard you cannot customize
- Store the `account.id` in your database immediately after creation, not after onboarding

## Related
- `stripe-connect-platform.md`
- `stripe-connect-payouts.md`
