# Redis HGETDEL atomic field consumption

**Problem**

Reading then deleting a hash field in separate commands permits duplicate consumption and races.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for one-time field retrieval where atomic removal is the intended data model.

## Controls

- Use exact fields and define missing-field behavior.
- Keep idempotency at the business-operation layer.
- Audit destructive reads.

## Implementation

- Call HGETDEL instead of client-side HGET/HDEL sequences.
- Avoid broad dynamic field lists.
- Record outcomes without sensitive values.

## Tests

- Test concurrent consumers, missing/expired fields, replication, failover, and retry after disconnect.

## Gotchas

- A lost response creates outcome uncertainty.
- Deletion is not queue acknowledgement.
- Version support must be pinned.

## Official sources

- [Official documentation](https://redis.io/docs/latest/commands/hgetdel/)
