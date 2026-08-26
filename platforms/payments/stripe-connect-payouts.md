# stripe-connect-payouts

**Issue:** Managing payouts to connected accounts in Stripe Connect
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Connected accounts accumulate balance from charges. Payouts transfer that balance to the connected account's bank account.

## Pattern / Solution
```typescript
// Manual payout to connected account's bank
const payout = await stripe.payouts.create(
  { amount: 5000, currency: 'usd' },
  { stripeAccount: connectedAccountId }
);

// Instant payout (if supported)
const instantPayout = await stripe.payouts.create(
  {
    amount: 5000,
    currency: 'usd',
    method: 'instant',
    destination: debitCardId,
  },
  { stripeAccount: connectedAccountId }
);
```

For automatic payouts: configure payout schedule in Dashboard or via API:
```typescript
await stripe.accounts.update(connectedAccountId, {
  settings: { payouts: { schedule: { interval: 'daily' } } },
});
```

## Gotchas
- Instant payouts require a debit card as the destination, not a bank account
- Payout timing depends on bank processing — typically T+2 for standard
- Failed payouts fire `payout.failed` webhook — check `failure_code` for the reason
- Minimum payout amount varies by currency

## Related
- `stripe-connect-platform.md`
- `stripe-connect-express.md`
