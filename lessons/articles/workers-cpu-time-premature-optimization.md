# Lesson: Premature Optimization of Workers CPU Time vs Actual User Impact

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production
- **Category:** Engineering lesson / retrospective

---

## Symptom

A backend engineer spent two sprints (four weeks) optimising Workers CPU time on a project-metadata endpoint, reducing median CPU time from 4.2 ms to 1.1 ms per invocation. At the end of the sprint review, no user-visible latency improvement was measurable in production. P50 response time for the endpoint remained at 38 ms before and after the optimization. The team had optimised the wrong thing.

---

## Context

Cloudflare Workers bill CPU time, not wall-clock time. The billing model creates a natural incentive to minimise CPU time. Engineers sometimes internalise this metric as a proxy for user experience quality. The reasoning is intuitive but often wrong: CPU time is only one component of response latency, and frequently not the dominant one.

This lesson documents what the team learned about the relationship between Workers CPU time, wall-clock latency, and actual user-perceived performance.

---

## Technical Sections

### 1. The CPU Time / Wall-Clock Latency Gap

In a Cloudflare Worker, the runtime is event-driven. When your Worker awaits an async operation (a fetch, a KV read, a D1 query, a Durable Object stub call), CPU execution suspends. The wall clock keeps running; the CPU time meter does not.

This means:
- A Worker that makes a 30 ms D1 query records 30 ms of wall-clock time but approximately 0.1 ms of CPU time for the await itself
- Reducing CPU time from 4 ms to 1 ms saves 3 ms of CPU execution but saves zero milliseconds of D1 query latency
- The user experiences the sum of all wall-clock time: CPU time + IO wait + network round-trips

In the incident above, the metadata endpoint broke down as follows:

| Component | Wall-clock time |
|-----------|----------------|
| Worker startup (no cold start; warm) | 0.1 ms |
| D1 read — metadata query | 28 ms |
| KV read — feature flags | 6 ms |
| JSON serialisation | 0.4 ms |
| Response write | 0.1 ms |
| **Total** | **~35 ms** |

The engineer optimised JSON serialisation and the metadata transformation logic, cutting CPU time from 4.2 ms to 1.1 ms. But D1 and KV reads — which together accounted for 34 ms of wall-clock time — were untouched. The net user-visible improvement was negligible.

### 2. When CPU Time Optimisation Is Worth It

CPU time optimisation is valuable in exactly two situations:

**Situation A: Cost reduction at high volume.** If a Worker invokes 100 million times per day and CPU time is 50 ms per invocation (5 billion CPU-ms/day = ~1.4 million CPU-seconds), reducing CPU time by 50% cuts the Workers bill by ~50%. This is a legitimate financial engineering concern at scale.

**Situation B: CPU time is the actual latency bottleneck.** If an endpoint does heavy synchronous computation — parsing, crypto, data transformation, compression — without any async IO, then CPU time and wall-clock time converge. Optimising CPU time directly improves user latency. This applies to: large JSON parsing, image manipulation via WebAssembly, cryptographic signing, complex business rule evaluation over large in-memory datasets.

For endpoints that perform any async IO (the majority of real-world Worker endpoints), CPU time is the wrong optimisation target if the goal is user-perceived latency.

### 3. Finding the Real Latency Driver

Before optimising anything, profile where wall-clock time is actually spent. The Workers platform provides this via Workers Trace Events and the `performance.now()` API:

```ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const t0 = performance.now();

    const t1 = performance.now();
    const metadata = await env.DB.prepare(
      'SELECT * FROM projects WHERE id = ?'
    ).bind(projectId).first();
    const dbMs = performance.now() - t1;

    const t2 = performance.now();
    const flags = await env.FLAGS.get(userId);
    const kvMs = performance.now() - t2;

    const t3 = performance.now();
    const body = JSON.stringify(transform(metadata, flags));
    const cpuMs = performance.now() - t3;

    const totalMs = performance.now() - t0;

    // Emit to Analytics Engine for aggregation
    env.ANALYTICS.writeDataPoint({
      blobs: [request.url],
      doubles: [dbMs, kvMs, cpuMs, totalMs],
      indexes: ['latency_profile'],
    });

    return new Response(body);
  }
};
```

Run this instrumentation for one week. Aggregate by endpoint. The component with the largest `doubles` value is the correct optimization target.

### 4. IO Latency Reduction Strategies

Once the real bottleneck is identified, common strategies for IO-bound Workers:

**Cache aggressively upstream.** If metadata changes rarely, serve it from the Cloudflare cache (`Cache-Control: s-maxage=60`) and skip the D1 read entirely for most requests. A cache hit has near-zero IO cost.

**Read from KV instead of D1 for hot, read-heavy data.** KV reads from the regional edge are typically 1–3 ms for cache-hot keys, versus 20–40 ms for D1 reads that traverse to the primary. For data that is read far more than written, denormalise into KV.

**Parallelise independent reads.** If the Worker needs data from both D1 and KV and neither depends on the other, await them in parallel:

```ts
// Sequential: 28 ms + 6 ms = 34 ms total IO
const metadata = await env.DB.prepare(...).first();
const flags = await env.FLAGS.get(userId);

// Parallel: max(28 ms, 6 ms) = 28 ms total IO
const [metadata, flags] = await Promise.all([
  env.DB.prepare(...).first(),
  env.FLAGS.get(userId),
]);
```

This single change — parallelising two independent reads — saves 6 ms of wall-clock time. The engineer's two-sprint CPU optimisation saved 0 ms of user-perceived latency. The parallelisation took 10 minutes.

**Use D1 read replicas.** D1 serves reads from regional replicas. Ensure the Worker is not forcing primary reads by passing `{ readFromPrimary: false }` (the default for SELECT statements). If a query is marked as requiring fresh data, remove that flag if eventual consistency is acceptable.

**Reduce round-trips with batching.** If the handler makes three sequential D1 queries that each need the result of the previous, consider whether the logic can be expressed as a single SQL query with joins or CTEs.

### 5. Cold Starts vs CPU Time

A separate — and often confused — performance concern is cold start latency. A cold start occurs when a Worker must be loaded into a new isolate. Cold starts add 5–30 ms of latency but are invisible in CPU time metrics because the billing model counts CPU time only after the Worker is running.

Cold starts are addressed by:
- Reducing Worker bundle size (tree-shake dependencies; prefer small native Workers APIs over large npm packages)
- Ensuring the Worker handles enough traffic to stay warm in Cloudflare's isolate pool
- Using Durable Objects (which have their own isolate lifecycle) judiciously

Optimising CPU time of a cold-starting Worker is doubly misdirected: the visible latency is caused by isolate instantiation, not by the Worker's compute logic.

### 6. The Cost Argument: When to Optimise CPU Time Anyway

Even if CPU time does not affect user latency, it does affect your bill. The Workers paid plan bills at $0.02 per million CPU-milliseconds (2026 pricing). At 8 million requests/day:

| CPU time per request | Daily CPU-ms | Monthly cost |
|----------------------|-------------|-------------|
| 10 ms | 80B | ~$48 |
| 5 ms | 40B | ~$24 |
| 1 ms | 8B | ~$4.80 |

CPU time optimisation for cost reasons is rational once the platform is past product-market fit and is at a scale where the bill is a material input cost. Before that point, engineer time is more valuable than CPU cost savings.

---

## Anti-Patterns

- **Using CPU time as a proxy for user latency.** CPU time is a billing metric. User latency is a product metric. They are related but not equivalent. Always measure wall-clock latency at the edge (or, better, from a real-user monitoring perspective) when evaluating performance work.
- **Optimising before profiling.** The engineer in this case assumed JSON serialisation was slow because it "looked expensive." Profiling would have immediately shown that D1 and KV reads were the bottleneck.
- **Reporting CPU time reduction as a latency win to stakeholders.** This creates false confidence and erodes trust in performance metrics. Report P50/P95/P99 wall-clock latency to stakeholders, not CPU time.
- **Over-indexing on micro-benchmarks.** Writing a benchmark that measures JSON.stringify performance in isolation tells you nothing about the endpoint's end-to-end latency under real traffic patterns.
- **Parallelising reads as an afterthought.** Sequential awaits for independent IO operations are the single most common low-effort, high-impact performance fix in Workers code. Review every multi-IO handler for sequential awaits before doing any other performance work.

---

## Gotchas

- `performance.now()` in Workers measures wall-clock time, not CPU time. Use it for latency profiling. Workers CPU time is only visible in the billing dashboard and via the `cf-ray` trace.
- D1 query latency varies by region. A query from a Worker running in Frankfurt to a D1 primary in North America may see 80+ ms latency. Check the D1 primary region and consider whether it aligns with your traffic geography.
- KV reads are served from the regional cache if the key has been accessed recently. First access to a cold KV key can be 50+ ms. Warm reads are 1–5 ms. Latency profiling should be done after cache warm-up.
- `Promise.all()` on D1 queries runs them concurrently from the Worker's perspective, but D1 serialises writes. For read queries, true parallelism is achieved; for writes, the parallelism is limited by D1's write lock.
- Workers CPU time billing uses the 99th percentile of a sample, not the mean. Outliers matter for billing even if they are invisible in P50 latency graphs.

---

## Verification

The team validated the lesson by:

1. Adding latency breakdown instrumentation to the top 10 endpoints by request volume.
2. Identifying that 7 of 10 endpoints had sequential awaits for independent IO.
3. Parallelising those reads. Measured P50 latency improvement: 8–22 ms per endpoint.
4. Comparing against the CPU time optimisation (zero user-visible improvement). The ratio of engineer time to user-visible latency improvement was approximately 200:1 in favour of parallelisation.

---

## Related

- `index-before-not-after-performance-problem.md`
- `n-plus-one-queries-compound-at-scale.md`
- `cloudflare-storage-primitive-selection.md`
- `cost-optimization-cloudflare-stack.md`
- `developer-experience-dx-cloudflare-workers.md`

---

## Sources

- Cloudflare Workers CPU time billing: https://developers.cloudflare.com/workers/platform/limits/
- D1 performance guidance: https://developers.cloudflare.com/d1/best-practices/
- Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Workers performance.now() API: https://developers.cloudflare.com/workers/runtime-apis/performance/
