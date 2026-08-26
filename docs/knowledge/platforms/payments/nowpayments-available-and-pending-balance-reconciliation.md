# NOWPayments Available and Pending Balance Reconciliation

**Issue:** Treating the custody `amount` as total owned funds or ignoring `pendingAmount` can overstate withdrawable liquidity and hide payments still being processed.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Poll the authenticated balance endpoint from a server-side reconciliation worker and store each currency's available `amount` and `pendingAmount` separately as a timestamped provider snapshot. Never use pending funds for payout availability. Normalize currency/network identifiers through the provider currency list and preserve decimal precision.

Build the internal balance from immutable payment, conversion, transfer, fee, and payout ledger events. Compare that expected state with provider available-plus-pending totals and classify differences by processing state rather than posting a balancing entry automatically. Require manual review for unexplained or persistent variance.

Use one credential scope per environment, restrict source networks where supported, and keep keys out of logs. Alert on negative/implausible values, pending age beyond objective, sudden asset drift, and reconciliation API failure. Finance-facing reports must state snapshot time and availability status.

## Verification

Test new payment moving through pending to available, conversion, payout reservation/completion/failure, delayed chain confirmation, API timeout, pagination for supporting transaction lists, decimal assets, unknown currency, duplicate ledger event, and credential rotation. Prove reconciliation never triggers a payout itself.

## Gotchas

A balance snapshot is not an accounting ledger and is not atomic with independently fetched transaction lists. Pending is not spendable. Asset valuation changes must remain separate from unit reconciliation.

## Sources

- [NOWPayments API balance and transaction documentation](https://documenter.getpostman.com/view/7907941/2s93JusNJt)
- [NOWPayments custody](https://nowpayments.io/custody)
