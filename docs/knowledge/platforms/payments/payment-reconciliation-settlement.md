# Payment Reconciliation and Settlement

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your finance team spends days each month manually matching payment
processor reports against your internal transaction database. Discrepancies
go unresolved for weeks. Refunds, partial captures, and currency
conversions create mismatches that are discovered only during month-end
close. You cannot answer "did we receive the correct settlement for
transaction X?" without manual investigation.

## Context

Payment reconciliation is the process of matching your internal
transaction records against payment processor settlement reports to ensure
every charge, refund, and payout is accounted for correctly. In 2026,
reconciliation is becoming an engineering function rather than a purely
finance one — driven by payment method diversity, real-time settlement
expectations, and the complexity of multi-processor architectures. AI-
powered reconciliation can achieve 80% faster audit-to-cash cycles and
up to 100x faster settlement matching.

## Reconciliation types

### 1. Transaction-level reconciliation

Match every individual transaction in your system against the
corresponding record in the processor's settlement report.

```
Your DB: order_123 → charge $50.00 → captured → settled
Stripe:  ch_abc   → $50.00      → captured → payout po_xyz

Match on: amount, date, transaction ID mapping
```

### 2. Settlement reconciliation

Match processor payouts (bank deposits) against the sum of individual
transactions minus fees, refunds, and chargebacks.

```
Stripe payout: $4,850.00 on 2026-08-15
  = Sum of charges ($5,000.00)
  - Processing fees ($120.00)
  - Refunds ($30.00)
  = $4,850.00 ✓
```

### 3. Cross-processor reconciliation

When using multiple payment processors, reconcile that every transaction
is recorded in exactly one processor's settlement — no duplicates (double
charges) and no gaps (missing settlements).

## Reconciliation pipeline

```
1. Ingest     → Pull settlement reports from each processor (API/SFTP)
2. Normalize  → Map processor-specific formats to internal schema
3. Match      → Join on transaction ID, amount, date, currency
4. Flag       → Identify mismatches, missing records, duplicates
5. Investigate → Route exceptions to finance/engineering
6. Resolve    → Adjust internal records or dispute with processor
7. Report     → Generate reconciliation summary for accounting
```

### Automated matching rules

```
Rule 1: Exact match — same amount, same currency, matching transaction ID
Rule 2: Partial match — amount within tolerance (FX rounding: ±$0.02)
Rule 3: Fee-adjusted match — charge amount minus known fee structure
Rule 4: Refund offset — charge + refund net to expected settlement
Rule 5: Split match — one payout maps to multiple transactions
```

## Engineering implementation

### Webhook-driven reconciliation

Instead of batch-processing settlement reports, use processor webhooks to
reconcile in near-real-time:

```typescript
// Stripe webhook handler for reconciliation
async function handlePayoutPaid(event) {
  const payout = event.data.object;
  const balanceTransactions = await stripe.balanceTransactions.list({
    payout: payout.id,
  });

  for (const bt of balanceTransactions.data) {
    await reconciliationService.match({
      processorId: bt.source,
      amount: bt.amount,
      fee: bt.fee,
      net: bt.net,
      currency: bt.currency,
      payoutId: payout.id,
      settledAt: new Date(payout.arrival_date * 1000),
    });
  }
}
```

### Idempotent reconciliation

Settlement reports may contain duplicate entries or be re-delivered.
Reconciliation must be idempotent — processing the same report twice
should not create duplicate matches or false mismatches.

## Common mismatch causes

| Mismatch type | Cause | Resolution |
|---|---|---|
| Amount differs | FX rounding, partial capture, tax adjustment | Check FX rate and capture amount |
| Missing in processor | Transaction not yet settled (timing) | Wait for next settlement cycle |
| Missing in your DB | Webhook failure, race condition | Replay missed webhooks |
| Duplicate | Retry logic created duplicate charge | Refund duplicate, fix retry logic |
| Fee mismatch | Interchange++ pricing, volume discount | Verify fee schedule with processor |

## Anti-patterns

- **Manual spreadsheet reconciliation** — matching transactions in Excel
  does not scale beyond a few hundred transactions per month. Automate
  with code.
- **Reconciling only monthly** — discovering a systematic billing error
  30 days later means 30 days of incorrect charges. Reconcile daily or
  on every settlement.
- **Ignoring sub-cent differences** — FX conversions and fee calculations
  create sub-cent rounding differences. Set a tolerance threshold
  (e.g., ±$0.05) and auto-match within tolerance.
- **No exception workflow** — flagging mismatches without a process to
  investigate and resolve them creates an ever-growing backlog. Route
  exceptions to owners with SLAs.

## Gotchas

- **Settlement timing** — processors settle on different schedules (Stripe:
  T+2, Adyen: configurable, PayPal: T+1). Cross-processor reconciliation
  must account for different settlement windows.
- **Currency conversion timing** — the FX rate at charge time differs from
  the rate at settlement time. Settlement amounts in your base currency
  may differ from the original charge conversion.
- **Chargebacks and disputes** — chargebacks appear as negative settlement
  items weeks after the original transaction. Reconciliation must handle
  retroactive adjustments.
- **Platform fees (Stripe Connect)** — marketplace platforms with
  connected accounts have multi-party settlement flows. Reconciliation
  must track platform fees, application fees, and connected account
  payouts separately.

## Verification

- Reconciliation runs daily (or per settlement cycle) without manual
  intervention.
- Mismatch rate is below 0.1% of total transaction volume.
- Exceptions are investigated and resolved within 48 hours (SLA).
- Monthly reconciliation summary is generated for accounting close.
- Multi-processor transactions are verified for no duplicates or gaps.
- FX rounding tolerance is defined and applied consistently.

## Related

- `documentation/docs/policies/payments/stripe-webhook-integration.md`
- `documentation/docs/policies/payments/cross-border-payment-routing.md`
- `documentation/docs/policies/payments/refund-chargeback-handling.md`

## Source URLs (verified 2026-08-16)

- Reconciliation as engineering function — https://y.uno/en/blog/reconciliation-is-becoming-an-engineering-function-not-a-finance-one
- Optimus reconciliation guide — https://optimus.tech/blog/mastering-payment-reconciliation-in-2026-7-key-considerations-for-merchants
- AI-powered reconciliation — https://optimus.tech/blog/top-ai-powered-payment-reconciliation-platforms-in-2026
- Lunos automated reconciliation — https://www.lunos.ai/blog/best-automated-payment-reconciliation-software
