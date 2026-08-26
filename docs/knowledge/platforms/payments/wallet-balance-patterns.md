# wallet-balance-patterns

**Issue:** Implementing an internal wallet or balance system for prepaid credits or deposits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some products require users to prepay into a wallet that is drawn down with usage. This requires atomic balance operations to prevent double-spending and negative balances.

## Pattern / Solution
Store balance as an integer (cents) in the database. Use database transactions for all debit operations: SELECT FOR UPDATE the user row, check balance is sufficient, apply debit, insert ledger entry, commit. Use Stripe Customer Balance for real-money wallets that need to interface with Stripe charges.

## Gotchas
Never update balance without a corresponding ledger entry — the ledger is the source of truth, balance is a cached sum. Use idempotency keys for all debit operations. Negative balances should be impossible if SELECT FOR UPDATE is used correctly.

## Related
credits-system-implementation, stripe-metered-billing, payment-reconciliation
