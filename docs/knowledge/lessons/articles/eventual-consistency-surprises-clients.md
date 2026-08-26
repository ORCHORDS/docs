# eventual-consistency-surprises-clients

**Issue:** APIs that are eventually consistent confuse clients who expect read-your-own-write consistency
**Date:** 2026-08-11
**Status:** documented

## What happened
A user uploaded a profile photo. The API returned 200. The user immediately navigated to their profile and saw the old photo. They uploaded again. Now they had two uploads in the queue. Support tickets flooded in: "the upload doesn't work." The API was eventually consistent with a 2-second propagation lag that nobody had documented.

## The lesson
Eventual consistency is a valid design choice, but it must be a conscious, documented one. Clients — both humans and code — expect that immediately after a successful write, a read will reflect that write. If your system cannot guarantee this, document it explicitly, surface it in the API response (e.g., `"propagation_delay_ms": 2000`), or design client UX that masks the lag.

## Why it matters
Unexpected eventual consistency causes duplicate actions, user frustration, and subtle data bugs (double charges, double submissions). "It'll be consistent in a moment" is not a user experience.

## How to apply
- [ ] Document your consistency model in the API docs for every endpoint that has eventual consistency.
- [ ] For user-facing writes, prefer synchronous confirmation from all affected stores before returning 200.
- [ ] Where lag is unavoidable, optimistically update the client UI immediately (don't wait for the read round trip).
- [ ] Include consistency guarantees in your SLA definitions.
- [ ] Test eventual consistency windows under load — they grow under pressure.

## Related
- `cache-invalidation-is-harder-than-caching.md`
- `idempotency-keys-for-all-payment-calls.md`
