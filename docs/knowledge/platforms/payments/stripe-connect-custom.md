# stripe-connect-custom

**Issue:** Using Stripe Connect Custom accounts for full platform control
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Custom accounts give your platform full control over the UX and dashboard, but you are responsible for building the onboarding flow and handling compliance.

## Pattern / Solution
```typescript
// Create a Custom account
const account = await stripe.accounts.create({
  type: 'custom',
  country: 'US',
  capabilities: {
    card_payments: { requested: true },
    transfers: { requested: true },
  },
});

// Use Stripe.js to collect sensitive info (avoid touching raw account numbers)
// Then update the account with business info
await stripe.accounts.update(account.id, {
  business_type: 'individual',
  individual: {
    first_name: 'Jane',
    last_name: 'Doe',
    email: 'jane@example.com',
    dob: { day: 1, month: 1, year: 1990 },
    address: { line1: '123 Main St', city: 'Austin', state: 'TX', postal_code: '78701', country: 'US' },
    ssn_last_4: '0000', // use Stripe.js for full SSN
  },
});
```

## Gotchas
- You must build the entire KYC flow — Stripe does not provide UI for Custom accounts
- Platform assumes full liability for Custom account compliance
- Use Stripe.js for collecting sensitive identity data to avoid PCI/KYC scope
- `requirements.currently_due` tells you exactly what Stripe needs to enable charges

## Related
- `stripe-connect-express.md`
- `stripe-connect-platform.md`
