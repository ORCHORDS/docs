# latency-budget-allocation

**Issue:** A product requirement says "pages must load in under 1 second" or "API must respond in 300 ms", but nobody decomposes that number across the network hop, TLS handshake, server queueing, three backend calls, and the database query. Every team spends the full budget, the user-facing SLO is missed, and the ensuing argument cannot be settled because there is no agreed mapping from the end-to-end target to per-component limits. This article defines how to allocate a latency budget across a request path, express it as percentile SLOs, and measure each segment so violations point at the component that spent too much.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Foundations

1. **Averages lie, percentiles do not.** A mean of 80 ms is compatible with 5% of users waiting 2 seconds; p95/p99 targets are the only honest expression of "fast for users". Tail latency (p95, p99, p99.9) is where queueing, GC pauses, retries, and cold caches show up, and it is what fan-out architectures amplify.
2. **Sequential time adds; parallel time takes the max.** If steps run in sequence, their latency budgets sum to the end-to-end budget; if they run concurrently, the slowest one dominates. Write the budget as a dependency graph first — converting a sequential chain into parallel calls is often the cheapest way to "buy" budget.
3. **Fan-out multiplies tail probability.** A page rendering 50 parallel shard queries at 1% slow each will hit at least one slow shard in roughly 40% of requests; p99 per shard becomes p60 for the page. This is the core Dean-Barroso "tail at scale" argument: the top-level percentile target must be stricter than each component's.
4. **Budgets include retries and fallbacks.** A retry that re-executes a 250 ms call after a 250 ms timeout spends 500 ms plus the second attempt; timeouts, retry counts, and hedging policies are part of the latency budget, not an afterthought. Budget the worst configured path, not the happy path.
5. **Reserve headroom for growth and jitter.** Allocate at most 70-80% of the end-to-end budget to known components and leave the rest unassigned for network variance, load spikes, and new middleware. A budget at 100% utilization breaks with the first new feature.

## Budget Allocation Method

1. **Write down the end-to-end target as a percentile.** For example "p95 of authenticated GET /feed < 800 ms, p99 < 1.5 s", measured at the client (RUM) or the edge, not inside the app where the clock starts late. One number, one percentile, one measurement point — ambiguity here invalidates everything downstream.
2. **Trace the request and list every segment.** Use distributed tracing to enumerate real segments: edge/CDN, TLS, app queueing, auth, each downstream call, DB query, serialization. An allocation made against an imagined architecture (e.g., "the DB is 10 ms" from memory) is fiction; pull segment medians and p95s from actual trace data first.
3. **Assign each segment a p95 budget proportional to its controllability.** Components you own and can optimize get tighter budgets; third-party calls get their observed p95 plus retry cost, or get moved off the critical path asynchronously. Ensure the sum of sequential segments plus headroom equals the top-level budget; renegotiate the top-level target if the math refuses to close.
4. **Propagate deadlines downstream.** Pass a deadline (absolute timestamp, not a duration) with each internal call so backends know how much budget remains and can shed work that can no longer affect the response. When the deadline is spent, fail fast with partial content instead of burning CPU on an answer nobody is waiting for.
5. **Record the budget as an SLO per component.** Each segment's limit becomes a monitoring expression (e.g., histogram_quantile on the segment's latency metric), with an owner. Unowned budgets drift; put the table of segments, limits, and owners in the service's README or SLO catalog.

## Measurement and Instrumentation

1. **Measure histograms, not pre-aggregated averages.** Export latency as cumulative histograms (Prometheus-style le buckets or OTel explicit-bucket histograms) so percentiles can be computed per window; storing only mean/max destroys the tail information the budget is written against.
2. **Watch for percentile interpolation error.** Histogram buckets that are too coarse (e.g., le=1, le=10) make p99 estimates swing wildly; place bucket boundaries near your SLO values so pass/fail is resolvable. For very strict percentiles (p99.9), use high-density histograms (HDR-style) or log each latency event.
3. **Prefer client-side (RUM) verification of the top-level SLO.** Server-side timing misses DNS, connection setup, and queueing at the browser; reconcile RUM p75/p95 with server histograms monthly and investigate systematic gaps (usually network or render time).
4. **Check statistical sufficiency before trusting a percentile.** p99 of 200 requests per hour is 2 samples — noise; high percentiles on low-traffic services need longer windows or event-level storage (ClickHouse-style) to be meaningful. Align the percentile choice with request volume: p95 for small services, p99/p99.9 only where traffic supports it.
5. **Attribute each miss to a segment automatically.** When the end-to-end SLO breaches, the alert should name the slowest over-budget segment (trace-based analysis or per-segment SLO burn). "API is slow" pages are useless at 03:00; "payments-call p95 at 4x budget" is actionable.

## Enforcement and Operations

1. **Alert on budget burn rate, not threshold crossings.** A fast multi-window burn-rate alert (e.g., 14.4x over 1h, 6x over 6h against the segment SLO) catches real regressions while ignoring single-window noise. This mirrors error-budget alerting from SRE practice, applied to latency percentiles.
2. **Enforce budgets in CI with load tests.** Run a staged load test per release comparing segment p95s against the budget table; a regression that spends more than its segment's budget blocks merge, exactly like a failing unit test. Gatling/k6 percentile assertions are the usual mechanism.
3. **Treat deadline exceeded as a first-class signal.** Graph the rate of deadline-exceeded cancellations per dependency; a rise means a downstream component is silently eating budget and forcing work shedding upstream.
4. **Rebalance budgets after optimization, do not bank them.** When a segment gets faster, redistribute the freed budget to under-provisioned segments or lower the top-level target — otherwise teams backfill slack with new synchronous calls and the end-to-end SLO erodes again.
5. **Review the budget quarterly against product reality.** Latency targets set for a desktop US audience do not hold for mobile users on high-RTT networks; re-derive segment budgets from fresh RUM data when traffic mix, geography, or architecture changes materially.

## Related

performance-budget-setup, ttfb-optimization, load-testing-methodology, rum-vs-synthetic-metrics, continuous-profiling-production
