# D1 Read Replication Consistency Models

D1 global read replication places read replicas closer to users so reads do not pay a round trip to the primary's location. The trade is consistency: a replica serves data that may lag the primary, because replication is asynchronous. An application that reads its own write through a replica can see stale data — a saved profile that appears unsaved, a submitted order absent from the list — unless the read path is deliberately pinned to the primary or the session logic honors read-your-writes. The D1 Sessions API exists to make that explicit rather than accidental. This article defines how to reason about, configure, and validate consistency when reads are served from replicas.

## Scope

Covers D1 with read replication enabled: the Sessions API, choosing replica versus primary reads, stale-read risk assessment, and validation of read-your-writes behavior. Applies to Workers using a D1 binding where replication has been or will be enabled. Excludes replica failover and promotion during regional failures, write-path tuning, and Time Travel restores.

## Workflow or implementation guidance

1. Classify every read path before enabling replication. Sort them into three buckets: strictly consistent reads that must reflect all prior writes (post-write confirmations, authorization checks, read-modify-write sequences), session reads that must reflect the current user's writes (profile views after save), and tolerance reads where seconds of staleness are invisible (public catalogs, analytics widgets).
2. Enable read replication and adopt the Sessions API on the binding. Sessions track which writes the current session has observed, so reads issued through a session after that session's write are routed to the primary or a replica known to include the write, instead of an arbitrary replica.
3. Route the strictly consistent bucket explicitly to the primary: with the Sessions API this means issuing those reads in a context where consistency demands it, using the first-sync or explicit primary-read semantics the API provides, rather than hoping a nearby replica is current.
4. Leave the tolerance bucket on default replica routing — that is where the latency win lives — and confirm each such endpoint really is staleness-tolerant by asking what breaks if it is 10 seconds behind.
5. Instrument staleness where it matters: log the bookmark or sequence information available from the session when a read is served, so you can measure observed lag on session reads rather than infer it.
6. Load the read path with a write-then-read test at each user-facing flow: perform a write, immediately read the affected view, and assert the write is visible. Automate this as a regression test so refactors cannot silently downgrade a session read to a bare replica read.
7. Review new features against the same classification before launch; the failure mode is a new read path added casually with default routing that turns out to need read-your-writes.

## Controls

- Read-path classification register: every D1-backed read endpoint is labeled strict, session, or tolerant, and the label is updated when the endpoint's semantics change.
- Sessions API adoption requirement: enabling replication without the Sessions API on the binding is a blocked change.
- Write-then-read regression suite: automated tests covering each session-class flow, run on every deploy.
- Staleness budget per endpoint: tolerant reads carry a documented acceptable staleness figure, reviewed when replication lag behavior changes.
- Primary-routing allowlist: strict reads that pin to the primary are listed, so the primary's load is knowable and bounded.
- Replication-lag monitoring: observed lag metrics are watched, with an alert that triggers review when lag exceeds the tightest staleness budget in the register.

## Validation evidence

- The read-path classification register with per-endpoint labels and owners.
- Write-then-read test results per session-class flow, passing on a deployment with replication enabled.
- Staleness measurement output: observed lag distribution on session reads over a representative window.
- Configuration record showing replication enabled and Sessions API semantics in use on the binding.
- Latency comparison for tolerant reads, primary versus replica, demonstrating the latency win being pursued.
- Review note for each new read path added since the last audit, with its assigned class.

## Failure modes and correction

- User saves data and immediately sees the old value: the read path skipped session semantics (bare database call, new code path, or a cached response). Correct by routing that read through the session-aware binding or the primary, and add the flow to the regression suite.
- Authorization or read-modify-write logic hits a replica and acts on stale data: reclassify as strict and pin to the primary; correctness beats latency for these paths.
- Caching layer sits in front of replica reads and extends effective staleness beyond the replication lag: set cache TTLs for session-class responses to zero or make them vary with the session bookmark.
- Cross-device flows expect read-your-writes but sessions are per-request, not per-user: the write from device A may not be visible to device B through a replica; either pin those reads to the primary or accept and document the window.
- Primary load grows after too many paths were labeled strict: re-audit the strict allowlist, push genuinely tolerant paths back to replicas, and re-verify each demotion with the staleness question.
- A refactor replaced session-aware calls with generic helpers: caught only by the regression suite — which is why the suite is mandatory, not optional.

## Limitations

- Replication is asynchronous; replicas lag the primary, and only deliberate routing choices bound what users observe.
- Sessions provide read-your-writes within a session; they do not provide serializable global ordering across independent sessions.
- Primary-pinned reads surrender the latency benefit, so over-classifying as strict erodes the reason replication was enabled.
- Observed lag depends on write volume and geography; budgets validated at one traffic level may not hold at another.
- Failover and replica promotion scenarios follow different rules and are outside this article's scope.

## Canonical sources

- Cloudflare D1 docs, "Global read replication": https://developers.cloudflare.com/d1/best-practices/read-replication/
- Cloudflare D1 docs, "Time Travel and backups" (context for D1 operational tooling): https://developers.cloudflare.com/d1/reference/time-travel/
