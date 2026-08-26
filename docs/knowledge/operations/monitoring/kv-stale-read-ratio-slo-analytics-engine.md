# KV Stale Read Ratio SLO with Analytics Engine

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Workers KV is an eventually consistent store. Under normal conditions, most reads return the latest written value within a few seconds of propagation. However, after a large key update or during a PoP failover, reads at edge locations may temporarily return stale values. If your application treats KV reads as authoritative — for feature flags, configuration, or session tokens — an elevated stale read ratio silently corrupts user-facing behaviour without triggering any error-rate SLO.

You need an SLO on KV read freshness and an alert when the stale read ratio burns your error budget faster than expected.

## Context

KV does not natively expose a staleness metric. The measurement strategy is to embed a version token in every KV write, read it back through your Worker, and compare it against the ground-truth version stored in an authoritative source (Durable Objects, D1, or a versioned Workers Secret). Each read is classified as **fresh** (version matches) or **stale** (version lags). The ratio `stale / (stale + fresh)` is the stale read ratio.

Results are written to Analytics Engine for SLO burn-rate alerting using the same multi-window approach as HTTP error budgets.

## KV Write with Version Token

```typescript
// src/kv-versioned.ts

export interface KVVersioned<T> {
  version: number;   // Unix timestamp ms of the write
  value: T;
}

/**
 * Write a value with a version token.
 * The authoritative version is stored separately (e.g. in D1 or a global counter).
 */
export async function kvPut<T>(
  kv: KVNamespace,
  key: string,
  value: T,
  version: number,
  ttlSeconds?: number
): Promise<void> {
  const payload: KVVersioned<T> = { version, value };
  await kv.put(key, JSON.stringify(payload), ttlSeconds ? { expirationTtl: ttlSeconds } : undefined);
}

/**
 * Read a value and classify it as fresh or stale.
 * `expectedVersion` is the latest version known from the authoritative source.
 */
export async function kvGetWithFreshnessCheck<T>(
  kv: KVNamespace,
  key: string,
  expectedVersion: number
): Promise<{ value: T | null; fresh: boolean; lagMs: number }> {
  const raw = await kv.get(key);
  if (raw === null) {
    return { value: null, fresh: false, lagMs: Date.now() - expectedVersion };
  }

  const parsed: KVVersioned<T> = JSON.parse(raw);
  const lagMs = expectedVersion - parsed.version;
  const fresh = lagMs <= 0; // version matches or is ahead (ahead means client clock skew)

  return { value: parsed.value, fresh, lagMs: Math.max(0, lagMs) };
}
```

## Worker Instrumentation

```typescript
// src/index.ts
import { kvGetWithFreshnessCheck } from './kv-versioned';

export interface Env {
  CONFIG_KV: KVNamespace;
  AE: AnalyticsEngineDataset;
  /** The latest config version, stored in a Workers Secret or fetched from D1. */
  CURRENT_CONFIG_VERSION: string;
}

const CONFIG_KEY = 'app_config';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const expectedVersion = Number(env.CURRENT_CONFIG_VERSION);
    const { value: config, fresh, lagMs } = await kvGetWithFreshnessCheck<Record<string, unknown>>(
      env.CONFIG_KV,
      CONFIG_KEY,
      expectedVersion
    );

    // Record the read result to Analytics Engine
    ctx.waitUntil(Promise.resolve().then(() => {
      env.AE.writeDataPoint({
        // blob1 = key, blob2 = freshness, blob3 = colo
        blobs:   [CONFIG_KEY, fresh ? 'fresh' : 'stale', String(request.cf?.colo ?? 'unknown')],
        // double1 = lag_ms, double2 = 1 (read count)
        doubles: [lagMs, 1],
        indexes: [CONFIG_KEY],
      });
    }));

    if (!config) {
      return new Response('Config unavailable', { status: 503 });
    }

    return new Response(JSON.stringify({ config, fresh, lagMs }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Analytics Engine Queries

```sql
-- Stale read ratio over the last 5 minutes (for alerting)
SELECT
  countIf(blob2 = 'stale')                         AS stale_reads,
  countIf(blob2 = 'fresh')                         AS fresh_reads,
  count()                                           AS total_reads,
  countIf(blob2 = 'stale') / count()               AS stale_ratio,
  quantileWeighted(0.95)(double1, _sample_interval) AS p95_lag_ms
FROM kv_freshness
WHERE
  blob1 = 'app_config'
  AND timestamp >= NOW() - INTERVAL '5' MINUTE;
```

```sql
-- 1-hour stale read ratio by colo — identify specific PoPs with propagation delays
SELECT
  blob3                                 AS colo,
  countIf(blob2 = 'stale') / count()   AS stale_ratio,
  count()                               AS reads
FROM kv_freshness
WHERE
  blob1 = 'app_config'
  AND timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY colo
HAVING reads > 100
ORDER BY stale_ratio DESC
LIMIT 20;
```

```sql
-- SLO burn rate: compare the 5-minute window against the 1-hour window
-- Error budget target: stale_ratio <= 0.01 (1% stale reads)
-- Short-window burn rate = (5m stale ratio / 0.01)
-- Long-window burn rate  = (1h stale ratio / 0.01)

WITH
  short_window AS (
    SELECT countIf(blob2 = 'stale') / count() AS ratio
    FROM kv_freshness
    WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
  ),
  long_window AS (
    SELECT countIf(blob2 = 'stale') / count() AS ratio
    FROM kv_freshness
    WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  )
SELECT
  short_window.ratio / 0.01 AS short_burn_rate,
  long_window.ratio  / 0.01 AS long_burn_rate
FROM short_window, long_window;
```

## Alerting Worker (Scheduled)

```typescript
// src/slo-alert.ts
// Cron: every 5 minutes ("*/5 * * * *")

export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  AE_DATASET: string;
  ALERT_WEBHOOK: string;
  SLO_TARGET: string;   // e.g. "0.99" → 99% fresh reads
}

async function queryBurnRates(env: Env): Promise<{ short: number; long: number }> {
  const sloTarget = Number(env.SLO_TARGET ?? '0.99');
  const errorBudget = 1 - sloTarget; // e.g. 0.01

  const sql = `
    WITH
      s AS (SELECT countIf(blob2='stale')/count() AS r FROM ${env.AE_DATASET}
             WHERE blob1='app_config' AND timestamp >= NOW() - INTERVAL '5' MINUTE),
      l AS (SELECT countIf(blob2='stale')/count() AS r FROM ${env.AE_DATASET}
             WHERE blob1='app_config' AND timestamp >= NOW() - INTERVAL '1' HOUR)
    SELECT s.r/${errorBudget} AS short_burn, l.r/${errorBudget} AS long_burn
    FROM s, l
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  const json = await res.json<{ data: Array<{ short_burn: number; long_burn: number }> }>();
  const row = json.data[0] ?? { short_burn: 0, long_burn: 0 };
  return { short: row.short_burn, long: row.long_burn };
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const { short, long } = await queryBurnRates(env);

    // Multi-window page threshold: short burn > 14x AND long burn > 14x
    // (fires when ~2% of the 30-day error budget is consumed in 1 hour)
    const shouldPage = short > 14 && long > 14;
    // Ticket threshold: short burn > 3x AND long burn > 3x
    const shouldTicket = !shouldPage && short > 3 && long > 3;

    if (shouldPage || shouldTicket) {
      const severity = shouldPage ? 'page' : 'ticket';
      ctx.waitUntil(
        fetch(env.ALERT_WEBHOOK, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: `KV stale read SLO alert [${severity}]: 5m burn=${short.toFixed(1)}x, 1h burn=${long.toFixed(1)}x`,
          }),
        })
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml
name = "kv-slo-alert"
main = "src/slo-alert.ts"

[triggers]
crons = ["*/5 * * * *"]

[vars]
SLO_TARGET   = "0.99"
AE_DATASET   = "kv_freshness"
```

## Anti-patterns

- **Inferring staleness from cache-hit headers**: The `CF-Cache-Status` header reflects Cloudflare's HTTP cache, not KV storage. KV reads within a Worker bypass the HTTP cache entirely — this header is irrelevant for KV freshness measurement.
- **Using TTL as a staleness proxy**: A short TTL forces frequent KV re-fetches but does not tell you whether the returned value is fresh at the moment of read. Version tokens are the only reliable freshness signal.
- **Setting the SLO target to 100% fresh reads**: KV propagation is eventually consistent by design. Targeting 100% treats normal propagation delays (typically < 60 s) as SLO violations. Set the target to reflect the tail of expected propagation latency — 99% or 99.5% is more appropriate.
- **Measuring freshness only in one colo**: KV propagation delays are PoP-specific. A single colo measurement underreports global staleness. Instrument all serving colos and segment by `colo` in your queries.

## Gotchas

- **Version source of truth must be consistent**: If `CURRENT_CONFIG_VERSION` is a Workers Secret, it is only updated on each `wrangler deploy`. For higher-frequency writes, use D1 or Durable Objects to store and serve the current version — not a static secret.
- **Clock skew between Workers**: Workers on different PoPs may have millisecond-level clock skew. If the version token is a Unix timestamp and the reading Worker's clock is slightly ahead, `lagMs` can be negative even for a fresh read. Clamp to `Math.max(0, lagMs)` as shown.
- **KV read caching in the Worker runtime**: By default, KV `.get()` calls are cached in the Worker's local memory for up to 1 second within a single isolate. If you call `kvGetWithFreshnessCheck` multiple times per request, subsequent calls may return the isolate-cached value even if KV was updated between calls. Use `kv.get(key, { cacheTtl: 0 })` to bypass this for freshness checks — but be aware this increases KV read costs.
- **Analytics Engine write limits**: Analytics Engine allows up to 25 writes per request, and each Worker can write up to 1000 data points per second. High-traffic Workers should sample freshness checks (e.g. 1% of requests) to stay within limits, then use `_sample_interval` weighting in queries.

## Verification

```bash
# Manually write a stale version to KV (set version 0) and verify detection
wrangler kv key put --namespace-id=<NS_ID> app_config '{"version":0,"value":{}}'

# Invoke the Worker and check Analytics Engine for a stale write
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob2 AS freshness, count() AS n FROM kv_freshness WHERE timestamp >= NOW() - INTERVAL '\''2'\'' MINUTE GROUP BY freshness"}' \
  | jq '.data'

# Restore correct version
wrangler kv key put --namespace-id=<NS_ID> app_config "{\"version\":$(date +%s%3N),\"value\":{}}"
```

## Related

- `workers-kv-latency-consistency-monitoring.md` — KV operation latency monitoring
- `kv-operation-rate-analytics-engine.md` — KV read/write rate tracking
- `slo-alerting-burn-rate.md` — burn-rate alerting methodology
- `multiwindow-burn-rate-slo-alerts.md` — multi-window SLO alert configuration

## Sources

- Cloudflare Workers KV consistency model: https://developers.cloudflare.com/kv/reference/how-kv-works/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Google SRE Workbook — multi-window burn rate alerting: https://sre.google/workbook/alerting-on-slos/
