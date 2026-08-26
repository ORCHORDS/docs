# durable-objects-sqlite-storage

**Issue:** Durable Objects offer two storage backends: the legacy key-value API and the newer SQLite-backed storage API. The KV API is in maintenance mode and Cloudflare recommends SQLite for all new Durable Objects, yet most code in the wild still uses `storage.get`/`storage.put` patterns copied from old tutorials. Teams starting new stateful coordination (rooms, sessions, rate counters, leader election) should design around `ctx.storage.sql` from day one — schema, migrations, cursors, and transaction semantics all differ from the KV API, and retrofitting later is a rewrite. This article captures the storage patterns, limits, and migration mechanics for SQLite-backed Durable Objects.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why SQLite over the KV API

1. **SQLite is the recommended backend.** Cloudflare positions the legacy KV storage API as maintenance-mode; new features (SQL, point-in-time recovery) land on SQLite first. New DO classes should use SQLite storage unless there is a hard constraint otherwise.
2. **Expressive queries replace manual indexing.** With KV storage you hand-maintain secondary indexes as separate keys. With SQLite you create real indexes with `CREATE INDEX` and run `WHERE`, `ORDER BY`, `LIMIT`, and aggregate queries directly, which removes an entire class of bookkeeping bugs.
3. **Automatic transactionality.** SQLite-backed DOs get implicit transactions: storage writes and in-memory state are kept consistent across awaits via input/output gates. Every mutation within an input handler commits atomically or not at all — no explicit begin/commit juggling for the common case.
4. **One database per object.** Each Durable Object instance owns an isolated SQLite database (multi-gigabyte capacity per object, up to the documented per-DO storage limit). Sharding strategy (how you derive object IDs from entity keys) now doubles as your partitioning strategy, so choose it before writing schema.

## Core API patterns

1. **Parameterized statements only.** `ctx.storage.sql.exec("SELECT * FROM votes WHERE room = ? AND user = ?", room, user)` binds parameters positionally (`?`, `?1`) or by name. Never string-concatenate user input into SQL — the DO runtime gives you no injection shield beyond prepared binding.
2. **Treat results as cursors.** `sql.exec` returns a cursor object, not an array. Consume it as an async iterator (`for await (const row of cursor)`), or use the terminal helpers `cursor.one()` (exactly one row or throw), `cursor.all()`, `cursor.toArray(columnNames)`, and `cursor.raw()` for untyped rows. Pulling a huge table through `cursor.all()` wastes memory; iterate instead.
3. **Respect cursor lifetimes.** Cursors are not free-floating handles — they tie into the object's execution and have a short validity window (about a minute) plus limits on how many can be open concurrently and on total statement size. Finish iterating inside the same handler that created the cursor; do not stash cursors across requests.
4. **Upserts and conflict handling.** Use `INSERT ... ON CONFLICT DO UPDATE` for counters and last-writer-wins records instead of read-then-write, which doubles round trips and invites races at the handler boundary.
5. **Explicit transactions when needed.** For multi-step sequences that must abort as a unit even across awaits, wrap logic in `ctx.storage.transaction(async tx => { ... })` and use `tx.sql.exec`. Aborting rolls back the writes performed inside the block; on success the block commits as one.

## Schema migrations

1. **Gate migrations on `PRAGMA user_version`.** The standard pattern: in the class constructor (or first-use path), read `PRAGMA user_version`, and if it is below the target, run `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE` statements inside a transaction, then bump `user_version`. Each DO instance migrates itself lazily on first wake, so migrations must be idempotent and monotonic.
2. **Never rewrite history in place.** Additive migrations (new tables, new columns, new indexes) are safe because old code ignores them. Destructive column changes break rolling deploys where some objects still run old code against new schema — stage them across two releases.
3. **Test migrations against real storage.** Run migration code under `@cloudflare/vitest-pool-workers` with isolated DO storage so schema bugs surface in CI, not on your users' first request after deploy.

## Limits and operations

1. **Per-object capacity is finite.** A single DO's SQLite database is bounded (on the order of gigabytes, per the current Durable Objects limits page); keep per-object datasets small by design and shard hot entities across objects rather than growing one database forever.
2. **Row and statement size caps.** Individual string/blob values and SQL statements have maximum sizes (roughly the 2 MB range per value); store large payloads in R2 and keep only keys and metadata in the DO.
3. **Alarms are your TTL engine.** SQLite storage has no native row expiry. Schedule an alarm, and in the alarm handler run `DELETE FROM sessions WHERE expires_at < ?` style sweeps — this is cheaper and more predictable than per-read garbage collection.
4. **Watch the write path.** Every mutating statement is durable storage I/O billed as DO storage operations; batch related mutations into one handler invocation and avoid tight-loop writes inside a single request to stay within CPU and storage-subrequest budgets.
5. **PITR for disaster recovery.** SQLite-backed DOs support point-in-time recovery, which the KV API lacks. Factor this into retention expectations, but still treat the DO as a coordination layer — canonical records that outlive a room/session belong in D1 or R2.

## References

1. **SQLite-backed Durable Object Storage API.** developers.cloudflare.com/durable-objects/api/sqlite-storage-api — full method reference, cursor semantics, and current limits.
2. **Access Durable Objects Storage best practices.** developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage.
3. **Zero-latency SQLite storage in every Durable Object.** blog.cloudflare.com/sqlite-in-durable-objects — design rationale for the storage engine.
