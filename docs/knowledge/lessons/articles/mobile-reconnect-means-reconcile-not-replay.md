# Mobile reconnect means reconcile, not replay

**Issue:** After connectivity returns, a mobile client blindly replays queued requests and duplicates mutations or overwrites newer server state.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

Connectivity is only a trigger to reconcile durable local intent with authoritative server state. It is not proof that the network is usable, that previous requests failed, or that replay is safe.

**Source:** [Android offline-first data layer guidance](https://developer.android.com/topic/architecture/data-layer/offline-first)

## Apply

- persist an outbox with immutable operation IDs and idempotency keys;
- distinguish unsent, sent-with-unknown-outcome, acknowledged, conflicted, and terminal states;
- fetch server checkpoints before applying dependent operations;
- preserve causal ordering only where the domain requires it;
- use exponential backoff with jitter and honor server retry guidance;
- surface conflicts instead of silently choosing a winner for consequential data.

## Verify

Test disconnect before send, after server commit but before response, partial batch, app/process death, token expiry, account switch, server rollback, reordered responses, and repeated connectivity signals. Prove each logical mutation commits at most once.

## Gotchas

Network reachability does not guarantee Internet or service reachability. HTTP timeout does not mean the server did nothing. A queue without reconciliation is deferred duplication.
