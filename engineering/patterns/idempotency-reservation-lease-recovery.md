# idempotency-reservation-lease-recovery

**Issue:** An idempotency key remains `in_progress` after the worker handling the original request terminates before it can persist a completed response.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

The first request reserves an idempotency key, then times out, is evicted, or fails between side effect and response persistence. Retries receive a permanent conflict even though no replayable completed response exists.

## Root cause

A unique constraint or atomic reservation prevents concurrent execution, but it does not recover a reservation whose owner has disappeared. Treating an in-progress row as valid for the full completed-response retention period turns a short worker failure into a long-lived customer-visible outage.

The HTTP Idempotency-Key draft distinguishes in-progress and completed work and describes server-managed key lifecycles; an implementation needs an explicit recovery policy for unfinished work.

**Source:** [IETF draft — Idempotency-Key HTTP Header Field](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-07).

## Fix

Store the reservation as a state machine with bounded ownership:

- atomically insert `in_progress` with an owner token and short `lease_expires_at`;
- only the owner token may mark the row `completed` and persist a replay-safe response;
- on retry, return an in-progress result only while the lease is valid;
- after expiry, reclaim atomically only when no completed result exists; record the recovery attempt;
- make downstream side effects independently idempotent, because a crash can occur after the side effect but before completion is stored;
- retain completed outcomes on a separate, documented TTL from the in-progress lease.

## Verification

- **Concurrency:** two simultaneous requests create one reservation and exactly one owner.
- **Termination:** simulate termination after reserve; a retry is blocked only until lease expiry, then safely reclaims or resolves the operation.
- **Ownership:** a stale owner cannot overwrite the result after another worker reclaimed the lease.
- **Persistence failure:** a failure after the external side effect yields a deterministic reconciliation path, not an unbounded `in_progress` state.

## Gotchas

- Do not reclaim merely because a request is slow; choose the lease from observed worst-case duration plus a safety margin.
- A lease prevents stuck locks, not duplicate external effects. Use provider idempotency keys or durable outbox/reconciliation where needed.
- Never replay a response that contains a one-time secret; see the related entry.

## Related

- `patterns/idempotency-keys.md`
- `security/idempotency-one-time-secret-replay.md`
- `patterns/outbox-pattern.md`
