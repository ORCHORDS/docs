# Statistical Anomaly Detection with Z-Score in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers emit latency, error-rate, and throughput metrics to D1 every minute. You need an automated system that flags abnormal readings without hard-coding static thresholds — because "p99 > 500 ms" breaks every time traffic patterns shift. Z-score–based detection adapts to your actual baseline and fires alerts only when a reading is statistically unusual.

## Context

Z-score measures how many standard deviations a new observation sits away from the rolling mean. A |z| > 3 threshold captures ~0.3 % of readings under a normal distribution — rare enough to be actionable, common enough to catch real incidents before users complain.

Additional complexity comes from time-of-day seasonality (p99 at 03:00 UTC is naturally lower than at 14:00 UTC) and the need to avoid alert storms when multiple correlated metrics spike together. KV-backed cooldowns prevent duplicate pages during a single incident window.

Stack:
- **D1** — 1-minute metric snapshots (`metrics` table)
- **KV** — rolling window cache + alert cooldown flags
- **Analytics Engine** — anomaly event sink for dashboards
- **Queue** — fan-out to PagerDuty / Slack

## Solution

```typescript
// anomaly-detection.ts
import type { D1Database, KVNamespace, AnalyticsEngineDataset, Queue } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  ANOMALY_KV: KVNamespace;
  AE: AnalyticsEngineDataset;
  ALERT_QUEUE: Queue;
  ZSCORE_THRESHOLD: string;   // default "3"
  COOLDOWN_SECONDS: string;   // default "300"
  WINDOW_MINUTES: string;     // default "60"
  SEASONAL_BUCKETS: string;   // default "24" (hourly buckets)
}

interface MetricRow {
  ts: number;          // unix seconds
  metric: string;
  service: string;
  value: number;
}

interface RollingStat {
  mean: number;
  stddev: number;
  n: number;
}

interface AnomalyEvent {
  service: string;
  metric: string;
  value: number;
  z: number;
  mean: number;
  stddev: number;
  ts: number;
}

// ── rolling statistics ────────────────────────────────────────────────────────

function computeStats(values: number[]): RollingStat {
  const n = values.length;
  if (n === 0) return { mean: 0, stddev: 0, n: 0 };
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
  return { mean, stddev: Math.sqrt(variance), n };
}

function zScore(value: number, stat: RollingStat): number {
  if (stat.stddev === 0) return 0;
  return (value - stat.mean) / stat.stddev;
}

// ── seasonal bucket key ───────────────────────────────────────────────────────
// Splits the day into N equal-width buckets so we compare 14:05 only against
// other readings from the 14:xx hour, not the overnight quiet period.

function seasonalBucketKey(
  service: string,
  metric: string,
  tsSeconds: number,
  buckets: number
): string {
  const hourOfDay = Math.floor((tsSeconds % 86400) / (86400 / buckets));
  return `stat:${service}:${metric}:bucket${hourOfDay}`;
}

// ── fetch window from D1 ──────────────────────────────────────────────────────

async function fetchWindow(
  db: D1Database,
  service: string,
  metric: string,
  windowMinutes: number
): Promise<number[]> {
  const cutoff = Math.floor(Date.now() / 1000) - windowMinutes * 60;
  const rows = await db
    .prepare(
      `SELECT value FROM metrics
       WHERE service = ? AND metric = ? AND ts >= ?
       ORDER BY ts ASC`
    )
    .bind(service, metric, cutoff)
    .all<{ value: number }>();
  return rows.results.map((r) => r.value);
}

// ── KV stat cache ─────────────────────────────────────────────────────────────
// Persist rolling stats per seasonal bucket so the next cron invocation
// doesn't re-query 60 minutes of D1 history each time.

async function loadCachedStat(
  kv: KVNamespace,
  key: string
): Promise<RollingStat | null> {
  const raw = await kv.get(key, 'json');
  return raw as RollingStat | null;
}

async function saveCachedStat(
  kv: KVNamespace,
  key: string,
  stat: RollingStat,
  ttlSeconds = 7200
): Promise<void> {
  await kv.put(key, JSON.stringify(stat), { expirationTtl: ttlSeconds });
}

// ── alert cooldown ────────────────────────────────────────────────────────────

async function isCoolingDown(
  kv: KVNamespace,
  service: string,
  metric: string
): Promise<boolean> {
  const key = `cooldown:${service}:${metric}`;
  return (await kv.get(key)) !== null;
}

async function setCooldown(
  kv: KVNamespace,
  service: string,
  metric: string,
  ttlSeconds: number
): Promise<void> {
  await kv.put(`cooldown:${service}:${metric}`, '1', {
    expirationTtl: ttlSeconds,
  });
}

// ── multi-metric correlation ──────────────────────────────────────────────────
// Only escalate if ≥2 metrics for the same service are anomalous simultaneously.
// Single-metric spikes are demoted to "warn" level.

function correlationLevel(
  anomalies: AnomalyEvent[]
): 'critical' | 'warning' {
  const byService = new Map<string, number>();
  for (const a of anomalies) {
    byService.set(a.service, (byService.get(a.service) ?? 0) + 1);
  }
  for (const count of byService.values()) {
    if (count >= 2) return 'critical';
  }
  return 'warning';
}

// ── main scheduled handler ────────────────────────────────────────────────────

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const threshold = parseFloat(env.ZSCORE_THRESHOLD ?? '3');
    const cooldown = parseInt(env.COOLDOWN_SECONDS ?? '300', 10);
    const windowMinutes = parseInt(env.WINDOW_MINUTES ?? '60', 10);
    const buckets = parseInt(env.SEASONAL_BUCKETS ?? '24', 10);
    const nowSeconds = Math.floor(Date.now() / 1000);

    // Discover active service/metric pairs from the last 5 minutes.
    const pairs = await env.DB
      .prepare(
        `SELECT DISTINCT service, metric FROM metrics
         WHERE ts >= ? GROUP BY service, metric`
      )
      .bind(nowSeconds - 300)
      .all<{ service: string; metric: string }>();

    const anomalies: AnomalyEvent[] = [];

    for (const { service, metric } of pairs.results) {
      // Load or compute rolling stat for this seasonal bucket.
      const bucketKey = seasonalBucketKey(service, metric, nowSeconds, buckets);
      let stat = await loadCachedStat(env.ANOMALY_KV, bucketKey);

      if (!stat || stat.n < 10) {
        const values = await fetchWindow(env.DB, service, metric, windowMinutes);
        stat = computeStats(values);
        ctx.waitUntil(saveCachedStat(env.ANOMALY_KV, bucketKey, stat));
      }

      if (stat.n < 10) continue; // not enough data yet

      // Get the most recent reading.
      const latest = await env.DB
        .prepare(
          `SELECT value, ts FROM metrics
           WHERE service = ? AND metric = ?
           ORDER BY ts DESC LIMIT 1`
        )
        .bind(service, metric)
        .first<{ value: number; ts: number }>();

      if (!latest) continue;

      const z = zScore(latest.value, stat);

      if (Math.abs(z) > threshold) {
        const cooling = await isCoolingDown(env.ANOMALY_KV, service, metric);
        if (!cooling) {
          anomalies.push({
            service,
            metric,
            value: latest.value,
            z,
            mean: stat.mean,
            stddev: stat.stddev,
            ts: latest.ts,
          });
          ctx.waitUntil(
            setCooldown(env.ANOMALY_KV, service, metric, cooldown)
          );
        }
      }

      // Incrementally update the stat with the latest reading (Welford online).
      const newN = stat.n + 1;
      const delta = latest.value - stat.mean;
      const newMean = stat.mean + delta / newN;
      const delta2 = latest.value - newMean;
      const newM2 = stat.stddev ** 2 * stat.n + delta * delta2;
      const updatedStat: RollingStat = {
        n: newN,
        mean: newMean,
        stddev: Math.sqrt(newM2 / newN),
      };
      ctx.waitUntil(saveCachedStat(env.ANOMALY_KV, bucketKey, updatedStat));
    }

    if (anomalies.length === 0) return;

    const level = correlationLevel(anomalies);

    // Write to Analytics Engine for dashboards.
    env.AE.writeDataPoint({
      blobs: [level, JSON.stringify(anomalies.map((a) => a.service))],
      doubles: [anomalies.length, anomalies[0]?.z ?? 0],
      indexes: ['anomaly'],
    });

    // Fan-out alert to queue.
    await env.ALERT_QUEUE.send({ level, anomalies, detectedAt: nowSeconds });
  },
};
```

## Implementation Details

**Welford online algorithm** — rather than re-reading 60 minutes of history every minute, each cron run does a single-row D1 read for the latest value and updates the running mean/stddev using Welford's method. This reduces D1 reads from O(window) to O(1) per metric per cron tick.

**Seasonal decomposition** — the `seasonalBucketKey` function partitions the day into N time buckets (default 24 = hourly). Each bucket maintains its own rolling stat independently. A reading at 03:00 UTC is only compared against the 03:xx baseline, not the global 24-hour average, which eliminates false positives during off-peak hours.

**KV cache TTL** — stat objects are cached for 2 hours. The `expirationTtl` field means stale metrics (e.g., a service that went away) self-evict without manual cleanup.

**`ctx.waitUntil`** — KV writes are deferred so they don't block the critical D1 read path. The scheduled handler finishes sooner, avoiding the 30-second CPU limit.

## Anti-patterns

- **Static thresholds**: `if (latency > 500)` breaks during high-traffic periods when elevated latency is expected. Z-score adapts to the actual distribution.
- **Alerting on every anomalous tick**: Without the KV cooldown, a single 10-minute degradation produces hundreds of pages. The cooldown window (default 5 min) collapses storms into one alert per incident.
- **Global mean across all hours**: Comparing a 3 AM reading against a combined day/night mean inflates σ and misses real anomalies. Always bucket by time-of-day.
- **Skipping correlation**: A single metric spike could be a D1 measurement fluke. Requiring ≥ 2 correlated metrics before escalating to `critical` reduces noise pages.

## Gotchas

- **Cold start**: The first 10 readings per bucket are skipped (`stat.n < 10`). Deploy a backfill script that seeds the KV cache from historical D1 data on initial rollout.
- **Non-normal distributions**: Latency distributions are often right-skewed (log-normal). For latency metrics, apply `Math.log(value)` before computing Z-score to normalize the distribution.
- **KV eventual consistency**: In rare cases two cron instances may read the same stale stat and both fire alerts for the same metric. The cooldown key write from the first instance will suppress the second within seconds.
- **D1 row retention**: The `metrics` table must have a cleanup cron or a TTL-equivalent `DELETE WHERE ts < now - 7d` to keep query latency stable.

## Verification

```bash
# Insert a synthetic spike and confirm the alert fires.
npx wrangler d1 execute <DB_NAME> \
  --command "INSERT INTO metrics VALUES (strftime('%s','now'), 'api', 'p99_ms', 9999);"

# Tail queue consumer to see the alert payload.
npx wrangler tail --format pretty

# Confirm cooldown key is written.
npx wrangler kv key get --namespace-id=<ID> "cooldown:api:p99_ms"

# Query Analytics Engine for recent anomaly events.
curl -s "https://api.cloudflare.com/client/v4/accounts/<ACCT>/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  --data "SELECT blob1, SUM(_sample_interval) FROM <DATASET> WHERE index1='anomaly' GROUP BY blob1"
```

## Related

- `documentation/docs/policies/monitoring/metric-aggregation-cron-d1.md` — metric ingestion pipeline
- `documentation/docs/policies/monitoring/workers-error-budget-burn-rate.md` — SLO burn-rate alerting
- `documentation/docs/policies/monitoring/on-call-rotation-pagerduty.md` — alert routing

## Sources

- Cloudflare Workers Scheduled Handlers — https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- D1 Database — https://developers.cloudflare.com/d1/
- Workers KV — https://developers.cloudflare.com/kv/
- Welford online algorithm — Welford, B. P. (1962). *Technometrics*, 4(3), 419–420.
- Google SRE Workbook — Chapter 5: Alerting on SLOs
