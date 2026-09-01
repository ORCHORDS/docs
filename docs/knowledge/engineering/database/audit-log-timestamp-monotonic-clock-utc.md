# Audit Log Timestamp Monotonic Clock UTC

## Scope

This article covers timestamp correctness in database audit logs: storing instants in UTC, the difference between transaction time (`now()`/`CURRENT_TIMESTAMP`), statement time, and true wall-clock time (`clock_timestamp()`), and how to preserve monotonic ordering within an audit trail. It addresses the recurring incidents where audit rows appear out of order, carry client-supplied or ambiguous timestamps, or become unusable as evidence because of timezone drift. It covers PostgreSQL specifics for generation plus portable schema guidance, and it excludes application-side clock synchronization (NTP) details and event-sourcing designs.

## Workflow or implementation guidance

1. **Store instants, not civil times.** Use `timestamptz` (or an equivalent timezone-aware type) for every audit column. `timestamp` without time zone forces every reader to know an unstated convention; `timestamptz` normalizes to UTC internally and renders per session timezone, which is the only convention that survives multiple teams.
2. **Generate timestamps in the database, never from the client.** An audit row written with `DEFAULT now()` carries the server's transaction start time, which is authoritative, cluster-consistent, and impossible for a caller to forge in the same way a request payload is. Client clocks are untrusted input for audit purposes.
3. **Understand which "now" you are getting.** `now()` and `CURRENT_TIMESTAMP` return the *transaction start* time and are constant within a transaction — exactly right for audit rows that must agree with each other. `clock_timestamp()` returns the actual current instant and advances within a transaction — required when you need true elapsed-time deltas or strictly increasing values per row. `statement_timestamp()` and `transaction_timestamp()` sit between these and are documented distinctions worth checking whenever ordering surprises appear.
4. **When in-row monotonicity is required, do not rely on timestamp resolution.** Two rows written in the same microsecond (or on hardware with coarser resolution) produce ties. Add a monotonic sequence: a `bigint` identity column, or a composite ordering key of `(txn_id, seq)` where `txn_id` comes from `txid_current()` and `seq` is assigned by the trigger. Timestamps then carry meaning, sequence carries order.
5. **Write audit rows from triggers, in the same transaction as the change.** A `BEFORE`/`AFTER` trigger per audited table inserting into a shared audit table guarantees the audit row commits or rolls back with the operation it describes. Out-of-band audit writers (a separate service reading the WAL later, an application-level logger) are useful supplements but cannot provide the atomicity guarantee that makes an audit trail defensible.
6. **Record both the event time and the recording time when they can differ.** If audit ingestion is asynchronous, store `event_at` (source-supplied, validated) alongside `recorded_at` (`DEFAULT now()`), so backfilled or delayed events are visibly distinguishable from contemporaneous ones.
7. **Reject or normalize non-UTC input at the boundary.** When events arrive with an offset (ISO 8601 with `+02:00`), parse to an instant and store it; when they arrive with no offset, treat the offset as unknown rather than silently assuming UTC — an explicit `event_tz` column or a rejection policy prevents the silent corruption that later reads as "the log says 3 a.m. but the incident was at 3 p.m.".
8. **Keep clock-dependent assertions out of tests unless they assert ordering, not equality.** Tests that assert an exact stored timestamp couple themselves to execution timing; tests that assert row N's ordering key is greater than row N-1's capture the property that matters.

## Controls

1. **Column-type linting.** A migration check that rejects new `timestamp`/`timestamp without time zone` columns on audit-path tables, requiring `timestamptz`.
2. **Default and trigger enforcement.** Audit insert paths carry `DEFAULT now()`; no application code path passes an explicit timestamp for the recording column.
3. **Composite ordering key.** Every audit table has a documented ordering key (for example `recorded_at, audit_id`) and consumers order by that key, never by a single timestamp alone.
4. **Session timezone pinned in tooling.** Reporting connections set `TimeZone=UTC` explicitly so rendered timestamps are identical across developer machines, dashboards, and exports.
5. **Untrusted-source validation.** Ingested events with an `event_at` more than a bounded skew (for example 5 minutes) from `now()` are flagged in a quarantine column or table rather than silently accepted.
6. **Gap and ordering monitor.** A scheduled check that the audit table's ordering key is strictly increasing and that per-minute row counts show no unexplained zero-minute gaps during known traffic.

## Validation evidence

1. **Same-transaction consistency test.** In one transaction, insert an entity and let its trigger write an audit row; assert both rows carry identical `now()`-derived timestamps, and that after rollback neither row exists.
2. **Monotonicity test.** Insert 10,000 audit rows across 50 concurrent transactions; assert the composite ordering key is strictly increasing when results are sorted by it, with zero ties on the sequence component.
3. **Timezone render test.** Set two sessions to `America/New_York` and `Asia/Tokyo`, select the same audit row, and confirm the rendered wall times differ by exactly the offset difference while the stored value is unchanged.
4. **Skew quarantine test.** Submit an event with `event_at` four hours in the past and one two minutes in the past; assert the former is quarantined and the latter is accepted, evidencing the boundary control.
5. **Round-trip precision test.** Write microsecond-precision instants through the application and read them back; assert equality to the stored precision, confirming no driver-side truncation to seconds is silently degrading ordering granularity.

## Failure modes and correction

1. **Ties and inversions in a microsecond-resolution timestamp.** Symptom: audit rows whose "later" event has an equal or earlier timestamp. Correction: add the monotonic sequence to the ordering key; keep the timestamp for human meaning.
2. **Ambiguous local-time storage.** Rows stored as naive local time become wrong twice a year across DST transitions. Correction: migrate to `timestamptz`, backfilling by interpreting the old values in the then-applicable offset recorded in metadata, and add the type linting control.
3. **Client-supplied audit times.** A compromised or merely clock-skewed client produces an audit trail that contradicts server-side evidence. Correction: database-generated `recorded_at`, with client times quarantined to a separate validated column.
4. **Misreading `now()` as wall-clock elapsed time.** Code computing duration between two `now()` samples inside one transaction always gets zero. Correction: use `clock_timestamp()` for intra-transaction measurement; reserve `now()` for agreement semantics.
5. **Replica-clock confusion.** Audit queries run against a replica lagging behind the primary make recent events look missing. Correction: route ordering-sensitive audit reads to the primary or accept and display the measured replication lag alongside results.
6. **Silent driver truncation.** Some drivers or ORMs map timestamp columns to second precision. Correction: precision round-trip tests in CI and explicit column typemaps.

## Limitations

1. **Database timestamps are only as trustworthy as the server clock.** A host clock step (NTP correction, VM migration) can produce instants that move backwards; `now()` cannot fix a broken system clock.
2. **Monotonic sequence keys are monotonic per sequence, not globally time-meaningful.** They prove order, not duration, and they are not comparable across tables with independent sequences.
3. **`timestamptz` microsecond precision bounds ordering granularity** at one million values per second per sequence; sufficiently concurrent workloads still need the composite key.
4. **Audit trails in the same database share the fate of that database.** A dropped table or a malicious superuser can alter them; tamper-evidence requires external append-only storage or hash chaining, which this article does not cover.
5. **Distributed multi-database audit trails have no shared clock**, so cross-system ordering requires a coordination mechanism beyond timestamps.

## Canonical sources

- PostgreSQL Documentation, Date/Time Functions and Operators — current date/time distinctions: https://www.postgresql.org/docs/current/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT
- PostgreSQL Documentation, Data Types — Date/Time Types: https://www.postgresql.org/docs/current/datatype-datetime.html
- PostgreSQL Documentation, Runtime Config — Client Defaults (TimeZone): https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-TIMEZONE
