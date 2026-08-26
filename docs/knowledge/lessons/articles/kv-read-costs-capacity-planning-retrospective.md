# Capacity Planning Retrospective: Underestimating KV Read Costs at 10x Scale

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production
- **Category:** Capacity planning / retrospective

---

## Symptom

After a successful product launch drove 10x growth over four months, the platform's monthly Cloudflare bill increased by 34x rather than the expected 10x. Investigation revealed that KV read operations — which had been treated as "essentially free" in the capacity model — accounted for 61% of the unexpected cost increase. The team's cost model had assumed KV reads were negligible at 1x scale; at 10x scale they were the dominant cost driver.

---

## Context

Cloudflare KV is an eventually-consistent, globally-replicated key-value store. It is extremely fast for reads (typically 1–5 ms from edge cache) and designed for high read-to-write ratios. The platform used KV extensively for: feature flags, user preference caches, JWT revocation lists, rate-limit state, and content delivery manifests.

At 1x scale (launch), the platform served approximately 500,000 requests per day and incurred a KV bill below the threshold the team tracked carefully. The team's informal capacity model assumed "KV is cheap, don't worry about it." This assumption did not survive contact with 10x scale.

---

## Technical Sections

### 1. KV Billing Model: What "Per Read" Actually Means

Cloudflare KV bills per read operation, not per byte transferred. As of 2026:

- First 10 million reads/month: included in Workers paid plan
- Additional reads: $0.50 per million

This sounds cheap. The failure mode is that "reads" compound rapidly when multiple KV calls occur per Worker invocation.

At 1x scale:
- 500,000 requests/day × 30 days = 15M requests/month
- Average 4 KV reads per request = 60M reads/month
- After 10M free: 50M billable reads × $0.50 = $25/month

At 10x scale:
- 5,000,000 requests/day × 30 days = 150M requests/month
- Average 4 KV reads per request = 600M reads/month
- After 10M free: 590M billable reads × $0.50 = $295/month

This is a 10x increase in cost for a 10x increase in traffic — linear, as expected. But the team's model had not accounted for the KV reads at all in its 10x projection, causing a $270/month blind spot. When combined with similar oversights for D1 reads, Workers CPU time, and Queues operations, the total bill overshoot was 34x.

### 2. The "Reads Per Request" Multiplier

The most important input to a KV cost model is not request volume but reads per request. The platform's per-request KV read breakdown was:

| KV operation | Reads | Notes |
|---|---|---|
| Feature flags lookup | 1 | One KV key per user tier |
| User preference cache | 1 | Per authenticated user |
| JWT revocation check | 1 | Per request with auth token |
| Rate-limit state read | 1 | Per IP address |
| **Total** | **4** | Per authenticated request |

Four reads per request is not unusual. Teams that have more complex feature flag systems, multi-tenant configurations, or A/B test assignments can easily reach 8–12 KV reads per request. These multiply directly into cost at scale.

The correct approach is to model cost as:

```
monthly_kv_cost = max(0, (monthly_requests × reads_per_request) - 10_000_000) × 0.0000005
```

This formula should be part of every capacity plan. Use it with 1x, 3x, 10x, and 30x traffic projections.

### 3. Cache-Coalescing: Reducing Reads Per Request

The single most effective cost reduction strategy is to reduce reads per request by coalescing multiple KV lookups into a single read.

**Pattern: Config bundle key.** Instead of reading feature flags, user tier, and rate-limit config separately, store all per-tenant configuration as a single JSON blob under one key:

```ts
// Before: 3 reads
const featureFlags = await env.KV.get(`flags:${userId}`);
const userTier    = await env.KV.get(`tier:${userId}`);
const rateConfig  = await env.KV.get(`rate:${userId}`);

// After: 1 read
const config = JSON.parse(
  await env.KV.get(`config:${userId}`) ?? '{}'
);
const { featureFlags, userTier, rateConfig } = config;
```

This pattern reduces KV reads per request from 3 to 1 (a 66% cost reduction) at the cost of slightly larger payloads per read and more complex cache invalidation when any config component changes.

**Trade-off:** The config bundle must be invalidated and rewritten whenever any component changes. If feature flags change 100 times per day and the bundle contains 10 components that each change at different rates, the write amplification grows. Measure write frequency before adopting bundles.

### 4. In-Memory Caching Within a Worker Isolate

Workers can cache KV values in module-level memory. When a Worker isolate serves multiple requests (Cloudflare reuses warm isolates), a module-level cache avoids repeated KV reads:

```ts
// Module-level cache — survives across requests within the same isolate
const flagCache = new Map<string, { value: unknown; expiry: number }>();

async function getFlags(env: Env, userId: string): Promise<Flags> {
  const cached = flagCache.get(userId);
  if (cached && cached.expiry > Date.now()) {
    return cached.value as Flags;
  }
  const raw = await env.KV.get(`flags:${userId}`);
  const value = JSON.parse(raw ?? '{}');
  flagCache.set(userId, { value, expiry: Date.now() + 30_000 }); // 30s TTL
  return value;
}
```

**Caveats:**
- Module-level state is isolate-local. It is not shared across Workers instances or across data centres. The cache is warm only for requests served by the same isolate.
- Isolate eviction is non-deterministic. Do not rely on module-level state for correctness; use it only as a read-cost reduction with a short TTL.
- The cache is not subject to KV TTL or invalidation signals. If feature flags change, the module-level cache will serve stale values until its own TTL expires or the isolate is evicted.

Despite these limitations, module-level caching is the lowest-friction KV read cost reduction available. In practice, for feature flags and configuration that change at most a few times per hour, a 30-second module TTL eliminates 80–95% of KV reads on warm isolates.

### 5. KV Write Patterns and Cost

KV writes are billed at $5.00 per million (10x the read cost). The platform's write patterns were not a significant cost driver at 10x scale, but they become relevant if the platform writes frequently:

- Avoid per-request writes. Writes that must happen on every request (e.g., last-seen timestamps) should be batched or moved to a write-optimised store.
- Use write coalescing in a queue consumer. If rate-limit counters must be persisted, enqueue updates and flush them in a batch every 5 seconds rather than writing on each request.
- KV writes have a minimum billing granularity of 1 write per key per operation, regardless of value size. Writing a 1-byte value and a 10 KB value cost the same.

### 6. Building a Forward-Looking Cost Model

The team adopted a capacity planning template after this incident. Every significant traffic-impacting feature must include a cost projection table:

| Metric | 1x (now) | 3x | 10x | 30x |
|---|---|---|---|---|
| Monthly requests | 5M | 15M | 50M | 150M |
| KV reads/req | 4 | 4 | 4 | 4 |
| Total KV reads | 20M | 60M | 200M | 600M |
| KV read cost | $5 | $25 | $95 | $295 |
| D1 reads/req | 2 | 2 | 2 | 2 |
| Total D1 reads | 10M | 30M | 100M | 300M |
| D1 read cost | $2.50 | $10 | $40 | $120 |
| Workers CPU-ms/req | 5 | 5 | 5 | 5 |
| Workers CPU cost | $5 | $15 | $50 | $150 |
| **Estimated total** | **~$20** | **~$55** | **~$190** | **~$570** |

This table forces the team to surface the "reads per request" multiplier before deploying a feature, rather than discovering it at scale.

---

## Anti-Patterns

- **Treating KV reads as zero-cost in capacity models.** At low scale this is approximately true. At 10x+ scale, KV reads are a primary cost driver. Always include them in cost models.
- **Unbounded KV reads per request.** If the number of KV reads per request grows with feature additions (each new feature adds one more KV read), cost grows super-linearly with both features and traffic. Establish a per-request KV read budget (e.g., max 2 reads per request) and enforce it in code review.
- **Writing KV on every request.** KV writes cost 10x more than reads. Any pattern that writes to KV on every request will be expensive at scale. Rate-limit state, analytics, and similar high-frequency writes belong in a write-optimised path.
- **Not monitoring KV usage until the bill arrives.** The Workers dashboard shows KV operation counts in near-real time. Alert when KV reads exceed a threshold that would result in a bill above the cost target for the month.
- **Assuming KV cache TTLs solve everything.** KV has a built-in cache TTL (`expirationTtl`), but this controls when the key expires, not how long it is served from the Cloudflare edge cache. A short-lived key that is read frequently between writes still incurs a read charge on each access.

---

## Gotchas

- KV's 10M free read tier is shared across all KV namespaces in the account. It is not per-namespace. Teams with multiple products on the same Cloudflare account share the free tier.
- KV list operations are billed separately from read operations and are significantly more expensive per operation. Avoid `KV.list()` in hot paths.
- KV `getWithMetadata()` counts as one read but returns the value and metadata in one call. If you need both, this is more efficient than separate calls.
- KV read costs are incurred even if the key does not exist (a null result still costs one read). Negative-path KV checks (e.g., checking a revocation list for a token that is almost always valid) should be avoided in hot paths; invert the logic so that only exceptional states require a KV read.
- Cloudflare KV has a maximum value size of 25 MB. Config bundle keys that grow unboundedly will eventually hit this limit. Cap bundle sizes and split if necessary.

---

## Verification

After adopting config bundling and module-level caching:

1. KV reads per request dropped from 4 to 1.6 (module cache hit rate approximately 60% on warm isolates).
2. At the next traffic peak (equivalent to 10x baseline), KV read cost was $47 rather than the projected $295 — an 84% reduction.
3. The cost model template was validated: projected cost was $42; actual was $47 (10% variance, acceptable for a capacity model).

---

## Related

- `cost-optimization-cloudflare-stack.md`
- `cloudflare-storage-primitive-selection.md`
- `d1-write-contention-viral-event-postmortem.md`
- `workers-cpu-time-premature-optimization.md`
- `rate-limit-before-you-need-it.md`
- `capacity-forecast-error-review-loop.md`

---

## Sources

- Cloudflare KV pricing: https://developers.cloudflare.com/kv/platform/pricing/
- KV performance and caching: https://developers.cloudflare.com/kv/learning/how-kv-works/
- Workers module-level caching guidance: https://developers.cloudflare.com/workers/runtime-apis/cache/
- D1 pricing: https://developers.cloudflare.com/d1/platform/pricing/
