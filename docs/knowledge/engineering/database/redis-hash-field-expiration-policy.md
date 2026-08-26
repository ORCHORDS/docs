# Redis hash-field expiration policy

**Problem**

Per-field expiration changes data lifecycle inside a hash and can invalidate assumptions that TTL applies only to whole keys.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for independently expiring hash attributes when the deployed Redis version supports it.

## Controls

- Define field TTL semantics and refresh ownership.
- Monitor expired-field effects and memory.
- Keep whole-key TTL interaction documented.

## Implementation

- Use HEXPIRE-related commands with explicit conditions.
- Treat missing/expired fields as normal states.
- Avoid using expiry as the only audit mechanism.

## Tests

- Test field/key TTL ordering, persistence, replication, failover, restore, and concurrent updates.

## Gotchas

- Field expiration can make partial objects.
- Command support is version-bound.
- Expiry timing is not exact scheduling.

## Official sources

- [Official documentation](https://redis.io/docs/latest/commands/hexpire/)
