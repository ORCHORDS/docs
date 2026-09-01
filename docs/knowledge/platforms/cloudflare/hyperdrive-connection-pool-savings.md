# Hyperdrive Connection Pooling Savings Analysis

Every time a Worker opens a fresh TCP plus TLS connection to a faraway Postgres or MySQL server, it pays a heavy fixed cost before the first query byte moves. Hyperdrive removes that cost two ways: it keeps warm connection pools near the database so Workers grab an established connection instead of negotiating one, and it caches the results of popular read-only queries so many queries never reach the database at all. Both mechanisms save latency and database capacity, but they save different things and must be measured separately. A savings analysis that lumps them together cannot tell whether the win came from pooling, caching, or neither.

## Scope

Covers quantifying Hyperdrive's savings for Workers talking to supported SQL databases: connection establishment elimination, query result caching behavior, and measurement design that separates the effects. Applies to adoption decisions, renewal reviews, and post-migration performance verification. Excludes database-side tuning (indexes, query plans), read replica architectures, and D1 migrations where the database itself is being replaced.

## Workflow or implementation guidance

1. Define the metrics before migration: cold-connection latency (full TCP/TLS/handshake time from a Worker's location to the database), per-query latency, queries per second, read/write ratio, and database connection counts.
2. Measure the baseline with the Worker connecting directly, capturing connection setup time separately from query execution time. If the client library pools connections in-process, note that Workers' isolates do not share long-lived connections the way a traditional server does — the baseline must reflect Worker reality, not a long-running Node process.
3. Estimate the pooling benefit: for query-heavy short exchanges, savings approach the connection establishment cost per invocation; for few-queries-per-invocation patterns the same fixed saving is amortized over less work, so the relative gain shrinks.
4. Estimate the caching benefit independently: identify repeated read-only queries eligible for caching, their frequency, and their result staleness tolerance. Default caching applies to read-only queries with a short max age; anything needing fresh data opts out and cannot be counted as cache savings.
5. Classify queries into cacheable (read-only, repetition, tolerance for a short staleness window) and uncacheable (writes, reads feeding decisions that must be current). The cacheable share bounds the maximum caching win.
6. Migrate the Worker to Hyperdrive in staging with the same database, then re-measure the same metrics with identical query load. Keep caching disabled for the first pass to isolate the pooling effect, then enable caching and measure again for the combined effect.
7. Compute the three numbers side by side: direct baseline, pooled-only, pooled-plus-cached. Report latency percentiles and database-side connection/arrival counts, not just averages.
8. Set expectations for review: caching savings depend on traffic mix that drifts, so schedule a re-measurement after a quarter rather than treating the initial figure as permanent.

## Controls

- Metric definition gate: the analysis names its metrics and measurement method before any migration work begins.
- Pooling-versus-caching separation: results are reported in two layers (pooling alone, then with caching) so effects are attributable.
- Cache eligibility register: queries marked cacheable carry a stated staleness tolerance; anything without one defaults to uncacheable.
- Same-database comparison rule: before/after measurements run against the same database instance and dataset to remove database variance.
- Percentile reporting requirement: p50 and p95 at minimum; mean-only reports are rejected.
- Staleness-sensitive query audit: any query feeding authorization, balances, or ordering is verified uncacheable before go-live.

## Validation evidence

- Baseline measurement report: connection setup latency distribution, query latency distribution, and query mix, with the measurement method stated.
- Pooled-only measurement (caching disabled) over an identical load, with per-query latency deltas.
- Pooled-plus-cached measurement, with cache hit behavior visible in the observed latency split for eligible queries.
- Query classification table: cacheable, uncacheable, and the staleness tolerance recorded per cacheable class.
- Database-side evidence: connection arrival rate or active connection counts before and after, corroborating the pooling effect.
- Side-by-side summary table: baseline, pooled-only, pooled-plus-cached across p50/p95 latency and throughput.

## Failure modes and correction

- Savings look negligible: the workload is write-heavy or queries are unique, so pooling only saves connection setup. Correct expectations, or restructure to batch queries so each connection use does more work.
- Cached results serve stale data to a sensitive flow: the query was misclassified cacheable; move it to uncacheable and add it to the audit list.
- Caching win evaporates over time as traffic mix shifts: re-run the measurement per the quarterly control and reclassify queries against the new mix.
- Comparison contaminated by database-side changes (index added, load changed): re-baseline both sides in the same window; the same-database rule exists for this.
- Client library assumptions from traditional servers skew the baseline: measure from a Worker, not a long-lived process, because connection reuse semantics differ.
- Report shows only averages and hides a p95 regression for uncached queries under queueing at the pool: percentile reporting surfaces it; investigate pool saturation at peak.

## Limitations

- Caching applies to read-only queries; write-heavy workloads see pooling benefits only.
- Cache behavior is governed by a short max-age default and per-query opt-outs; exact staleness windows follow current product documentation.
- Savings depend on the Worker-to-database distance that existed before adoption; nearby databases show smaller pooling gains.
- Database-side connection-count evidence depends on database introspection access, which may be limited in managed environments.
- Quarterly re-measurement is necessary because traffic mix, not configuration, drives the caching share.

## Canonical sources

- Cloudflare Hyperdrive docs, "Hyperdrive (Postgres & MySQL)": https://developers.cloudflare.com/hyperdrive/
- Cloudflare Hyperdrive docs, "Query caching": https://developers.cloudflare.com/hyperdrive/concepts/query-caching/
