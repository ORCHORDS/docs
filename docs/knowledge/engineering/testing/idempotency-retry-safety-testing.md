# idempotency-retry-safety-testing

**Issue:** Distributed systems deliver messages and HTTP requests at least once: webhooks are redelivered on timeout, clients retry payments and order submissions after a dropped connection, and queues hand the same job to more than one worker during rebalancing. If processing is not idempotent, those duplicate deliveries become duplicate charges, duplicate rows, and double-sent notifications. Idempotency is a correctness property of the system under test, and like any correctness property it needs dedicated tests that replay, duplicate, and interleave deliveries on purpose instead of hoping normal traffic never triggers them.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Semantics to pin down first

1. **At-least-once delivery is the contract.** Write down explicitly that the transport may redeliver, and that the handler must produce the same observable effect for a repeated delivery as for the first. Tests then target this contract rather than trying to prove the transport never duplicates, which is unprovable.
2. **Idempotency keys are client-generated.** Following the Stripe model and the IETF Idempotency-Key draft, the caller generates a key (up to 255 characters, no sensitive data inside it), reuses it verbatim on retries, and the server records it. Tests must verify the server honors the header and that the client actually reuses the same key across its own retry attempts.
3. **Same key must return the original result, not a re-execution.** The strongest guarantee is response replay: persist the status and payload keyed by the idempotency key and return the stored response on a repeat. A test should assert the second response matches the first byte-for-byte, including timestamps and identifiers.
4. **Different keys must mean different operations.** Two requests with distinct keys and identical payloads are two legitimate operations; a naive payload-hash deduplication would wrongly collapse them. Assert the system distinguishes key identity from payload identity.
5. **Key stores expire.** Keys have a TTL (commonly 24 hours) so storage stays bounded. A test at the TTL boundary should confirm expiry results in a clean rejection or fresh processing per the documented policy, never a silent corruption of state.

## Test scenarios for duplicate handling

1. **Sequential replay.** Send the same webhook event or request with the same key twice, back to back. Assert the side effect occurs exactly once: one payment, one row, one email. This is the smoke test of idempotency and catches naive implementations immediately.
2. **Concurrent duplicate delivery.** Fire the same keyed request from several connections simultaneously. A check-then-insert implementation will race and process twice; only an atomic check-and-set (a unique constraint, an insert-or-ignore, or a conditional write) survives. Assert both the invariant and that exactly one caller receives the original response.
3. **Retry after partial failure.** Kill the worker or abort the connection after the side effect but before the response is written, then retry with the same key. The handler must either resume from recorded progress or return the recorded outcome without performing the side effect a second time.
4. **Out-of-order and interleaved events.** Deliver the same event id mixed with unrelated events and with events for the same aggregate from other sources; deduplication must key on the event identity, not on arrival order or position in a stream.
5. **Poison replay.** Replay an event whose first processing failed permanently. The system must not flip into a state where the retry loop re-executes a half-applied change; assert the failed outcome is recorded and replays return it consistently.

## Implementation details the tests must exercise

1. **Atomicity of the deduplication write.** The unique-constraint or set-if-absent operation and the business side effect need to be ordered so a crash between them cannot produce either double processing or a black-holed key that blocks all retries. Test by injecting failure at each step boundary.
2. **Concurrency control on the underlying aggregate.** Even after deduplication, two different keys targeting the same account or order can race; optimistic versioning or row locking must keep the invariant. Test with concurrent distinct-key requests against one aggregate.
3. **Webhook signature verification before deduplication.** Replayed or spoofed deliveries must be rejected by signature check first; assert that a valid-signature duplicate is deduplicated while an invalid-signature copy of the same payload is rejected, proving the two mechanisms are independent.
4. **Cleanup and reprocessing windows.** If keys are deleted after use (queue acknowledgment patterns), assert the window between delete and re-delivery cannot cause double processing; the usual fix is deferring deletion until after the side effect commits, and the test proves it.

## Making it continuous

1. **Duplicate-injection harness in CI.** Wrap every webhook handler test so it runs each case twice with the same delivery metadata; the harness makes replay testing a default rather than something remembered per handler.
2. **Property-based invariants.** A property test can state the invariant generically: for any sequence of deliveries of the same event (any count, any interleaving), the final state equals the state after one delivery. Shrinking then produces minimal reproducing schedules.
3. **Assert side-effect counts, not response codes.** Idempotency bugs hide behind correct-looking HTTP 200s; assertions must count rows, ledger entries, and outbound calls to prove the effect happened once.
4. **Production-traffic canary.** Log hash-bucketed counts of duplicate key sightings in production; a spike in deduplication hits after a deploy is an early warning that a client changed its retry behavior in a way tests should now model.
