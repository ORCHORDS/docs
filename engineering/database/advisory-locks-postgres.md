# advisory-locks-postgres

**Issue:** Applications frequently need mutual exclusion that is bigger than one row: only one worker should run a nightly sync, two admins must not edit the same billing batch, a singleton cron leader must be elected, or a group of rows sharing a tenant key must be serialized. Doing this with application-level flags in a table invites races (check-then-set gaps), while taking hard row locks over wide ranges destroys concurrency. Postgres advisory locks are a named, database-level lock namespace — `pg_advisory_lock(key)` — that fills this gap: locks on 64-bit integers (or int4 pairs) that are invisible to MVCC, never block autovacuum, and are enforced cluster-wide with the same machinery as regular locks. Used correctly they are cheap and robust; used casually they leak, deadlock, or silently break behind a pooler.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Session-level vs transaction-level locks

1. **`pg_advisory_lock` is session-scoped and sticky.** It is held until the session explicitly calls `pg_advisory_unlock` or the connection closes — not until the transaction ends, and crucially not on rollback. This is what makes leaked locks common: an exception unwinds the transaction, the developer assumes cleanup happened, and the lock rides the pooled connection back into circulation.
2. **`pg_advisory_xact_lock` is the safe default.** It is released automatically at commit or rollback, giving mutex semantics with zero cleanup code. Any time the critical section is a single transaction (read-modify-write on a group of rows, per-tenant serialization), use the xact variant and the leak class of bugs disappears.
3. **Session locks need an acquire/release discipline.** If you genuinely need to hold a lock across transactions (a long export job), wrap acquisition and release in one helper that uses try/finally semantics, set `lock_timeout` and `statement_timeout` around the acquire, and log every acquire/release pair with the key so leaks are traceable.
4. **Re-entrancy is per-session, not per-call-site.** The same session acquiring the same advisory lock twice increments a counter and must release twice; across sessions the second acquirer blocks. This asymmetry surprises people who expect mutexes to be owned by "the job".

## Choosing and managing keys

1. **Use the two-int form for namespacing.** `pg_advisory_xact_lock(classid, objid)` lets you divide the 64-bit space into namespaces (e.g. 42 = billing batches, 43 = sync jobs), preventing collisions between features that each picked "1" as their key. Document a registry table of classids or the keys will collide eventually.
2. **Derive keys from stable identifiers, not names.** Hashing a tenant slug into the key is fine; hashing a display name that can be renamed is not — the lock silently moves mid-flight. Prefer `hashtextextended(tenant_id, seed)` or the integer PK.
3. **Never hardcode magic numbers in business code.** Centralize key construction in one module with named constants; the lock is only correct if every access path derives the identical key for the identical resource.
4. **Monitor what is held.** `pg_locks` rows with `locktype = 'advisory'` joined to `pg_stat_activity` show which sessions hold which keys and for how long; alert on advisory locks held longer than the expected critical-section duration, which is the signature of a leak.

## Pooler and failure interactions

1. **Transaction-mode pooling breaks session locks.** Under PgBouncer in transaction mode a session lock can be acquired on one server connection and "released" on a different one — the release fails and the lock stays orphaned until the server connection dies. Session advisory locks are only safe with session pooling or a direct connection; xact locks are always safe because their lifetime matches the transaction.
2. **A crashed app server releases its locks.** When the backend connection drops (worker killed, network partition), Postgres releases that session's advisory locks — good for liveness, but it means lock-based "ownership" must still be re-checkable: after acquiring, re-verify the thing you locked is still in the expected state.
3. **Advisory locks are not queues.** Blocked acquirers wait without an ordering guarantee and without timeouts unless you set one; prefer `pg_try_advisory_lock` in worker loops (skip and retry later) over `pg_advisory_lock` where piling up waiters would turn an outage into a convoy.
4. **Deadlock detector applies.** Advisory locks participate in the deadlock detector like any lock; acquiring multiple advisory keys in inconsistent order across processes can produce `deadlock detected` errors — always acquire in a canonical global order.

## When an advisory lock is the wrong tool

1. **Mutual exclusion over exactly one row is just `FOR UPDATE`.** If the critical section is a single row's read-modify-write, `SELECT ... FOR UPDATE` (or `UPDATE ... WHERE version = n`) is simpler, lock-scoped, and deadlock-observable; don't reach past it.
2. **Enforcing uniqueness is a constraint, not a lock.** Advisory locks serialize access but prove nothing about data state; if the invariant is "one active record per tenant", a partial unique index enforces it for every code path including manual SQL, which a lock never does.
3. **Leader election with stronger guarantees wants a lease table.** Advisory locks give liveness-tying to a connection, but no fencing: a paused (not dead) process can resume believing it still leads. For tasks where double-execution is costly, back the lock with a lease row containing an expiry and a fencing token checked by consumers.
4. **Cross-database or cross-cluster coordination needs a real primitive.** Advisory locks live in one Postgres cluster; the moment two services on different databases must coordinate, move to a distributed lock with fencing tokens (or redesign so they don't share the resource) rather than approximating it with row flags.
