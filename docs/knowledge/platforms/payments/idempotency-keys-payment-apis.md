# idempotency-keys-payment-apis

**Issue:** Payment API calls fail in ambiguous ways — a charge request times out, the network drops mid-response, or a client retry resubmits a request the server already processed. Without idempotency keys, every retry risks double-charging a customer, creating duplicate subscriptions, or issuing duplicate refunds. Stripe's own idempotency design and the emerging IETF Idempotency Keys draft RFC both treat client-supplied idempotency keys as the primary defense, but the engineering details (key scoping, storage, TTL, conflict semantics) are where integrations go wrong. This article covers how to generate, scope, store, and enforce idempotency keys correctly when calling payment APIs and when designing your own payment endpoints.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Key generation and scoping

1. **Generate keys client-side per logical operation.** The client (your backend, not the shopper's browser) should mint a fresh UUID v4 for each logical operation — one key per "charge this order," not per HTTP attempt. Reuse the same key only when retrying that exact request after a timeout or 5xx. Never derive keys from volatile data like timestamps within the same operation.

2. **Never embed sensitive data in keys.** Stripe documents that idempotency keys are up to 255 characters and explicitly warns against using emails or personal identifiers. Keys end up in logs, error trackers, and support tooling, so treat them as semi-public. A UUID or a hash of a stable operation reference is sufficient.

3. **Respect endpoint scoping.** Stripe scopes idempotency keys per account and per endpoint — reusing a key on a different endpoint or a different request body returns an idempotency_error conflict rather than a replay. Design your own API the same way: the key tuple should be (merchant/account, endpoint/operation, key), which prevents an accidentally reused key from silently replaying an unrelated response.

4. **Hash the request body into the stored record.** When you store a key, store a hash of the request payload alongside it. If a second request arrives with the same key but a different body, reject it with a 422 conflict. This catches the classic bug where a retry loop grabs a stale key and tries to charge a different amount.

## Storage and replay semantics

1. **Store keys with the original response in a unique-constrained table.** The Stripe-style implementation (famously described by Brandur Leach for Postgres) uses a table with a unique index on the key, columns for request hash, response body, response code, and a lock state. First request inserts a row with a lock, executes, then writes the response. Concurrent duplicates block on the lock, then read the stored response.

2. **Replay errors too, but distinguish error classes.** A request that failed with a validation error should replay that same error for the key's lifetime — the caller retrying a malformed request should get the same answer, not a new validation run. A connection-level failure (never reached the server) should not persist the key, so the retry executes fresh. Stripe's design replays stored responses including errors, which is why client-side retry logic must not blindly reuse keys after non-retryable errors.

3. **Set and document a TTL.** Stripe retains idempotency keys for 24 hours after first use; retries after that window execute as new requests. If you build your own store, pick a TTL at least as long as your most aggressive retry schedule plus clock skew, and evict expired keys with a background job. An eviction that is too eager causes duplicate executions; too lazy wastes storage.

4. **Make key expiry visible to callers.** Return a distinct error or header when a replayed key has expired and the request executed fresh. Silent execution after expiry is correct behavior, but your operations team should be able to distinguish "replayed" from "re-executed" when investigating a double-charge report.

## Common failure modes

1. **Retrying with a new key after every failure.** The most common double-charge cause: a retry helper generates a fresh key per attempt instead of reusing the original. Audit every retry loop, queue consumer, and cron reprocessor to confirm it carries the original key forward.

2. **Idempotency at the wrong layer.** Wrapping only the HTTP handler is not enough if downstream code (a webhook handler, a queue worker) can invoke the same business operation twice. Attach the key at the business-operation boundary — "create charge for order 1234" — and thread it through every downstream call, including refunds and capture.

3. **Webhooks are not idempotent by default.** Processors deliver webhooks multiple times and out of order. Key webhook processing on the event ID (not the delivery attempt) and keep a processed-events table, so a redelivered payment_intent.succeeded does not grant a subscription twice. Stripe webhook idempotency is covered in a separate article in this knowledge base; the same principle applies to any PSP.

4. **Assuming the PSP dedupes for you.** Stripe enforces idempotency only when you send the Idempotency-Key header; without it, two identical POSTs create two PaymentIntents. PayPal and Adyen have similar but not identical header schemes (PayPal also supports the Prefer: return=representation header for idempotent order creation). Read each provider's docs before assuming parity.

## Testing and operations

1. **Chaos-test with injected timeouts.** In test mode, kill connections between your service and the PSP at various points (after send, before response parse) and verify that retries with the same key never produce two succeeded charges. Automate this as a integration test, not a one-off.

2. **Monitor key-collision alerts.** A spike in 422 conflict errors means either a retry bug or a key-generation bug (e.g., a UUID function seeded identically across worker processes). Alert on conflict rate, not just on 5xx.

3. **Keep keys in the audit trail.** When a customer disputes a duplicate charge, the fastest resolution is showing support which key each attempt used and whether the second attempt was a replay or a fresh execution. Log key, request hash, and outcome for every payment mutation.

4. **Adopt the draft RFC vocabulary.** The IETF Idempotency Keys draft standardizes replay semantics with headers like Idempotency-Key and Idempotent-Replayed. Aligning your internal API design with it keeps your payment service consistent with the direction Stripe-style APIs are converging toward, and makes client SDK behavior predictable.
