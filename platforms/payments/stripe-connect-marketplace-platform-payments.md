# Stripe Connect — Marketplace Platform Payments

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Content creators on example.com cannot receive payouts, platform
fees are not being deducted correctly, or connected account
onboarding is dropping users mid-flow.

## Context

example.com operates as a marketplace: the platform collects
payments from subscribers and fans, retains a fee, then routes
the remainder to creator accounts. This requires Stripe Connect.
Our Workers API sits at `api.example.com` (Cloudflare) and never
touches raw card data. All Stripe calls originate server-side
using the secret key stored in Workers Secrets.

## 1. Connected Account Types

Choose based on how much control and liability the platform needs.

```
┌──────────────┬─────────────┬───────────────┬──────────────┐
│ Type         │ Onboarding  │ Dashboard     │ Liability    │
├──────────────┼─────────────┼───────────────┼──────────────┤
│ Standard     │ Stripe-hosted│ Creator owns  │ Creator      │
│ Express      │ Stripe-hosted│ Limited view  │ Shared       │
│ Custom       │ Platform owns│ None (embed)  │ Platform     │
└──────────────┴─────────────┴───────────────┴──────────────┘
```

For example.com, **Express** is the right default. Creators get
a Stripe-hosted KYC flow; the platform controls branding and
retains responsibility for disputes. Custom accounts add
regulatory overhead (money transmitter considerations) that
outweighs the UI benefit at current scale.

## 2. Creating Connected Accounts

```typescript
// workers/src/payments/connect.ts
export async function createExpressAccount(
  creatorEmail: string,
  countryCode: string,
): Promise<string> {
  const account = await stripe.accounts.create({
    type: "express",
    country: countryCode,
    email: creatorEmail,
    capabilities: {
      card_payments: { requested: true },
      transfers: { requested: true },
    },
    settings: {
      payouts: { schedule: { interval: "weekly", weekly_anchor: "friday" } },
    },
  });
  return account.id; // store in D1 against creator profile
}

export async function buildOnboardingLink(
  accountId: string,
  returnUrl: string,
  refreshUrl: string,
): Promise<string> {
  const link = await stripe.accountLinks.create({
    account: accountId,
    refresh_url: refreshUrl,
    return_url: returnUrl,
    type: "account_onboarding",
  });
  return link.url;
}
```

Store `account.id` in D1 (`creator_stripe_account_id`). The
onboarding link expires after 24 hours; regenerate on `refresh_url`
hit.

## 3. Platform Fees — application_fee_amount

Use destination charges. The platform charges the customer; Stripe
automatically routes funds minus the fee to the connected account.

```typescript
// Destination charge: platform takes 20 %
export async function chargeSubscriber(
  amountCents: number,
  currency: string,
  paymentMethodId: string,
  customerId: string,
  connectedAccountId: string,
) {
  const fee = Math.round(amountCents * 0.20);
  return stripe.paymentIntents.create({
    amount: amountCents,
    currency,
    customer: customerId,
    payment_method: paymentMethodId,
    confirm: true,
    application_fee_amount: fee,
    transfer_data: { destination: connectedAccountId },
  });
}
```

Do **not** use `on_behalf_of` unless you also set `transfer_data`.
Omitting `transfer_data` leaves funds on the platform account
permanently.

## 4. Separate Charge + Transfer Flow

Use when the platform needs to batch transfers or defer them
(e.g., hold during a dispute window).

```typescript
// Step 1 — charge platform account
const pi = await stripe.paymentIntents.create({
  amount: 5000,
  currency: "usd",
  confirm: true,
});

// Step 2 — transfer after N days
await stripe.transfers.create({
  amount: 4000, // platform keeps 1000
  currency: "usd",
  destination: connectedAccountId,
  source_transaction: pi.latest_charge as string,
});
```

The `source_transaction` pin prevents double-spend: Stripe
verifies the originating charge is settled before releasing.

## 5. Webhook Scoping

Platform-level webhooks (`whsec_...` on the main account) fire
for all accounts. Account-level webhooks fire only for that
connected account. For example.com we use platform-level and
filter on `account` field.

```typescript
// worker webhook handler
const event = stripe.webhooks.constructEvent(
  rawBody,
  request.headers.get("stripe-signature")!,
  env.STRIPE_WEBHOOK_SECRET,
);
const connectedAccountId = (event as any).account; // present on Connect events
```

Key events to handle:
- `account.updated` → re-check `charges_enabled`, `payouts_enabled`
- `payment_intent.succeeded` → credit creator balance in D1
- `payout.failed` → alert creator, pause scheduled payouts

## 6. 1099-K Identity Verification

Stripe files 1099-K for US Express/Custom accounts exceeding
IRS thresholds ($600 gross for 2026). Ensure these fields are
collected during onboarding:

```
required for 1099-K:
  individual.ssn_last_4      (or full SSN via Stripe-hosted)
  individual.dob
  individual.address (line1, city, state, postal_code)
  business_type = "individual" | "sole_prop"
```

Query `account.requirements.eventually_due` after onboarding
and surface missing fields in the creator dashboard before
January payout cycle.

## Anti-patterns

- Storing `application_fee_amount` as a percentage string in
  config — always compute in cents at charge time to avoid
  floating-point drift.
- Using a single platform webhook secret for both live and test
  modes — Stripe issues separate secrets; store both in Workers
  Secrets (`STRIPE_WEBHOOK_SECRET_TEST` / `_LIVE`).
- Calling `stripe.transfers.create` without `source_transaction`
  on destination charges — funds may be pulled from uninvested
  platform balance, creating a shortfall.

## Gotchas

- Express accounts in restricted countries (Russia, Belarus,
  Iran) will have `charges_enabled: false` immediately after
  creation; check at login, not just after onboarding.
- `payout.schedule` changes take effect at the next payout
  cycle, not immediately. Creators changing bank accounts see
  a 7-day hold on the new bank.
- `application_fee_amount` cannot exceed the charge amount; a
  100 % fee causes a Stripe API error, not a silent zero-out.
- `transfer_data.destination` must match the account country's
  currency for automatic settlement. USD-only platform sending
  to a EUR-only account requires explicit currency conversion.

## Verification

```bash
# confirm connected account is charges-enabled
stripe accounts retrieve acct_XXXX \
  --api-key $STRIPE_SECRET_KEY \
  | jq '.charges_enabled, .payouts_enabled'

# list recent transfers for an account
stripe transfers list \
  --destination acct_XXXX \
  --limit 5
```

Check D1 `creator_payments` table matches Stripe Dashboard
totals within 1 cent for the previous rolling 24 h.

## Related

- `payment-fraud-detection-velocity-checks.md`
- `subscription-billing-lifecycle-management.md`
- `pci-dss-scope-reduction-tokenization.md`

## Source URLs (verified 2026-08-17)

- https://stripe.com/docs/connect/account-types
- https://stripe.com/docs/connect/destination-charges
- https://stripe.com/docs/connect/separate-charges-and-transfers
- https://stripe.com/docs/connect/webhooks
- https://stripe.com/docs/connect/1099-K
