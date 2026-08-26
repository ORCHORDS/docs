# Stripe Connect reserve hold lifecycle

**Issue:** A platform treats a connected-account reserve as a balance subtraction or a permanent configuration flag. Holds, plans, releases, refunds, and balance transactions then fail to reconcile, and disabling a plan unexpectedly returns risk funds.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** private preview — eligibility-gated

## Product boundary

Stripe connected-account reserves are eligibility-gated private-preview functionality. Build behind an account capability/feature flag and do not assume API availability in every region, account, mode, or API version.

Model distinct objects and events:

- a **reserve plan** defines future hold behavior;
- a **reserve hold** associates reserved funds with eligible activity;
- a **release** returns held funds according to lifecycle/action;
- related balance transactions explain the ledger movement.

A reserve is risk liquidity, not earned revenue, a refund, a payout, or an application-level wallet balance.

## Lifecycle controls

1. Discover platform/account eligibility before showing controls or making calls.
2. Store Stripe object IDs, connected account, livemode, currency, source charge/payment relationship, status, amount held/released, timestamps, and raw versioned event reference.
3. Create or change plans with authenticated operator intent, bounded percentage/amount policy, and an idempotency key.
4. Treat disabling a reserve plan as financially consequential: Stripe documents that disabling immediately releases associated holds. Require impact preview and step-up approval.
5. Enforce the documented maximum hold duration (up to 180 days) in local monitoring; do not invent indefinite holds.
6. Reconcile asynchronous state from Stripe webhooks/API reads and balance transactions. Never mark funds reserved solely because the create request returned without a transport error.
7. Process webhook deliveries idempotently and tolerate out-of-order arrival. Re-fetch the canonical object when an event would move state backward.
8. Keep platform risk policy, connected-account communication, and legal/contract permissions outside the API abstraction.

Partial refunds need explicit reconciliation. Stripe notes that a refund smaller than the associated hold does not automatically release that hold. Do not infer “refund happened” means “corresponding reserve is gone.”

## Accounting

Post double-entry movements from canonical balance transaction data. Preserve currency and sign; never net unrelated holds/releases into one opaque daily number. Reconcile opening reserved balance + holds - releases = closing reserved balance for each connected account/currency, then compare to Stripe's exposed balances and object states.

Separate “API object exists,” “funds moved,” and “ledger posted” checkpoints. A retry must not double-post.

## Verification

In test-supported environments, cover plan create/update/disable, hold creation, scheduled/manual release, maximum-duration behavior, full and partial refunds, dispute interaction, webhook replay/reordering, insufficient/changed balance, currency partitioning, and connected-account closure. Verify disabling warnings state the release impact.

## Gotchas

- Preview APIs and field semantics can change; pin and review the Stripe API version/docs.
- A hold is not a chargeback defense or a substitute for negative-balance policy.
- Dashboard state and webhook delivery are observations, not your accounting journal.
- Never mix platform and connected-account object scope.

## Sources

- [Stripe Docs — Connected account reserves](https://docs.stripe.com/connect/connected-account-reserves)
- [Stripe API — Reserves](https://docs.stripe.com/api/reserves)
