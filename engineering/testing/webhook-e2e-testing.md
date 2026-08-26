# webhook-e2e-testing

**Issue:** Stripe says it delivered the `invoice.paid` webhook three times; the order is still `pending`, and nobody knows whether the handler rejected the signature, crashed mid-processing, returned 500 and triggered the retry storm, or processed it twice and the second one failed. Webhooks are an inverted API — the provider calls you, on their schedule, with their retry semantics — so normal API testing does not reach the failure modes: unreachable endpoints, invalid signatures, replayed events, out-of-order delivery, duplicate delivery, and timeout-driven retries. This article covers testing webhook handling from unit level to genuine end-to-end, informed by Stripe/GitHub webhook docs, Hookdeck and Svix tooling practice, and 2025 local-development guides for webhook testing.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Testing signature verification in isolation

1. **Unit-test the HMAC path with known-good vector pairs.** Construct a raw body and signing secret, compute the HMAC yourself in the test, and assert the verifier accepts it; then flip one byte of body, secret, or signature and assert rejection. Verification code is security-critical and tiny — it deserves exhaustive unit coverage including malformed headers (missing timestamp, unknown scheme, truncated signature).
2. **Preserve the raw body before any parsing.** HMAC is computed over exact bytes; any JSON re-serialization (key reordering, whitespace, float formatting) breaks verification. Test this explicitly: send the same event pretty-printed and minified, and assert both verify — this catches frameworks that parse-then-re-serialize before your handler sees the body.
3. **Use constant-time comparison and test that you do.** Assert the verifier's comparison is timing-safe (`crypto.timingSafeEqual` / `hmac.equal`), not `===`; a simple equality check is a timing-oracle finding waiting for the security audit.
4. **Enforce and test timestamp tolerance.** Replay protection requires rejecting events whose timestamp header is older than the tolerance window (commonly ~5 minutes). Freeze the clock (see `jest-timer-fakes.md`), craft events at tolerance−1s and tolerance+1s, and assert accept/reject at the boundary — and test that a stale-but-valid-signature event is rejected with a distinct status so ops can tell replay from forgery.
5. **Test the failure contract.** A bad signature must return 400 (so the provider stops retrying) — or whatever your policy is — while a processing failure returns 500 (so the provider retries). Assert the status codes per failure class; returning 500 on signature failure causes infinite retry loops on the provider side, a real production pathology.

## Duplicates, ordering, and idempotency

1. **Make idempotency the default test assumption: providers redeliver.** Stripe, GitHub, and Svix all retry failed deliveries, and some redeliver on request; every webhook handler must be safe to invoke twice with the same event ID. The core test: deliver the same event twice, assert exactly-once side effects (one DB row, one email, one charge) and a 2xx on both deliveries.
2. **Test out-of-order delivery.** `invoice.updated` arriving before `invoice.created` (or an event delivered late after a long retry backoff) must not corrupt state — the handler either upserts by monotonic version/timestamp or defers. A test that delivers events reversed and asserts final state equals the in-order outcome catches ordering assumptions early.
3. **Race two concurrent deliveries of the same event.** Two simultaneous requests creating the same side effect is the classic concurrency bug (the AGENTS canon calls it out); a unique constraint or transactional insert-if-absent must hold. This test belongs in the integration suite, exercised over real HTTP against a real database, not against a mocked store.
4. **Test partial-failure recovery.** Handler completes the DB write, then crashes before returning 2xx; the provider retries; assert the retry finds the work already done and returns cleanly. The transactional/outbox pattern (see `event-driven-testing.md`) is the usual fix, and this test is its proof.

## Local end-to-end: receiving real provider traffic

1. **Tunnel real webhooks to localhost with ngrok/Hookdeck/Webhook Relay.** The provider must be able to reach you; a tunnel plus a provider-configured endpoint URL is the standard loop. Capture a real signed payload once and you have a golden fixture with authentic headers — provider test-mode triggers (Stripe CLI `stripe trigger`, GitHub's redeliver button, Svix's replay) generate fresh real events on demand.
2. **Capture every delivery with headers, and keep a replay library.** Tools like Hookdeck CLI, webhook.site, and webhook-debugger record full requests for later replay; check a folder of captured real events (raw body + headers) into the repo as fixtures so signature tests use authentic vectors — the same governance discipline `playwright-har-replay-fixture-governance.md` applies to HARs.
3. **Use a separate test signing secret for dev, never disable verification.** 2025 local-testing guides emphasize: running with verification "temporarily off" in dev means the verification path is never exercised until production. A dedicated dev secret keeps the code path identical across environments; toggle secrets via env config, not code branches.
4. **Simulate the provider's retry behavior in tests.** Return 500 to the first delivery, 2xx to the second, and assert your handler's observable state (and that you are not doing destructive work per retry). Conversely, return a timeout (open a connection, never respond) and assert the handler's internal timeout is shorter than the provider's — handlers that hang past the provider's timeout window look like failures and trigger duplicate deliveries.
5. **Verify the loop end-to-end, not just the endpoint.** A genuine E2E test triggers an event in the provider's test environment (e.g., create a test payment), waits for the delivery through the tunnel, and asserts the business outcome in your own DB with a bounded poll — never a fixed `sleep` (the eventual-consistency testing rules in `event-driven-testing.md` apply verbatim).

## Operational verification in production

1. **Respond 2xx fast; do the work async.** Providers time out slow handlers and retry, multiplying load; the tested contract should be "verify → enqueue → 2xx in <1s," with a queue between the HTTP endpoint and processing. Test that the endpoint responds within budget under a burst of deliveries (a mini-load test against the handler alone).
2. **Log delivery ID, event type, signature validity, and outcome per request.** When Stripe support says "we sent it three times," you must be able to answer from your logs what happened to each of the three; a structured log line per delivery is the difference between a 5-minute answer and an afternoon of guessing.
3. **Add a dead-letter path and test it.** Events that permanently fail verification or processing after N attempts must land somewhere inspectable (a failed-deliveries table or DLQ) with an alert; a webhook that silently vanishes after retries exhaust is an incident discovered by the customer.
4. **Monitor signature-failure rates as a security signal.** A spike in failed verification is either a config drift (rotated signing secret — test the rotation procedure!) or an attack; both demand paging. Secret rotation deserves its own test: old-secret events should fail, new-secret events pass, and the overlap window behaves as documented.
5. **Replay real production events against staging after handler changes.** Provider replay endpoints (Svix replay, GitHub redeliver, Stripe CLI `stripe listen --forward-to`) let you re-run yesterday's traffic against the new handler; a post-deploy canary that replays a sample of captured events and diffs outcomes is the highest-fidelity regression test a webhook system can have.

## Related

- `event-driven-testing.md` — eventual-consistency assertions the E2E webhook test borrows
- `api-mock-fidelity-schema-locking.md` — keeping mocked provider payloads honest
- `flaky-test-remediation.md` — replacing webhook-test sleeps with polling
- `security-testing-zap.md` — the wider security surface this article's signature tests plug into
