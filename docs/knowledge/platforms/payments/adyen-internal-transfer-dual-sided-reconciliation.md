# Adyen internal transfer dual-sided reconciliation

**Issue:** An internal balance-account transfer emits source and target webhook streams. Treating every event as a new transfer doubles amounts, while treating `authorised` as booked exposes funds before the ledger movement is final.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Model one logical transfer with two account perspectives. Key records by provider transfer ID plus balance account and direction; preserve the platform reference and beneficiary reference separately. Apply `received`, `authorised`, `booked`, failed, and returned states through an explicit monotonic/event-aware state machine rather than arrival order.

Pair outgoing and incoming views by transfer identity and amount/currency, but post ledger movement only from the designated booked evidence. Reconcile transaction webhooks for actual debits/credits separately from transfer-status webhooks. A return is a modification of the original transfer: link its event and reverse the appropriate entries instead of creating an unrelated payment.

## Verification

Test out-of-order and duplicate created/updated events, only one side arriving, received-to-failed, authorised delay, booked on both sides, same-account rejection, insufficient funds, scheduled and on-demand transfers, partial evidence loss, return received/authorised/booked, and replay after recovery. Assert source plus target nets to zero per currency.

## Gotchas

Two webhook views do not mean two fund movements. `authorised` indicates reservation, not final booking, and webhook arrival order is not a ledger ordering guarantee.

## Sources

- Adyen Docs, [Webhooks for internal funds transfers](https://docs.adyen.com/platforms/internal-fund-transfers/internal-transfer-webhooks/)
- Adyen Docs, [Track transactions with webhooks](https://docs.adyen.com/platforms/transfer-transactions/track-webhooks)
