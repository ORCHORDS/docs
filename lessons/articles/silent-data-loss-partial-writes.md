# silent-data-loss-partial-writes

**Issue:** Nothing errors. The API returns 200, the job logs "success," the dashboard looks normal — and six weeks later a customer asks why their June records are missing. Silent data loss from partial writes happens whenever a logical operation spans multiple physical writes (two tables, a database plus a search index, a row plus object storage) and completes only some of them; the system records success for the whole because each individual step succeeded or the failure was swallowed. It is the worst incident class because detection time is measured in weeks, the missing data's absence produces no logs, and recovery depends on sources (binlogs, provider exports, client-side remains) that may themselves have expired. The curated postmortem collections (danluu's index documents multiple cases where data loss reappeared on several servers after a buggy hotfix, and GitLab 2017 remains the canonical story of discovering, mid-incident, that the backups you assumed existed had silently not run) show that the defining failure is usually not the write bug — it's the absence of anything that would have told you.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How silent partial writes happen

1. **Multi-step writes without a transaction boundary.** Update the orders table, then enqueue the fulfillment event, then write the audit log — step two fails after a timeout is caught-and-logged, and the request still returns success because the handler decided the core step finished. Each future reader of the log glosses over the WARN.
2. **Dual writes to heterogeneous stores.** Database commit succeeds, search-index or cache update fails, and nothing reconciles the two. The divergence grows for months and is only noticed when a query path changes to rely on the secondary store.
3. **Swallowed errors in batch pipelines.** A bulk import marks the batch complete if any threshold of rows succeed; per-row failures are written to a report nobody reads. The definition of "done" quietly diverged from "complete."
4. **Client-side partial sends.** Mobile or offline-first apps queue writes locally and sync later; a sync bug discards unacked items after a reauthentication, and the server never knew they existed. The data loss happens on devices you don't have logs from.
5. **Schema-drift nulls.** A migration adds a column, writers fill it, a deploy rolls back to code that doesn't, an integration later treats the null as "delete." The data was destroyed by an interaction of two individually-reasonable changes.

## Why it stays undetected

1. **No error, no alert, no log line.** The monitoring stack is built to catch things that fail loudly. Absence of data generates zero signals — you cannot page on a count that is lower than it should have been when nobody knows the expected count.
2. **Reads hide the hole.** UIs render whatever exists; a record with a missing child object looks identical to one that never had it. Users who notice often assume user error and don't report it, stretching MTTD further.
3. **Verification was point-in-time.** The restore test passed, the reconciliation job ran during the release week and was then disabled for performance — verification that isn't continuous decays into false confidence, the precise pattern of GitLab's backup discovery.
4. **The gap predates the report.** By the time anyone asks, the loss is weeks old; binlog retention has rolled over, provider data-export windows have closed, and the tamper-evident evidence you need was itself expired by policy.

## Detection strategies

1. **Continuous reconciliation, not one-time checks.** Run a scheduled job that independently recomputed counts/checksums across the stores involved in multi-step writes and alerts on divergence beyond epsilon. The job is boring infrastructure until it is the only thing standing between you and a six-week data hole.
2. **Invariant checks on every logical object.** An order must have exactly one fulfillment event; a user must have exactly one profile row. Cheap per-object invariants asserted at read time (or in a nightly sweep) convert silent absence into a loud error.
3. **Outbox pattern as a canary.** Writes go through a transactional outbox; a growing outbox (rows written but not processed) is an explicit, monitorable backlog of incompleteness — partial writes become visible as unprocessed rows instead of invisible as missing rows.
4. **Population metrics on business entities.** Track daily created-row counts per core entity with seasonality-aware alerting. A 4% drop in signups-completed on Tuesdays is often the first honest signal that some writes vanish.

## Prevention patterns

1. **Single-writer, transactional core.** If the write matters, it commits in one transactional store. Fan-out to secondary stores happens via events from the outbox — never synchronously in the request path where its failure must be swallowed to keep latency sane.
2. **Idempotent, resumable write APIs.** Every logical write gets an idempotency key and a state machine (pending, committed, propagated) so a retry resumes at the true frontier instead of re-deciding what "done" means.
3. **Fail closed on secondary failure, by choice.** Make the tradeoff explicit: either the request fails when propagation can't complete, or it succeeds with a durable marker of incompleteness. The bug is never the choice — it's making no choice and thereby defaulting to "silently half-done."
4. **Test the middle of the write.** Chaos-style integration tests that kill the process (or drop the network) between step one and step two of every multi-step write, then assert the system either completes or surfaces incompleteness. Partial-failure tests are the only tests that catch partial failures.

## Response and recovery

1. **Freeze expiry clocks first.** When loss is discovered, immediately extend log and backup retention (binlogs, CDC streams, provider exports) — the recovery sources are still expiring while you investigate, and the incident's first hour determines whether week-old data is recoverable at all.
2. **Bound the damage before fixing the cause.** Quantify the window (first bad deploy to now) and the affected entity set from the pipeline's own logs; communicate "rows X..Y for tenants Z" rather than "some data may be missing," which users correctly read as evasion.
3. **Recover from independent copies.** The recovery source must not be the system that lost the data: CDC/archive topics, client-side caches, or provider exports. Restoring from the primary's own backups reproduces the hole that the backup faithfully captured.
4. **Postmortem the detection, not just the bug.** The write bug gets fixed in a day; the lesson that matters is why weeks passed without a signal, and the action items are reconciliation jobs, invariant checks, and retention freezes — the detection layer that was missing.
