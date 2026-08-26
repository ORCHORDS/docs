# Stripe Treasury transaction-entry reconciliation

**Issue:** A Treasury integration books the top-level Transaction amount as one accounting line and ignores TransactionEntries. Pending/posted transitions, multiple balance impacts, reversals, and currency/sign semantics then produce a ledger that cannot reproduce the financial account balance.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Object boundary

Stripe Treasury Transactions represent balance-changing activity on a FinancialAccount. TransactionEntries are the individual credit/debit entries associated with that Transaction and contain the detailed balance impact.

Keep these identities separate:

- Transaction ID and status describe the grouped Treasury activity.
- TransactionEntry ID is the immutable ingestion/idempotency key for a ledger line.
- Flow objects explain the business source (for example, an outbound/inbound transfer) and have their own lifecycle.
- Balance and balance-transaction observations are reconciliation evidence, not replacements for entries.

## Ingestion pattern

1. Scope every API read/event to livemode and the correct platform/connected account and FinancialAccount.
2. Upsert the Transaction envelope, then list/ingest all associated entries with pagination.
3. Store integer minor-unit amounts, currency, entry type, effective/created timestamps supplied by Stripe, status context, and canonical object references.
4. Map signs from documented entry semantics. Never infer debit/credit from a localized UI label or from whether the parent flow “felt outgoing.”
5. Post each TransactionEntry exactly once using its Stripe ID plus account/mode as the external key.
6. If a Transaction changes state or gains entries, append/correct through explicit ledger rules. Do not mutate a posted audit trail silently.
7. Process webhooks as wake-up signals. Re-read canonical objects, tolerate duplicates and reordering, and use a cursor/high-water replay job to close delivery gaps.
8. Treat unknown entry types as unapplied reconciliation exceptions, not zero-value success.

## Reconciliation invariant

For each FinancialAccount and currency, sum posted entry impacts over the reconciliation window and compare opening balance + entries to closing balance. Reconcile counts and IDs as well as totals: equal net amounts can conceal a missing debit and missing credit.

Tie every general-ledger posting back to one TransactionEntry and its parent Transaction. Keep pending and posted balances in separate accounts/statuses if the accounting model distinguishes them.

## Operations

Run near-real-time ingestion plus a scheduled overlap-window backfill. Expose aged pending Transactions, missing entry pages, duplicate external keys, currency mismatches, balance variance, late events, and parent flows with no explainable entry set. A manual repair should record actor, reason, before/after data, and Stripe source.

## Verification

Test multi-entry Transactions, pagination, zero/negative values allowed by documented types, pending-to-posted transitions, reversals/returns, webhook replay and reordering, API timeout after successful work, connected-account scoping, and day-boundary timestamps. Inject one missing entry and prove the variance alarm fires.

## Gotchas

- Top-level amount alone is not an audit-ready journal.
- Never use floating-point money.
- A webhook event ID deduplicates a delivery, while an entry ID deduplicates the financial fact.
- Re-fetching cannot replace retention of your accounting decisions and audit history.

## Sources

- [Stripe API — Treasury Transactions](https://docs.stripe.com/api/treasury/transactions)
- [Stripe API — Treasury TransactionEntries](https://docs.stripe.com/api/treasury/transaction_entries)
