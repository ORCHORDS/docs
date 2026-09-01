# Workers Analytics Engine SQL Boundaries

Workers Analytics Engine invites an appealing pattern: write high-cardinality events straight from a Worker, then query them with SQL. The boundary that trips teams is that Analytics Engine is not a general-purpose relational store. Its SQL interface targets a specific shape of workload — time-bucketed aggregation over sampled, pre-aggregated data — and it enforces that through a restricted SQL dialect, default sampling that trades exactness for scale, and cost behavior tied to ingested bytes and query shape. Teams that treat it like Postgres hit confusing empty results and silent approximation; teams that respect the boundaries get cheap, durable product analytics.

## Scope

Covers the Workers Analytics Engine SQL API: what the supported dialect does and does not include, how sampling changes what queries return, and how query cost and data density shape time-series workloads. Applies when designing schemas, choosing sample rates, or migrating queries from another analytics system. Excludes Workers Logpush, Workers Trace Events Logpush, and the GraphQL Analytics API used for account-level Cloudflare analytics.

## Workflow or implementation guidance

1. Model each dataset around its query patterns first. Because the dialect centers on time-bucketed aggregation, decide up front which fields are blobs (indexable by prefix matching), which are doubles, and which are timestamps; retro-fitting a schema after events exist is not possible.
2. Encode dimensions you will filter on into the blob with a deliberate prefix convention (for example `_a=tenant1,b=eu`), since blob prefix matching is the primary way to constrain scans. Unbounded, un-prefixed blobs defeat the index and make queries slow or empty.
3. Set `sampling` deliberately per write. The default is not guaranteed to persist every event; high-volume low-value events can accept aggressive sampling, while billing-relevant counters need either a lower sampling rate or client-side aggregation before the write.
4. Write queries against the supported subset: SELECT with FROM, WHERE on time range and blob prefixes, GROUP BY, ORDER BY, LIMIT, and time bucketing via the `_sample_interval` semantics and interval functions. JOINs and arbitrary nested subqueries are outside the boundary — plan pre-aggregation at write time instead of relational joins at read time.
5. Account for sampling in every result: multiply by the sampling factor when you need estimated counts, and treat small absolute numbers with suspicion because sampling variance dominates at low volumes.
6. Bound every query with an explicit time window. Unbounded time ranges are the fastest way to burn query budget against a large dataset.
7. Validate query cost behavior in a staging dataset loaded with production-scale volume before promoting dashboards, so a "cheap" query does not become an expensive one at real data density.

## Controls

- Schema review gate: new datasets require a written query-pattern list and blob prefix convention before the first event is written.
- Sampling decision record: each dataset documents its sampling rate, the reasoning, and the estimation multiplier used when reading it back.
- Time-window mandate: queries in production dashboards carry an explicit bounded interval; open-ended range queries are rejected in review.
- Approximation disclosure: any dashboard built on sampled data labels its numbers as estimates with the sampling factor stated.
- Query cost review for new dashboards: each new query is run against a production-scale copy and its observed cost recorded before the dashboard ships.
- Dataset retirement policy: datasets without an owner or a live dashboard for a defined period are disabled to stop silent ingestion cost.

## Validation evidence

- Dataset definition showing field roles (blob, double, timestamp) and the documented prefix convention.
- Sampling calibration run: a known event count injected at the chosen sampling rate, then queried back, with the estimation error measured and recorded.
- Dialect-conformance test: the production query set executed against a staging dataset, confirming every query parses and returns within the supported SQL subset.
- Time-window enforcement check: a lint or review record showing all dashboard queries declare bounded intervals.
- Cost observation for representative queries at production data density, captured before dashboard promotion.
- Approximation labels present on sampled-data dashboards, verified in a dashboard review.

## Failure modes and correction

- Queries return rows that look undercounted: sampling is discarding events. Either apply the correct estimation multiplier or lower the sampling rate for events that must be counted accurately.
- Blob filter matches nothing although the data is there: the prefix convention drifted (delimiters, key order, casing); standardize the encoding and re-verify with a small time window.
- A query needing a JOIN cannot be expressed: move the join logic to write time — emit pre-joined denormalized events — because the dialect will not acquire relational joins.
- Dashboard cost spikes after data density grows: tighten time windows, push more aggregation to write time, or reduce cardinality in blob prefixes to let pruning work.
- Small-numbers dashboards jitter day to day: sampling variance; increase sample retention for those events (reduce sampling) or aggregate client-side before writing.
- Events written with a malformed schema can never be re-shaped: the fix is a new dataset version and dual-writing during transition, not an in-place migration.

## Limitations

- The SQL dialect supports a subset of SQL; relational features like joins are not available.
- Sampling is integral to scaling the engine; exact counts for arbitrary high-volume events are not the design goal.
- Data is retained according to Analytics Engine retention rules rather than indefinite storage, so long-horizon analysis needs export.
- Schema changes effectively mean new datasets; existing written events cannot be transformed retroactively.
- Cardinality, while high, is achieved through sampling and pre-aggregation, so per-event fidelity is traded away by design.

## Canonical sources

- Cloudflare Analytics docs, "Workers Analytics Engine": https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Analytics docs, "SQL API": https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
