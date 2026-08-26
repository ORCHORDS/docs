# Durable Objects Eviction and Reconstruction Tests

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** Documented

## Problem

A Durable Object can appear correct while one isolate remains warm yet fail after eviction because essential state lived only in class fields, initialization was not repeatable, or side effects replayed during reconstruction. Production eviction must be a tested lifecycle transition.

## Test contract

Cloudflare's Workers Vitest integration provides `evictDurableObject()` and `evictAllDurableObjects()` in `@cloudflare/vitest-pool-workers` 0.16.20 and later. Use these helpers to force reconstruction instead of relying on timing or garbage collection.

## Required scenarios

1. Arrange durable state through the public RPC or fetch interface.
2. Evict the target instance.
3. Obtain or reuse its stub and invoke the next operation.
4. Assert persisted state reconstructs correctly and ephemeral caches rebuild safely.
5. Assert no completed side effect, alarm, or idempotent operation is duplicated.
6. Evict all objects to expose hidden cross-instance memory dependencies.
7. For WebSocket objects, test hibernation assumptions and the explicit `{ webSockets: "close" }` path separately.
8. Repeat after schema and deployment-version changes.

## Controls

- Persist every correctness-critical fact before acknowledging success.
- Make constructor and lazy initialization idempotent.
- Treat in-memory state only as a cache.
- Recover alarms and reconciliation ownership from storage.
- Keep tests isolated by object identity and namespace.
- Pin a compatible Vitest-pool version and review its open-beta known issues.

## Verification evidence

Record the pre-eviction state, eviction action, post-reconstruction observations, side-effect count, alarm state, and any socket outcome. A passing request alone is insufficient; assert the invariants that would detect lost or duplicated work.

## Gotchas

- Fake timers do not advance every Cloudflare storage simulator.
- Closing WebSockets tests a different condition from hibernating them.
- Active outbound connections affect production lifetime, but must not become a persistence mechanism.
- An object's in-memory fields are lost after eviction, hibernation, or crash.

## Official sources

- [Durable Objects changelog — eviction test helpers](https://developers.cloudflare.com/changelog/product/durable-objects/)
- [Testing Durable Objects](https://developers.cloudflare.com/durable-objects/examples/testing-with-durable-objects/)
- [Workers Vitest integration known issues](https://developers.cloudflare.com/workers/testing/vitest-integration/known-issues/)
- [Durable Object in-memory state](https://developers.cloudflare.com/durable-objects/examples/durable-object-in-memory-state/)
