# Web Locks Cross-Context Coordination

**Issue:** Multiple tabs and workers race to refresh tokens, migrate IndexedDB, drain an offline queue, or elect a single leader, producing duplicate work and inconsistent state.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented
**Specification maturity:** W3C Working Draft; feature-detect and retain a fallback.

## Control pattern

Use `navigator.locks.request(name, options, callback)` for origin-scoped mutual exclusion. Name locks by stable resource identity, keep critical sections small, and perform only work that truly requires exclusivity. Use `ifAvailable` for best-effort leader work and `AbortSignal` to bound queued acquisition. Treat the callback's completion as release; ensure every path settles.

The lock is coordination, not durable state. Persist a transaction marker or idempotency key in IndexedDB/server storage so recovery after tab termination is safe. Never place access tokens, user identifiers, or other sensitive values in lock names, because same-origin contexts can observe lock metadata.

## Verification

Run two tabs and a worker contending for the same and different names. Test abort-before-acquisition, callback rejection, tab closure, worker termination, starvation under repeated contenders, private/storage-partitioned contexts, and browsers without the API. Confirm fallback operations remain idempotent and that no network request is duplicated.

## Gotchas

Locks do not span origins, devices, browser profiles, or server processes. They are not a distributed lock and do not make a non-transactional database update atomic. Long callbacks block unrelated contenders and can create user-visible stalls. Querying lock state is diagnostic only; avoid correctness decisions based on a racy snapshot.

## Sources

- [W3C Web Locks API Working Draft](https://www.w3.org/TR/web-locks/)
- [Web Applications Working Group 2026 charter](https://www.w3.org/2026/01/webappswg-charter-2026.html)
