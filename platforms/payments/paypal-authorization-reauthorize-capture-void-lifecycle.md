# PayPal authorization, reauthorization, capture, and void lifecycle

**Issue:** Checkout stores one PayPal authorization ID forever and retries capture after the honor period. Reauthorization creates a new identifier, captures target the stale authorization, or a timeout leads to a duplicate capture.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Time and identity model

For authorize-intent checkout, PayPal documents an authorization validity period of 29 days and an initial three-day honor period. Capture as soon as fulfillment allows. If capture cannot occur during the honor period, reauthorization can renew the honor period subject to PayPal's timing/rules.

A successful reauthorization returns a new authorization ID. Replace the active capture target while retaining lineage to the prior ID. Do not capture or void the stale identifier as if reauthorization mutated it in place. A late reauthorization cannot extend beyond the remaining authorization validity.

## State machine

Track order, original authorization, each reauthorization, captures, refunds, and void as related but distinct resources. Suggested states are local projections only; canonical PayPal status and webhook/API evidence control transitions.

1. Create/approve the order with authorize intent and persist the PayPal order ID.
2. Authorize and persist ID, amount/currency, expiration/honor timestamps, status, payer/account scope, and creation response.
3. Before fulfillment/capture, re-read canonical status and calculate whether capture is still valid.
4. If policy permits reauthorization, call it idempotently, store the new ID and parent lineage, and make it the active authorization atomically.
5. Capture against the active ID. Set `final_capture` only when no further captures are expected under that authorization.
6. Void only an eligible uncaptured authorization and reconcile its eventual status.
7. For ambiguous timeouts, query by resource/request context before retrying.

Use `PayPal-Request-Id` on supported POST operations with a durable business-operation key. Reuse it for retries of the same intent; never reuse it for a new capture or reauthorization.

## Fulfillment and accounting

Do not fulfill from “authorization call returned 2xx” alone. Define whether the business fulfills on authorized or completed capture and validate amount/currency and order ownership. Multiple/partial captures require remaining-authorized-amount accounting and a single deliberate final capture.

Webhook handlers must be idempotent, signature-verified, and tolerant of reordering. Re-fetch canonical resources when a stale event conflicts with current state. Post financial ledger entries from capture/refund facts, not from authorization holds.

## Verification

Use sandbox fixtures for capture inside/outside the honor period, reauthorization returning a new ID, late validity, partial and final captures, void, already-captured/voided states, timeout-after-success, duplicate request IDs, webhook replay/reordering, currency mismatch, and concurrent fulfillment workers. Assert only one worker can claim an active capture operation.

## Gotchas

- Authorization is not settled money.
- A new honor period does not create an unlimited extension chain.
- Voiding an old authorization after reauthorization can target the wrong resource.
- Idempotency keys identify intent; random keys on every retry defeat protection.

## Sources

- [PayPal — Authorize payment and capture later](https://developer.paypal.com/docs/checkout/standard/customize/authorization/)
- [PayPal Payments v2 — Void authorized payment](https://developer.paypal.com/api/payments/v2/authorizations-void/)
- [PayPal Payments v2 — Capture authorized payment](https://developer.paypal.com/api/payments/v2/authorizations-capture)
