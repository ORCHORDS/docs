# KV TTL Expiration and Eviction Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

KV keys written with a TTL silently vanish after expiration. If TTLs are set too short,
requests that expect a cached value get a `null` read and fall through to D1 or an
upstream API, causing unexpected load spikes. If TTLs are set too long, stale data
accumulates. Neither condition is visible in the Cloudflare dashboard. Without
instrumentation you cannot distinguish a cold cache (empty namespace at startup) from a
cache with pathologically short TTLs (expiring before the next read), or detect that
eviction rates have spiked after a deployment change.

## Context

KV does not emit TTL-expiration events; keys simply stop being readable after their
`expiration` time. The monitoring approach is indirect: instrument every KV read and
record whether it returned `null` alongside the key's metadata (specifically the
`expiration` field available from `getWithMetadata`). When a key exists in KV but was
expected to be present and the read returns `null`, that is either expiration or a
genuine miss. Correlating the miss rate with the expected TTL and the read timestamp
lets you identify premature expiration.

Writes with TTL are recorded separately so you can compute the ratio of expected-alive
keys to actual hits at any point in time.

## Instrumented KV Read with Expiration Metadata

```typescript
// kv-monitor.ts
export type KvReadOutcome = "hit" | "miss_expired" | "miss_never_written" | "miss_unknown";

export interface KvReadEvent {
  namespace: string;
  keyPrefix: string; // first 32 chars — avoid logging full keys if they contain user IDs
  outcome: KvReadOutcome;
  remainingTtlSeconds: number; // 0 if miss
  valueAgeSeconds: number;     // seconds since the key was written (from metadata)
}

export async function monitoredKvGet<T>(
  kv: KVNamespace,
  env: Env,
  namespace: string,
  key: string,
  writtenAt?: number // Unix ms, passed from write-side metadata
): Promise<T | null> {
  const result = await kv.getWithMetadata<T, { writtenAt: number }>(key, "json");

  const now = Date.now();
  const valueAgeSeconds =
    result.metadata?.writtenAt != null
      ? Math.round((now - result.metadata.writtenAt) / 1_000)
      : 0;

  let outcome: KvReadOutcome;
  if (result.value !== null) {
    outcome = "hit";
  } else if (result.metadata?.writtenAt != null) {
    outcome = "miss_expired";
  } else {
    outcome = "miss_never_written";
  }

  // Remaining TTL: KV does not expose it directly on null reads; record 0
  const remainingTtlSeconds = result.value !== null ? -1 : 0; // -1 = unknown for hits

  env.ANALYTICS.writeDataPoint({
    blobs: [namespace, key.slice(0, 32), outcome, ""],
    doubles: [remainingTtlSeconds, valueAgeSeconds, now],
    indexes: [namespace],
  });

  return result.value;
}
```

## Instrumented KV Write with TTL Metadata

```typescript
// kv-write.ts
export async function monitoredKvPut<T>(
  kv: KVNamespace,
  env: Env,
  namespace: string,
  key: string,
  value: T,
  ttlSeconds: number
): Promise<void> {
  const writtenAt = Date.now();

  await kv.put(key, JSON.stringify(value), {
    expirationTtl: ttlSeconds,
    metadata: { writtenAt },
  });

  env.ANALYTICS.writeDataPoint({
    blobs: [namespace, key.slice(0, 32), "written", ""],
    doubles: [ttlSeconds, 0, writtenAt],
    indexes: [namespace],
  });
}
```

## Querying Miss Rate and Expiration Ratio per Namespace

```typescript
// expiration-metrics.ts
export interface KvExpirationMetrics {
  hitRate: number;
  expirationMissRate: number; // miss_expired / total reads
  neverWrittenMissRate: number;
  avgValueAgeOnHitSeconds: number;
}

export async function fetchKvExpirationMetrics(
  env: Env,
  namespace: string,
  windowHours = 24
): Promise<KvExpirationMetrics> {
  const query = `
    SELECT
      blob3 AS outcome,
      COUNT() AS n,
      AVG(double2) AS avg_age_seconds
    FROM kv_read_events
    WHERE timestamp > NOW() - INTERVAL '${windowHours}' HOUR
      AND blob1 = '${namespace}'
    GROUP BY outcome
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const { data } = await resp.json<{
    data: Array<{ outcome: string; n: number; avg_age_seconds: number }>;
  }>();

  const byOutcome = Object.fromEntries(data.map((r) => [r.outcome, r]));
  const total = data.reduce((s, r) => s + r.n, 0);

  return {
    hitRate: total > 0 ? (byOutcome["hit"]?.n ?? 0) / total : 0,
    expirationMissRate: total > 0 ? (byOutcome["miss_expired"]?.n ?? 0) / total : 0,
    neverWrittenMissRate: total > 0 ? (byOutcome["miss_never_written"]?.n ?? 0) / total : 0,
    avgValueAgeOnHitSeconds: byOutcome["hit"]?.avg_age_seconds ?? 0,
  };
}
```

## Alerting on High Expiration-Miss Rate via Scheduled Worker

```typescript
// expiration-alert.ts
// Cron: "*/15 * * * *"
const NAMESPACES = ["sessions", "feature-flags", "rate-limits"];
const EXPIRATION_MISS_THRESHOLD = 0.15; // 15%

export async function checkExpirationRates(env: Env): Promise<void> {
  for (const ns of NAMESPACES) {
    const metrics = await fetchKvExpirationMetrics(env, ns, 1);

    if (metrics.expirationMissRate > EXPIRATION_MISS_THRESHOLD && metrics.hitRate + metrics.expirationMissRate > 0.01) {
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text:
            `KV namespace \`${ns}\`: expiration-miss rate is ` +
            `${(metrics.expirationMissRate * 100).toFixed(1)}% over the last hour ` +
            `(threshold: ${EXPIRATION_MISS_THRESHOLD * 100}%). ` +
            `Average value age on hit: ${Math.round(metrics.avgValueAgeOnHitSeconds)}s. ` +
            `Consider increasing TTL or pre-warming cache keys.`,
        }),
      });
    }
  }
}
```

## Anti-patterns

- Inferring expiration from `kv.get()` returning `null` alone — a `null` could mean the
  key was never written, was deleted explicitly, or expired; storing `writtenAt` in
  metadata is what makes the distinction possible.
- Using the same Analytics Engine dataset name for KV reads and writes — query logic is
  simpler when reads and writes are in separate datasets with clearly named blob fields.
- Setting extremely short TTLs (`expirationTtl: 60`) on high-read keys to force
  "freshness" — the result is a thundering herd on cache miss; use background refresh
  (stale-while-revalidate) instead.
- Logging the full KV key in Analytics Engine blobs when keys contain user IDs, tokens,
  or PII — truncate or hash keys before recording them.

## Gotchas

- `kv.getWithMetadata` returns `metadata: null` (not an empty object) when the key was
  never written or has expired AND had no metadata; always null-check before accessing
  `metadata.writtenAt`.
- KV expiration is eventually consistent — a key may remain readable for up to 60 seconds
  past its `expiration` time due to edge caching; do not alert on a single-sample miss
  immediately after TTL boundary.
- `expirationTtl` in `kv.put()` is relative (seconds from now); `expiration` is an
  absolute Unix timestamp in seconds. Mixing them up silently sets keys with wildly
  incorrect lifetimes.
- Analytics Engine `writeDataPoint` inside a Workers request handler runs synchronously
  — it does not block, but if the namespace binding is missing from `wrangler.toml` the
  call throws at runtime rather than at deploy time.

## Verification

```bash
# Miss outcomes in the last hour by namespace
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"SELECT blob1 AS namespace, blob3 AS outcome, COUNT() AS n FROM kv_read_events WHERE timestamp > NOW() - INTERVAL 1 HOUR GROUP BY namespace, outcome ORDER BY namespace, n DESC"}' \
  | jq '.data'

# Average value age on hit (how stale are served values?)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"SELECT blob1 AS namespace, AVG(double2) AS avg_age_s, MAX(double2) AS max_age_s FROM kv_read_events WHERE blob3 = '\''hit'\'' AND timestamp > NOW() - INTERVAL 24 HOUR GROUP BY namespace ORDER BY avg_age_s DESC"}' \
  | jq '.data'
```

## Related

- `kv-cache-hit-rate-analytics-engine-monitoring.md`
- `kv-operation-rate-analytics-engine.md`
- `kv-stale-read-ratio-slo-analytics-engine.md`
- `workers-kv-latency-consistency-monitoring.md`
- `cache-hit-rate-monitoring.md`

## Sources

- https://developers.cloudflare.com/kv/api/read-key-value-pairs/#metadata
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- https://developers.cloudflare.com/analytics/analytics-engine/
