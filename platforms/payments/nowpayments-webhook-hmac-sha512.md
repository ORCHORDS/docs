# nowpayments-webhook-hmac-sha512

**Issue:** NOWPayments IPN webhooks arrive at a public, unauthenticated endpoint, so every callback must be verified before it can touch order state. Verification is an HMAC-SHA512 computed by NOWPayments over the callback JSON body with keys sorted alphabetically, sent in the `x-nowpayments-signature` header (legacy name `x-nowpayments-sig`/`x-payments-signature` depending on docs vintage), signed with the store's IPN secret. The receiving side must re-serialize the body with identically sorted keys or the signature never matches — and verified callbacks still arrive replayed and out of order, handled by comparing payment status transitions.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The signature mechanism

1. **HMAC-SHA512 over the sorted-key JSON body.** NOWPayments computes the signature over the callback payload re-serialized with all object keys sorted alphabetically (recursively for nested objects), not over the raw wire bytes — this differs from providers like Stripe that sign the raw body and forces a parse-then-re-serialize step on the receiver.
2. **The header carries the hex digest.** The signature arrives in the request header; the current API documentation (Postman collection at documenter.getpostman.com/view/7907941/S1a32n38) names it `x-nowpayments-sig`, while older integrations and docs have used `x-payments-signature`. Read whichever header is present rather than hard-coding one name and rejecting the other.
3. **The IPN secret comes from Store settings and is shown once.** The secret is generated under Account → Store Settings and displayed only once at generation time; store it immediately in the secret manager (Workers secret / vault) — there is no "view secret" later, only regenerate-and-rotate.
4. **Compare digests safely.** Compute your hex digest, lowercase both sides, and compare with a constant-time equality primitive (e.g. `crypto.timingSafeEqual`) rather than `===` on attacker-controlled strings.

## Getting the re-serialization exactly right

1. **Sort keys recursively.** Sorting only top-level keys fails on nested objects (`outcome_amount`, `payin/payoff` blocks); every nested object must have its keys sorted too, which is what the official Node SDK's `sortObjectDeep` does before `JSON.stringify`.
2. **Serialize compactly.** Use `JSON.stringify` default (no spaces) on the sorted structure; whitespace or pretty-printing in the re-serialized string changes the bytes and therefore the HMAC.
3. **Do not HMAC the raw body.** Signing the raw request body as delivered will not match, because NOWPayments normalized the JSON (sorted keys) before signing on their side. The correct pipeline is: raw body → parse → deep-sort → compact stringify → HMAC-SHA512 with the IPN secret → compare to header.
4. **Watch number formatting.** JSON.parse/stringify round-trips must preserve the original numeric rendering; in JS, amounts that were delivered as decimals re-serialize identically, but string-typed numbers must stay strings — never coerce fields (e.g. `"purchase_id`" or amount fields) between string and number before signing.

## Replay and out-of-order delivery

1. **IPNs are at-least-once status notifications, not events in order.** NOWPayments retries callbacks and network paths can duplicate or reorder them; a verified signature proves authenticity, not novelty or sequence.
2. **Enforce a status transition ladder.** Compare each incoming `payment_status` against the persisted status and only accept documented forward transitions (e.g. `waiting` → `confirming` → `confirmed` → `sending` → `finished`, with `expired`/`failed`/`refunding` as their own terminal branches). A stale replayed `confirming` arriving after `finished` must be a no-op.
3. **Deduplicate on payment_id plus status, durably.** Record processed (payment_id, status) pairs — or a monotonic status version per payment — in durable storage so a retried webhook that already advanced the state is acknowledged with 200 and skipped, not re-fulfilled.
4. **Reconcile uncertainty through the API.** When ordering or completeness is unclear, fetch the payment status from the NOWPayments API server-side and let that be the tiebreaker; the callback is a hint to reconcile, not the source of truth (see `payments/nowpayments-callback-payment-intent-integrity.md` for the intent-binding side).

## Failure modes seen in practice

1. **Signature breaks after payload-shape changes.** If verification is implemented against specific fields rather than the whole sorted body, a new field NOWPayments adds to the payload silently invalidates hand-rolled serialization — always verify over the complete parsed-and-sorted body.
2. **Double-encoded JSON.** A framework that wraps the parsed body again (e.g. re-stringifying an already-stringified body) produces escaped inner quotes and a mismatch; log the exact string you HMAC during debugging.
3. **Silent secret drift across environments.** Sandbox and production stores have different IPN secrets; a sandbox callback verified with the production secret fails in a way that looks like a broken algorithm. Keep secret-per-environment explicit.
4. **Reject before business logic.** Signature check must run before any parsing into domain state or DB writes; the endpoint is publicly reachable and forged callbacks are otherwise one HTTP request away from free goods.
