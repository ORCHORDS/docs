# read-replica-lag-handling

**Issue:** Offloading reads to Postgres replicas is the standard scaling move, but streaming replication is asynchronous by default, so a replica can be milliseconds or minutes behind the primary. Users then see ghosts: a write succeeds, the next request is routed to a replica that has not replayed it yet, and the row "disappears". The engineering problem is threefold — measuring lag honestly, routing so that read-your-writes and monotonic-read expectations hold, and reducing lag when it grows — without quietly turning the scaling win into a correctness bug.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Measuring lag honestly

1. **The three lag columns.** On the primary, `pg_stat_replication` exposes `write_lag`, `flush_lag`, and `replay_lag` — the time from local WAL flush to the standby's write, flush, and replay confirmation respectively. `replay_lag` is the number that matters for read-after-write staleness. Monitor it per replica, not averaged.
2. **Bytes beat seconds for bursty traffic.** `pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)` gives lag in bytes. The time-based columns only reflect recently-committed transactions and go stale during quiet periods; a byte delta stays truthful and converts to "how much work remains" rather than "how long since the last commit".
3. **NULL is ambiguous.** `replay_lag` is NULL when the standby has simply had nothing to do — which also means it is caught up — or when feedback has not arrived. Never alert on the timestamp columns alone; pair every time alert with the LSN-diff alert.
4. **Measure on both sides.** On the standby, `pg_last_wal_receive_lsn()` versus `pg_last_wal_replay_lsn()` splits lag into "network/walreceiver behind" versus "replay behind" — the two halves have different fixes (network versus a single replay process bogged down in I/O or long queries).

## Read-your-writes patterns

1. **Sticky-primary window.** After a user performs a write, route that user's reads to the primary for a short window (1–5 seconds, tracked in a cookie or session). Simple, no protocol changes, covers the vast majority of "my post vanished" complaints; the cost is that the busiest users never use replicas.
2. **LSN token (causal reads).** Capture `pg_current_wal_lsn()` on write; before serving a replica read, check `pg_last_wal_replay_lsn() >= token` and either wait briefly or fall back to the primary. This is the rigorous version of the sticky window and is what "causal consistency" modes in routers implement.
3. **`synchronous_commit = remote_apply` for critical writes.** Transactions with this setting (per-role or per-transaction) do not acknowledge until a synchronous standby has replayed them, making subsequent replica reads correct by construction. Reserve it for login/session writes and payment state — applied globally it prices every commit at a round trip plus replay.
4. **Monotonic reads need pinning.** Even without read-your-writes, a user bouncing between replicas can see time move backwards (a row reappears after deletion). Pin a user/session to one replica (or route by consistent hashing) so a session never observes replay reversing.

## Routing with bounded staleness

1. **Lag-aware replica selection.** The router picks among replicas only those whose measured lag is under a threshold (e.g. under 100 ms / under a few MB); if none qualify, fall back to the primary. This converts "replicas are usually fine" into a guarantee with a defined staleness bound.
2. **Fail open on the primary, not on stale reads.** When in doubt, route to the primary. A slightly hotter primary is an operational event; serving a payment confirmation from two minutes ago is an incident.
3. **Tag requests, not code paths.** Attach a consistency requirement to each request (fresh, eventual, or session-bound) at the edge, and let one routing layer interpret it. Consistency rules scattered through handlers are unmaintainable.
4. **Watch for hotspot reads.** Any query that must be fresh (auth checks, balance reads) is not a replica query; move it to the primary explicitly and stop pretending the pool will figure it out.

## Reducing lag at the source

1. **Kill long transactions on the primary.** Lag usually grows because replay cannot proceed past a WAL record while vacuum-holding or replication-slot-holding transactions stay open; alert on transaction age, not just lag symptoms.
2. **Sized WAL volume surprises.** Bulk updates, `VACUUM FULL`, index builds, and DDL generate enormous WAL bursts that take replicas minutes to replay; schedule them off-peak and rate-limit batch sizes.
3. **Tune the standby, not just the primary.** Replay is single-process: fast storage on standbys, `hot_standby_feedback` evaluated deliberately (it prevents conflicts at the cost of primary bloat), and `max_standby_streaming_delay` bounded so a reporting query cannot pause replay indefinitely.
4. **Decompose lag in dashboards.** Netdata/Cybertec-style breakdowns separate network transfer, disk flush, and apply time; alerting on the total without knowing the component produces useless 3 a.m. pages.

## Operating practice

1. **Alert on lag bytes and on trend.** Page on sustained lag growth (e.g. lag bytes rising for 5 minutes) rather than instantaneous spikes; a single burst query is not worth waking anyone.
2. **Include lag in deploy reviews.** New query patterns (a heavier index, a chatty job) often show up first as replica lag; graph lag around deploys.
3. **Rehearse replica loss.** Losing one replica should shift reads to others plus primary fallback without user-visible errors — test the router's failover path, not just the database's.
