# Redis WAITAOF durability acknowledgement boundaries

**Issue**

A successful write reply does not establish that the local append-only file or replicas have durably acknowledged the write.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `WAITAOF` only where the latency/durability tradeoff is explicit.
- Set required local and replica acknowledgements plus a bounded timeout.
- Keep application idempotency because acknowledgement uncertainty remains after disconnects.

## Verification

1. Crash the primary around write and acknowledgement boundaries.
2. Test unavailable and lagging replicas.
3. Record returned local and replica counts rather than treating timeout as a boolean.

## Gotchas

- WAITAOF does not make Redis a consensus system.
- Timeout does not roll back the write.
- Durability depends on AOF configuration and storage.

## Official source

- [Official documentation](https://redis.io/docs/latest/commands/waitaof/)
