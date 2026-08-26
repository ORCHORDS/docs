# Workers Fetch Cache Hit Ratio Monitoring via Tail Workers and Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers make `fetch()` subrequests that should be cached by Cloudflare's edge cache, but you have no visibility into actual hit/miss ratios. Cache HIT rates silently degrade when TTL headers change or a new code path bypasses cache with explicit `no-store`.

## Context

Every response returned through Cloudflare's edge carries a `cf-cache-status` response header. A Tail Worker can read the outcome of each main-request event and write it to Analytics Engine for ratio trending and alerting.

## Understanding `cf-cache-status` Values

```typescript
type CacheStatus =
  | "HIT"         // Served from edge cache
  | "MISS"        // Fetched from origin, then cached
  | "EXPIRED"     // Cache entry expired, revalidated with origin
  | "STALE"       // Served stale while revalidation happens in background
  | "BYPASS"      // Cache was bypassed
  | "REVALIDATED" // Revalidation confirmed it was still fresh (304)
  | "UPDATING"    // Being updated
  | "DYNAMIC"     // Not cacheable
  | "NONE";       // Cache not consulted
```

## Tail Worker: Recording Cache Status per Request

```typescript
// tail-cache-monitor.ts
interface Env { AE: AnalyticsEngineDataset; }

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const cacheStatus = (event.cf as { cacheStatus?: string } | undefined)?.cacheStatus ?? "UNKNOWN";
      const isHit = cacheStatus === "HIT" || cacheStatus === "STALE" || cacheStatus === "REVALIDATED";
      const isServedFromEdge = isHit ? 1 : 0;
      const isOriginFetch = cacheStatus === "MISS" || cacheStatus === "EXPIRED" ? 1 : 0;
      const isBypassed = cacheStatus === "BYPASS" || cacheStatus === "DYNAMIC" ? 1 : 0;

      const rawPath = (event.logs?.[0] as unknown as { path?: string })?.path ?? event.scriptName ?? "unknown";
      const path = rawPath.split("?")[0].slice(0, 80);
      const method = (event as { method?: string }).method ?? "GET";

      env.AE.writeDataPoint({
        blobs: [cacheStatus, path, method],
        doubles: [isServedFromEdge, isOriginFetch, isBypassed, 1],
        indexes: [cacheStatus],
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Analytics Engine SQL Queries for Hit Ratio

```sql
-- Overall cache hit ratio (last 1 hour)
SELECT
  sum(double1) AS edge_served,
  sum(double2) AS origin_fetches,
  sum(double4) AS total_requests,
  round(sum(double1) * 100.0 / sum(double4), 2) AS hit_ratio_pct
FROM workers_cache_status
WHERE timestamp > NOW() - INTERVAL '1' HOUR;

-- Hit ratio by path prefix
SELECT
  blob2 AS path,
  sum(double4) AS requests,
  round(sum(double1) * 100.0 / sum(double4), 1) AS hit_pct,
  countIf(blob1 = 'BYPASS') AS bypass_count
FROM workers_cache_status
WHERE timestamp > NOW() - INTERVAL '6' HOUR
GROUP BY 1
HAVING requests > 50
ORDER BY hit_pct ASC
LIMIT 20;
```

## Anti-patterns

- **Logging full URL paths including query strings** — can leak PII.
- **Setting SLO on dynamic API routes** — `DYNAMIC` is expected for non-cacheable responses.
- **Ignoring `STALE` and `REVALIDATED` as misses** — both are edge-served.

## Gotchas

- `cf.cacheStatus` is `undefined` in Tail Workers for `DYNAMIC` responses on some runtime versions.
- Cache status varies by Cloudflare PoP; a global fleet will show `MISS` on the first request to each PoP.
- Workers with `Cache-Control: private` or `Set-Cookie` will always show `BYPASS`.

## Verification

1. Deploy Tail Worker with `tail_consumers = [{ service = "tail-cache-monitor" }]` in `wrangler.toml`.
2. Send 10 GET requests to a cacheable route; confirm the first is `MISS` and subsequent are `HIT`.
3. Query Analytics Engine:
```bash
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  --data-raw "SELECT blob1, count() FROM workers_cache_status GROUP BY 1"
```

## Related

- `kv-cache-hit-rate-analytics-engine-monitoring.md`
- `cache-hit-rate-monitoring.md`
- `tail-worker-structured-log-sampling-strategies.md`

## Sources

- Cloudflare Cache Status values: https://developers.cloudflare.com/cache/concepts/default-cache-behavior/
- Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
- Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
