# Dead Letter Table Vs Soft Delete Pattern

## Scope

This article compares two retention strategies for rows that have permanently failed processing: dead-letter tables, where rejected rows are moved to a separate table (and often a separate lifecycle) for inspection, replay, or archival, versus soft-delete patterns, where rows remain in the main table with a `deleted_at` or `is_deleted` flag and queries filter them out. It covers decision criteria for adopting each, the operational consequences, and the failure modes that occur when one is used where the other was intended. It also addresses hybrid patterns where soft-delete flags exist *and* dead-letter capture exists, and the dispute that hybrid designs produce. It excludes garbage collection tuning, GDPR-style erasure, and the deletion-versus-history concerns that are orthogonal to this decision.

## Workflow or implementation guidance

1. **Define failure first.** A dead-letter table is the right tool when "the row was unprocessable and will be retried later or reviewed by a human", and the original row's state must be preserved exactly as it arrived. A soft-delete column is the right tool when "the user or system has logically removed the row but the application must continue to display or reference it by id", and processing is not in the picture.
2. **Pick dead-letter tables for processing pipelines.** A queue consumer that fails to parse or persist an inbound message should write the full message body plus the failure reason into a dead-letter table, then ack the source so it does not replay. This keeps the live table clean of unprocessable rows and gives operations a single place to inspect, replay, or escalate failures.
3. **Pick soft-delete for entity lifecycle.** A user deactivates an account; the row stays in the `users` table so foreign keys in `orders`/`sessions`/`audit` still resolve, and application code uniformly filters `WHERE deleted_at IS NULL`. Soft-delete here keeps referential integrity simpler than a tombstone table would.
4. **Treat the row's metadata as the deciding factor.** If the failure carries information the producer can act on later (replay hint, retry count, error category), it belongs in a dead-letter table with that metadata. If the deletion is an ordinary state transition with no producer-side response, it is a soft-delete flag.
5. **Index the live table to ignore soft-deleted rows cheaply.** A partial index `WHERE deleted_at IS NULL` keeps the working set small, and queries that always include the filter do not pay for deleted rows during planning. Without the partial index, planner statistics still include soft-deleted rows and query latency degrades over time.
6. **Bound the dead-letter table.** A growing dead-letter table that nobody triages is a leak. Add a `processed_at`/`status` column, a triage cron that escalates after a configurable age, and a documented archive-after-resolution path so the table does not silently accumulate.
7. **Do not mix them.** Soft-delete flag on a row that also has a dead-letter twin is two sources of truth for the same outcome. Pick one. If both seem necessary, the model is signalling a missing state in the lifecycle that warrants a real status field rather than two flags.
8. **Consider the "find the deleted row" use case.** Soft-delete's main selling point over a real delete is that the row still exists for a foreign-key or audit-trail reference; if that is the need, then the entity does need to remain queryable, and a soft-delete column is the correct shape. Hard delete plus dead-letter is for messages, not entities.

## Controls

1. **Dead-letter status lifecycle.** Columns `(status, last_error, retry_count, first_seen, last_seen, resolved_at)`, plus a state machine (`new`, `in_replay`, `resolved`, `archived`) enforced by a check constraint or trigger.
2. **Soft-delete partial indexes.** Every query against a soft-delete table either uses a partial index or is asserted in CI to filter on the flag.
3. **Triage SLA.** A runbook defining the maximum age before a dead-letter row is escalated, and a dashboard that shows the current oldest unresolved row per pipeline.
4. **Referential integrity rule.** Foreign keys into soft-delete tables are deliberate; foreign keys into dead-letter tables from the live table are forbidden (a dead-letter row is the end of a journey, not a reference target).
5. **Replay tool safety.** A replay utility that re-emits dead-letter rows only if their `status` is `in_replay`, idempotent on the source key to prevent duplicates on partial success.
6. **Bounded soft-delete growth.** A dashboard or alert on the share of soft-deleted rows per table, because at scale the partial index becomes a misnomer.

## Validation evidence

1. **Failure preservation test.** Trigger an unprocessable message in a staging consumer and assert it appears in the dead-letter table with the original payload intact, retry count 0, and `status = 'new'`, then verify a triage workflow increments `retry_count`.
2. **Soft-delete query plan test.** Compare `EXPLAIN` on the live table for queries that filter `deleted_at IS NULL` with and without the partial index; assert the partial-index plan excludes the deleted set.
3. **Replay idempotency test.** Replay the same dead-letter row twice; assert only one downstream effect occurs, evidencing the dedup key.
4. **Referential integrity test.** Delete a soft-deleted entity and verify behaviour against foreign keys; with `ON DELETE RESTRICT` the system enforces that the entity still logically exists; with cascading FKs, document the consequence and assert behaviour.
5. **Triage SLA test.** Stage a dead-letter row with an artificially aged `first_seen`; run the triage cron and assert it appears in the escalation report or is auto-archived per policy.

## Failure modes and correction

1. **Dead-letter table grows without bound.** No one notices until storage or query time is degraded. Correction: add an owner and a triage SLA; archival policy after resolution.
2. **Soft-delete flag becomes a query-time landmine.** New code forgets the `WHERE deleted_at IS NULL` and exposes deleted rows. Correction: enforce through a generated view or row-level security policy that always filters; do not rely on review.
3. **Soft-deleted row still appears in unique-key conflicts.** A row with `(email) = ('x@y')` and `deleted_at IS NOT NULL` blocks creation of a new user with the same email. Correction: partial unique index `WHERE deleted_at IS NULL`, or move the unique constraint to a normalized email-claim table.
4. **Dead-letter row references data that has since been modified.** Replay produces an inconsistent state because the underlying entity has moved on. Correction: capture a snapshot reference at dead-letter time, and design replay as an explicit "compensate" operation, not a blind re-emit.
5. **Soft-delete on a heavily updated table degrades the planner.** Symptom: the partial index helps but other indexes still cover deleted rows. Correction: monitor the share of soft-deleted rows and run periodic `VACUUM FULL` or rebuild indexes; consider archiving the truly cold ones to a separate table that the live queries do not scan.
6. **Mixing soft-delete and dead-letter on the same row.** Two sources of truth for the outcome, leading to inconsistent reports. Correction: pick one; if both seem necessary, redesign the lifecycle with a clear state machine.

## Limitations

1. **Dead-letter tables do not solve poison messages on their own.** A row that fails every replay still needs a human or a schema change; tooling helps but cannot substitute for attention.
2. **Soft-delete is not a privacy tool.** Erasure law (GDPR right-to-erasure) requires the row to be unreadable, which a `deleted_at IS NULL` filter does not provide.
3. **Soft-delete does not bound storage.** The row still occupies disk and contributes to index size; only archival or purge bounds growth.
4. **Dead-letter tables assume the producer is retry-safe.** A pipeline whose messages cannot be safely replayed (idempotency keys missing) is unfit for dead-letter semantics; either add idempotency or move to a human review workflow.
5. **Neither pattern replaces backups.** Both are operational artefacts; a row lost to operator error is lost from the live table and the dead-letter table alike.

## Canonical sources

- Microsoft Azure Architecture Center, Dead-letter queues pattern: https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-dead-letter-queues
- PostgreSQL Documentation, Partial Indexes: https://www.postgresql.org/docs/current/indexes-partial.html
- PostgreSQL Documentation, Unique Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html