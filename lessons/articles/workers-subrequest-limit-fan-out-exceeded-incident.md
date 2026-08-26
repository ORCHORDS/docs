# Workers Subrequest Limit 50 Fan-Out Exceeded Incident

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A search aggregation Worker began throwing `Error: Too many subrequests` errors for roughly 12% of requests during a product launch event, causing the search results page to return 500s for any query that triggered the fan-out path. The errors appeared instantly with no degraded period—requests either succeeded or failed completely.

## Context

The platform uses a Cloudflare Worker as a search aggregation layer that fans out to multiple upstream data sources: a D1 database, several R2-backed content stores, a Vectorize index, and three external SaaS APIs. Under normal traffic the fan-out never exceeded 25 subrequests per invocation. During the launch a new "related content" feature was enabled that added up to 30 additional subrequests per query via a recursive similarity expansion loop. Cloudflare Workers enforce a hard limit of 50 subrequests per Worker invocation in the free and paid tiers; this limit is not surfaced as a warning—it throws immediately when the 51st subrequest is initiated.

## Timeline

- **09:14 UTC** — Feature flag for "related content" enabled in production via KV flag store.
- **09:17 UTC** — First `Too many subrequests` errors appear in Logpush stream; on-call sees spike in 5xx rate on search endpoint.
- **09:22 UTC** — Initial triage assumes external API timeouts; on-call checks SaaS status pages (all green).
- **09:31 UTC** — Error message text searched in codebase; `fetch()` call site count reviewed manually.
- **09:44 UTC** — Root cause identified: new related-content expansion adds up to 30 `fetch()` calls on top of existing 22, exceeding the 50 limit.
- **09:51 UTC** — Feature flag disabled via KV update; error rate drops to zero within 30 seconds.
- **10:05 UTC** — Temporary mitigation deployed: related-content path capped at 5 subrequests.
- **11:30 UTC** — Architectural fix merged: fan-out moved to a dedicated aggregation Worker invoked via Service Bindings with its own subrequest budget.

## Root Cause

The original search Worker accumulated subrequests from several independent features, each authored by different teams, with no shared accounting. When the related-content feature was added it was tested in isolation (8 subrequests) without measuring the cumulative invocation budget:

```typescript
// search-worker/src/index.ts  — pre-incident (simplified)

async function handleSearch(query: string, env: Env): Promise<Response> {
  // Core data fetches (22 subrequests in a busy query)
  const [d1Results, r2Docs, vectorResults] = await Promise.all([
    fetchD1Results(query, env),          // 1 subrequest
    fetchR2ContentBatch(query, env),     // up to 8 subrequests
    fetchVectorizeNeighbors(query, env), // 1 subrequest
    fetchExternalApi1(query, env),       // 1 subrequest
    fetchExternalApi2(query, env),       // 1 subrequest
    fetchExternalApi3(query, env),       // 1 subrequest
    // ... personalisation, ads, etc.    // ~9 subrequests
  ]);

  // NEW: related content expansion — added without subrequest audit
  const related = await expandRelatedContent(vectorResults, env);
  // expandRelatedContent itself fans out: 1 Vectorize + up to 29 R2 fetches
  // Total: 22 + 1 + 29 = 52 — exceeds limit of 50

  return buildResponse(d1Results, r2Docs, vectorResults, related);
}
```

The `expandRelatedContent` function fetched each related item's R2 object individually, one `fetch()` per item, with no batching:

```typescript
// Problematic expansion — each item is a separate subrequest
async function expandRelatedContent(
  neighbors: VectorizeMatch[],
  env: Env
): Promise<RelatedItem[]> {
  return Promise.all(
    neighbors.map(n => env.R2_CONTENT.get(n.id))  // N subrequests, N up to 30
  );
}
```

There was no static analysis, no runtime counter, and no integration test that ran with a realistically large `neighbors` array.

## Fix Applied

**Immediate mitigation** (deployed 10:05 UTC): cap the neighbor list before expansion.

```typescript
const MAX_RELATED_SUBREQUESTS = 5;

async function expandRelatedContent(
  neighbors: VectorizeMatch[],
  env: Env
): Promise<RelatedItem[]> {
  const capped = neighbors.slice(0, MAX_RELATED_SUBREQUESTS);
  return Promise.all(capped.map(n => env.R2_CONTENT.get(n.id)));
}
```

**Architectural fix** (deployed 11:30 UTC): offload heavy fan-out to a dedicated aggregation Worker via Service Binding, keeping each Worker's subrequest budget independent:

```typescript
// search-worker/src/index.ts — post-fix
async function handleSearch(query: string, env: Env): Promise<Response> {
  const [core, related] = await Promise.all([
    fetchCoreResults(query, env),                    // stays under 25 subrequests
    env.AGGREGATION_WORKER.fetch(                    // 1 subrequest to sibling Worker
      new Request('https://agg/related', {
        method: 'POST',
        body: JSON.stringify({ query }),
      })
    ),
  ]);
  return buildResponse(core, await related.json());
}

// aggregation-worker/src/index.ts — has its own 50 subrequest budget
export default {
  async fetch(request: Request, env: Env) {
    const { query } = await request.json();
    const neighbors = await fetchVectorizeNeighbors(query, env); // 1
    const items = await Promise.all(
      neighbors.map(n => env.R2_CONTENT.get(n.id))              // up to 30
    );
    return Response.json(items);
  },
};
```

## What We Learned

1. **Subrequest budgets are per-invocation and not additive across Service Bindings.** Each Worker invocation (including those reached via Service Binding) has its own independent 50-subrequest limit; splitting work across Workers is the correct pattern.
2. **Fan-out features must be reviewed against the cumulative invocation budget**, not tested in isolation. A new feature that adds 8 subrequests is safe in isolation but dangerous when the baseline is already 22.
3. **The limit throws immediately** with no graceful degradation or warning—there is no soft limit or queuing. Any code path that can exceed 50 must be capped defensively.
4. **Feature flags that add fan-out should be tested under load with realistic query shapes** that trigger the maximum branching factor.
5. **Ownership fragmentation is a budget fragmentation risk.** When multiple teams add subrequests to the same Worker without a shared registry, cumulative usage is invisible until it breaks.

## Prevention

- **Subrequest budget tracker**: add a lightweight runtime counter injected via middleware that logs cumulative subrequest count per invocation to Analytics Engine. Alert when p99 exceeds 40.

```typescript
// middleware/subrequest-counter.ts
export function wrapWithSubrequestCounter(handler: ExportedHandler): ExportedHandler {
  return {
    async fetch(request, env, ctx) {
      let count = 0;
      const originalFetch = globalThis.fetch;
      globalThis.fetch = (...args) => { count++; return originalFetch(...args); };
      try {
        return await handler.fetch!(request, env, ctx);
      } finally {
        env.ANALYTICS.writeDataPoint({ indexes: ['search'], doubles: [count] });
        if (count > 40) console.warn(`[SUBREQUEST_BUDGET] count=${count} path=${new URL(request.url).pathname}`);
      }
    },
  };
}
```

- **CI integration test**: add a test that runs `handleSearch` with a maximum-size result set and asserts the mock fetch call count stays below 45.
- **Architecture rule**: any feature adding more than 5 subrequests to an existing Worker requires a fan-out review in the PR checklist.
- **Service Binding fan-out pattern**: document and enforce via internal linting that Workers exceeding 30 baseline subrequests must delegate expansion work to a named aggregation Worker.

## Anti-patterns

- Adding subrequests to a shared Worker without auditing the existing budget.
- Testing new fan-out features in isolation rather than integrated with the full Worker invocation.
- Using `Promise.all()` over unbounded arrays where each element triggers a `fetch()`.
- Assuming the subrequest limit is enforced lazily or has a grace period—it is not.
- Relying on manual code review to catch subrequest count accumulation across team boundaries.

## Gotchas

- Service Bindings count as **one** subrequest from the calling Worker, but the bound Worker gets its own separate 50-subrequest budget—this is not obvious from the documentation and is the key escape hatch.
- `env.R2.get()`, `env.KV.get()`, and `env.D1.prepare().run()` all count as subrequests; only `env.DO.get()` (Durable Object stub access) and Vectorize calls within the same account consume the same budget.
- The limit applies to the **free tier and paid Workers plans equally**; it is not lifted by the Workers Paid plan, only by Enterprise negotiation.
- Retries inside a fetch wrapper that fails transparently can double-count subrequests against the budget.
- `ctx.waitUntil()` tasks share the same subrequest budget as the main request handler.

## Verification

After deploying the Service Binding split:
1. Run `wrangler tail` on the search Worker during a load test and confirm no `Too many subrequests` errors appear.
2. Check Analytics Engine for `subrequest_count` data points—p99 should be below 30 for the search Worker.
3. Run `wrangler tail` on the aggregation Worker and confirm its p99 subrequest count is below 35.
4. Enable the related-content feature flag and repeat the load test with a query shape that maximises neighbor expansion.

## Related

- [Logpush R2 Backpressure Dropped Observability](logpush-r2-backpressure-dropped-observability.md)
- [D1 Write Contention Viral Event Postmortem](d1-write-contention-viral-event-postmortem.md)
- [Workers CPU Time Premature Optimization](workers-cpu-time-premature-optimization.md)
- [Workers KV Namespace Key Limit Production Incident](workers-kv-namespace-key-limit-production-incident.md)

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#subrequests
- https://developers.cloudflare.com/workers/runtime-apis/service-bindings/
- https://developers.cloudflare.com/workers/observability/tail-workers/
