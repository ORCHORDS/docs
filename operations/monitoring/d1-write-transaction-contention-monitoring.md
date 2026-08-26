# D1 Write Transaction Contention Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Intermittent 500 errors on write-heavy D1 tables. Logs show `SQLITE_BUSY: database is locked` or D1's translated variant `D1_ERROR: no such table` during WAL checkpointing. Retry logic masks the errors in p50 latency but p99 spikes every few minutes. You need to measure contention rate per table and surface the worst offenders before users notice.

## Context

D1 is built on SQLite with WAL (Write-Ahead Log) mode. Because D1 runs on Cloudflare's distributed edge, writes to the same database from multiple Worker instances can produce lock contention at the WAL writer. D1 serialises writes internally but queues them; under high write concurrency the queue timeout surfaces as `SQLITE_BUSY`. Tail Workers capture every exception outcome including contention errors, letting you count and dimension them in Analytics Engine without any changes to the application database layer — though adding explicit retry instrumentation gives far richer signal.

---

## 1. Instrumenting the D1 Binding with a Retry Wrapper

```typescript
// src/lib/d1-instrumented.ts
import type { D1Database, D1Result } from '@cloudflare/workers-types';

export interface D1Metrics {
  ae: AnalyticsEngineDataset;
}

export async function d1RunWithRetry<T = unknown>(
  db: D1Database,
  stmt: D1PreparedStatement,
  metrics: D1Metrics,
  table: string,
  maxRetries = 3
): Promise<D1Result<T>> {
  let attempt = 0;
  const startMs = Date.now();

  while (true) {
    attempt++;
    try {
      const result = await stmt.run<T>();
      const latencyMs = Date.now() - startMs;

      metrics.ae.writeDataPoint({
        indexes: [table],
        blobs: ['ok', String(attempt)],
        doubles: [latencyMs, attempt - 1, 0], // latency, retries, contention=0
      });

      return result;
    } catch (err: unknown) {
      const msg = (err as Error).message ?? '';
      const isContention =
        msg.includes('SQLITE_BUSY') ||
        msg.includes('database is locked') ||
        msg.includes('D1_BUSY');

      metrics.ae.writeDataPoint({
        indexes: [table],
        blobs: [isContention ? 'contention' : 'error', String(attempt)],
        doubles: [Date.now() - startMs, attempt - 1, 1],
      });

      if (!isContention || attempt >= maxRetries) throw err;

      // Exponential backoff: 50 ms, 100 ms, 200 ms
      await new Promise(r => setTimeout(r, 50 * 2 ** (attempt - 1)));
    }
  }
}
```

---

## 2. Tail Worker — Passive Contention Detection

For code paths where adding the retry wrapper is impractical, the Tail Worker can detect contention from exception messages.

```typescript
// tail/d1-contention-tail.ts
export interface Env {
  AE_DATASET: AnalyticsEngineDataset;
}

interface TailEvent {
  event: { request: { url: string } };
  exceptions: { name: string; message: string }[];
  outcome: string;
  scriptName: string;
}

const CONTENTION_PATTERNS = [
  /SQLITE_BUSY/i,
  /database is locked/i,
  /D1_BUSY/i,
  /WAL checkpoint/i,
];

const TABLE_PATTERN = /(?:INSERT INTO|UPDATE|DELETE FROM|INTO)\s+["'`]?(\w+)/i;

export default {
  async tail(events: TailEvent[], env: Env): Promise<void> {
    for (const ev of events) {
      for (const ex of ev.exceptions) {
        const isContention = CONTENTION_PATTERNS.some(p => p.test(ex.message));
        if (!isContention) continue;

        const tableMatch = TABLE_PATTERN.exec(ex.message);
        const table = tableMatch?.[1] ?? 'unknown';

        env.AE_DATASET.writeDataPoint({
          indexes: [table],
          blobs: [ev.scriptName, 'tail-detected', ex.name],
          doubles: [1, 0, 1], // count=1, retries=0, contention=1
        });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. Analytics Engine SQL Queries

```sql
-- Contention rate per table over the last hour
SELECT
  index1                                       AS table_name,
  SUM(_sample_interval * double3)              AS contention_events,
  SUM(_sample_interval)                        AS total_writes,
  ROUND(
    SUM(_sample_interval * double3) * 100.0 /
    NULLIF(SUM(_sample_interval), 0), 2
  )                                            AS contention_pct
FROM d1_contention
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY table_name
ORDER BY contention_pct DESC;

-- Average retries per table — indicates sustained contention pressure
SELECT
  index1          AS table_name,
  AVG(double2)    AS avg_retries,
  MAX(double2)    AS max_retries,
  COUNT()         AS samples
FROM d1_contention
WHERE timestamp > NOW() - INTERVAL '30' MINUTE
  AND blob1 != 'tail-detected'   -- instrumented path only
GROUP BY table_name
ORDER BY avg_retries DESC;

-- 5-minute contention rate trend (for alert burn rate)
SELECT
  toStartOfFiveMinutes(timestamp)              AS bucket,
  index1                                       AS table_name,
  SUM(_sample_interval * double3) * 1.0 /
    NULLIF(SUM(_sample_interval), 0)           AS contention_rate
FROM d1_contention
WHERE timestamp > NOW() - INTERVAL '2' HOUR
GROUP BY bucket, table_name
ORDER BY bucket DESC, contention_rate DESC;
```

---

## 4. Alert Worker — Contention SLO Breach

```typescript
// alert-worker/d1-contention-alert.ts
// Cron: */5 * * * *  (every 5 minutes)

const CONTENTION_SLO_THRESHOLD = 0.02; // 2% contention rate budget

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT index1 AS tbl,
             SUM(_sample_interval * double3) * 1.0 / NULLIF(SUM(_sample_interval), 0) AS rate
      FROM d1_contention
      WHERE timestamp > NOW() - INTERVAL '5' MINUTE
      GROUP BY tbl
      HAVING rate > ${CONTENTION_SLO_THRESHOLD}
      ORDER BY rate DESC LIMIT 5
    `;

    const res = await cfAeQuery(env, sql);
    if (!res.data.length) return;

    const lines = res.data.map(
      (r: { tbl: string; rate: number }) =>
        `${r.tbl}: ${(r.rate * 100).toFixed(1)}% contention`
    );

    await sendSlackAlert(env.SLACK_WEBHOOK, {
      text: `D1 write contention SLO breach (>${(CONTENTION_SLO_THRESHOLD * 100).toFixed(0)}%):\n${lines.join('\n')}`,
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. WAL Checkpoint Pressure Mitigation Check

```typescript
// src/lib/d1-wal-check.ts
// D1 does not expose PRAGMA wal_checkpoint directly but you can probe
// write latency spikes as a proxy for checkpoint-induced stalls.

export async function measureWriteLatency(
  db: D1Database,
  probeTable: string
): Promise<number> {
  const t0 = performance.now();
  // A no-op UPDATE that touches 0 rows but exercises the write path
  await db.prepare(`UPDATE ${probeTable} SET updated_at = ? WHERE 1 = 0`)
           .bind(Date.now())
           .run();
  return performance.now() - t0;
}
```

---

## Anti-patterns

- **Silently swallowing `SQLITE_BUSY` errors** — retrying without recording the event hides the true contention rate and prevents meaningful alerting.
- **Using transactions for reads** — `BEGIN` acquires a shared lock; unnecessary read transactions amplify write contention. Use D1's `prepare().first()` for reads.
- **Very long-running write transactions** — multiple D1 `batch()` calls in sequence hold the write slot; prefer a single `db.batch([...])` array to minimise lock duration.
- **Ignoring the `attempt` dimension** — tracking only success/failure misses the cost of retries (each retry adds latency and CPU).

## Gotchas

- D1 translates some `SQLITE_BUSY` errors into HTTP 503 responses at the API boundary; Tail Workers see the exception message from the binding, which may differ from raw SQLite error text.
- The `DATABASE IS LOCKED` message only appears when the Worker's own WAL reader is behind the writer; cross-instance contention manifests as a queue timeout with a different message.
- Analytics Engine `double3` values must be pre-computed before writing; you cannot update a data point after the fact.
- D1's internal retry logic (up to 3 attempts) means some contention is already hidden before your code sees it; your observed rate is a lower bound on true contention.

## Verification

```bash
# Simulate contention by firing concurrent writes from wrangler dev
for i in {1..20}; do
  curl -s http://localhost:8787/api/write &
done
wait

# Check AE for contention events (after ~30 s propagation delay)
curl -s "$CF_AE_SQL_URL" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query":"SELECT index1, SUM(double3), COUNT() FROM d1_contention WHERE timestamp > NOW() - INTERVAL '\''5'\'' MINUTE GROUP BY index1"}' \
  | jq '.data'
```

## Related

- `d1-explain-query-plan-slow-query-automation.md`
- `d1-query-latency-histogram-analytics-engine.md`
- `d1-database-size-growth-analytics-engine.md`
- `sli-slo-error-budget-d1-tracking.md`
- `tail-worker-exception-deduplication-fingerprinting-d1.md`

## Sources

- D1 error reference: https://developers.cloudflare.com/d1/observability/debug-d1/
- SQLite WAL mode: https://www.sqlite.org/wal.html
- D1 best practices — batching: https://developers.cloudflare.com/d1/best-practices/use-d1/
- Analytics Engine limits: https://developers.cloudflare.com/analytics/analytics-engine/limits/
