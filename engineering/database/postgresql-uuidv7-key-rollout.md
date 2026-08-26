# PostgreSQL UUIDv7 key rollout controls

**Issue:** Random UUID primary keys provide distribution but can increase index-page churn, while changing identifier formats without version controls can break consumers and ordering assumptions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

PostgreSQL 18 provides `uuidv7()` for time-ordered UUID generation. Adopt it only after every database in the write path runs a compatible major version, and preserve the column's `uuid` type so mixed historical UUID versions remain valid. Use `uuid_extract_version()` for migration audits and constraints only when rejecting other versions is actually required.

Treat UUIDv7 ordering as an indexing locality property, not a substitute for a business timestamp or a total event order. The embedded timestamp has finite precision and reflects the generator's clock. Keep an explicit creation timestamp for retention, audit, and legal semantics. Benchmark index size, page splits, replication traffic, and write latency using production-like concurrency before changing defaults.

## Verification

Generate high-concurrency UUIDv7 values across multiple sessions and nodes; prove uniqueness and measure index behavior against UUIDv4. Test restore into every supported environment, mixed-version rows, clock rollback, same-millisecond bursts, logical replication, and application serializers. Confirm extracted timestamps are diagnostic only and are not used to authorize or sequence transactions.

## Gotchas

- PostgreSQL 17 does not provide the built-in `uuidv7()` generator available in PostgreSQL 18.
- Lexical proximity does not guarantee commit order.
- Client-generated UUIDv7 implementations may differ in monotonic behavior.

## Official source

- [PostgreSQL UUID functions](https://www.postgresql.org/docs/current/functions-uuid.html)
