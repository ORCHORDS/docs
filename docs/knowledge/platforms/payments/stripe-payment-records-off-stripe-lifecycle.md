# Stripe Payment Records for off-Stripe payment lifecycles

**Issue:** Marking an invoice paid after processing funds elsewhere can create inconsistent ledgers if the external attempt, guarantee, failure, cancellation, and refund lifecycle is flattened into a boolean.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Model the overall external payment as a Payment Record and each network attempt as a Payment Attempt Record; retain the external processor reference in the supported processor details.
- Make every reporting call idempotent using a durable key derived from the external event/attempt, and persist the Stripe object IDs before acknowledging upstream work.
- Advance states only from authoritative processor events. Do not report guaranteed funds from a client redirect or an unverified callback.
- Reconcile amount, currency, customer, attempt status, refunds, and the invoice attachment independently; off-Stripe funds do not produce Stripe Balance Transactions.
- Pin and test the Stripe API version because Payment Record capabilities and fields have evolved across versions.

## Verification

1. Replay each upstream event and assert no duplicate attempts, refunds, or invoice credits.
2. Exercise failed, canceled, informational, and guaranteed attempts, including attempts arriving out of order.
3. Test partial and multiple refunds and confirm cumulative refunded amounts never exceed the external truth.
4. Compare Payment Records against the external processor settlement file and Stripe invoice state.
5. Upgrade the API version in a test environment and inspect request/response diffs plus webhook payload compatibility.

## Gotchas

Payment Records represent activity; they do not move external money into Stripe or create Balance Transactions. A successful attempt is not automatically proof of settlement or guarantee. Never paste secret API keys into examples or logs. Confirm product/API availability for the account and chosen version before relying on it.

## Sources

- [Stripe API: Payment Records](https://docs.stripe.com/api/payment-record)
- [Stripe API: Payment Attempt Records](https://docs.stripe.com/api/payment-attempt-record)
- [Stripe: Route payments to multiple processors](https://docs.stripe.com/payments/orchestration/route-payments)
