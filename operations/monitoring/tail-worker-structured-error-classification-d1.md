# Tail Worker Structured Error Classification with D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Uncaught exceptions in Cloudflare Workers arrive as raw `Error` objects in a Tail
Worker's `TraceItem` array. Without classification you cannot tell a transient network
hiccup from a schema violation or a D1 constraint breach. Alert noise grows and
root-cause analysis takes hours.

This article shows how to classify every exception by error family (D1, fetch,
validation, internal) in the Tail Worker, write structured rows to D1, and query
error-rate trends per family from Analytics Engine — all without touching the main
Worker bundle.

---

## Context

A Tail Worker receives an array of `TraceItem` objects for each production invocation.
Each item carries `exceptions[]`, `logs[]`, `outcome`, `scriptName`, and request
metadata. The Tail Worker runs in a separate isolate after the main invocation
completes, so it cannot affect response latency.

example project uses a single shared Tail Worker (`example project-tail`) bound to all production Workers.
Classification rules live in a versioned config row in a D1 table
(`tail_classifier_config`) so rules can be updated without redeployment.

---

## Error Classification Schema

```typescript
// schema: D1 migration 0012_tail_error_classes.sql
//
// CREATE TABLE IF NOT EXISTS tail_error_events (
//   id          TEXT PRIMARY KEY,
//   ts          INTEGER NOT NULL,          -- Unix ms
//   script_name TEXT NOT NULL,
//   error_class TEXT NOT NULL,             -- d1 | fetch | validation | internal | unknown
//   error_code  TEXT,                      -- e.g. D1_ERROR, CONSTRAINT_FAILED
//   message     TEXT,
//   stack_hash  TEXT,                      -- first 8 chars of SHA-1 of stack
//   ray_id      TEXT,
//   duration_ms INTEGER
// );
// CREATE INDEX idx_tail_error_ts ON tail_error_events(ts);
// CREATE INDEX idx_tail_error_class ON tail_error_events(error_class, ts);
```

---

## Classification Logic

```typescript
// src/tail-classifier.ts
export type ErrorClass =
  | 'd1'
  | 'fetch'
  | 'validation'
  | 'auth'
  | 'internal'
  | 'unknown';

interface ClassifiedError {
  errorClass: ErrorClass;
  errorCode: string | null;
  message: string;
  stackHash: string;
}

const D1_PATTERNS = [
  /D1_ERROR/i,
  /SQLITE_CONSTRAINT/i,
  /no such table/i,
  /UNIQUE constraint failed/i,
  /database disk image is malformed/i,
];

const FETCH_PATTERNS = [
  /fetch failed/i,
  /network error/i,
  /ERR_NAME_NOT_RESOLVED/i,
  /socket hang up/i,
];

const VALIDATION_PATTERNS = [
  /ZodError/i,
  /validation failed/i,
  /invalid input/i,
  /schema mismatch/i,
];

const AUTH_PATTERNS = [
  /unauthorized/i,
  /forbidden/i,
  /JWT/i,
  /token expired/i,
];

async function sha1Short(text: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-1',
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 8);
}

export async function classifyException(
  ex: TraceException,
): Promise<ClassifiedError> {
  const msg = ex.message ?? '';
  const stack = ex.name + ': ' + msg;

  let errorClass: ErrorClass = 'unknown';
  if (D1_PATTERNS.some((p) => p.test(msg))) errorClass = 'd1';
  else if (FETCH_PATTERNS.some((p) => p.test(msg))) errorClass = 'fetch';
  else if (VALIDATION_PATTERNS.some((p) => p.test(msg))) errorClass = 'validation';
  else if (AUTH_PATTERNS.some((p) => p.test(msg))) errorClass = 'auth';
  else if (ex.name === 'InternalError' || msg.includes('internal')) errorClass = 'internal';

  // Extract structured code if present, e.g. "D1_ERROR: SQLITE_CONSTRAINT_UNIQUE"
  const codeMatch = msg.match(/([A-Z0-9_]{3,40})(?=:|\s|$)/);
  const errorCode = codeMatch ? codeMatch[1] : null;

  return {
    errorClass,
    errorCode,
    message: msg.slice(0, 512),
    stackHash: await sha1Short(stack),
  };
}
```

---

## Tail Worker Handler

```typescript
// src/tail-worker.ts
import { classifyException } from './tail-classifier';

interface Env {
  DB: D1Database;
  AE: AnalyticsEngineDataset;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const rows: Record<string, unknown>[] = [];

    for (const event of events) {
      if (!event.exceptions || event.exceptions.length === 0) continue;

      for (const ex of event.exceptions) {
        const classified = await classifyException(ex);
        const id = crypto.randomUUID();
        const tsMs = event.eventTimestamp ?? Date.now();

        rows.push({
          id,
          ts: tsMs,
          script_name: event.scriptName ?? 'unknown',
          error_class: classified.errorClass,
          error_code: classified.errorCode,
          message: classified.message,
          stack_hash: classified.stackHash,
          ray_id: (event.event as RequestEvent)?.request?.headers?.['cf-ray'] ?? null,
          duration_ms: event.wallTimeMs ?? null,
        });

        // Write to Analytics Engine for real-time dashboards
        env.AE.writeDataPoint({
          blobs: [
            event.scriptName ?? 'unknown',
            classified.errorClass,
            classified.errorCode ?? '',
            classified.stackHash,
          ],
          doubles: [1, event.wallTimeMs ?? 0],
          indexes: [classified.errorClass],
        });
      }
    }

    if (rows.length === 0) return;

    // Batch-insert into D1 (max 100 rows per batch)
    const BATCH_SIZE = 100;
    for (let i = 0; i < rows.length; i += BATCH_SIZE) {
      const batch = rows.slice(i, i + BATCH_SIZE);
      const placeholders = batch
        .map(() => '(?,?,?,?,?,?,?,?,?)')
        .join(',');
      const values = batch.flatMap((r) => [
        r.id, r.ts, r.script_name, r.error_class,
        r.error_code, r.message, r.stack_hash, r.ray_id, r.duration_ms,
      ]);
      await env.DB.prepare(
        `INSERT OR IGNORE INTO tail_error_events
         (id,ts,script_name,error_class,error_code,message,stack_hash,ray_id,duration_ms)
         VALUES ${placeholders}`,
      ).bind(...values).run();
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## D1 Trend Queries

```sql
-- Error rate by class over last 24 h (5-minute buckets)
SELECT
  (ts / 300000) * 300000  AS bucket_ms,
  error_class,
  COUNT(*)                AS count
FROM tail_error_events
WHERE ts > (unixepoch('now') * 1000) - 86400000
GROUP BY bucket_ms, error_class
ORDER BY bucket_ms DESC;

-- Top recurring stack signatures per class
SELECT
  error_class,
  stack_hash,
  MIN(message)            AS sample_message,
  COUNT(*)                AS occurrences,
  MAX(ts)                 AS last_seen_ms
FROM tail_error_events
WHERE ts > (unixepoch('now') * 1000) - 3600000
GROUP BY error_class, stack_hash
ORDER BY occurrences DESC
LIMIT 20;

-- D1-class errors per script in last hour
SELECT
  script_name,
  COUNT(*)                AS d1_errors
FROM tail_error_events
WHERE error_class = 'd1'
  AND ts > (unixepoch('now') * 1000) - 3600000
GROUP BY script_name
ORDER BY d1_errors DESC;
```

---

## Analytics Engine Query (real-time)

```sql
-- Classification mix over last 15 minutes
SELECT
  blob2                              AS error_class,
  SUM(_sample_interval * double1)    AS error_count
FROM example project_TAIL_ERRORS
WHERE timestamp > NOW() - INTERVAL '15' MINUTE
GROUP BY error_class
ORDER BY error_count DESC;
```

---

## Anti-patterns

- **Classify in the main Worker** — costs CPU time on the hot path; use a Tail Worker.
- **Regex on full stack traces** — stacks include file paths that defeat simple patterns;
  match against `ex.message` only.
- **Unbounded D1 growth** — add a cron to `DELETE FROM tail_error_events WHERE ts < ?`
  keeping only the last 30 days.
- **One Analytics Engine blobs[] index for every error** — high cardinality on `stack_hash`
  exhausts the row budget; index on `error_class` (low cardinality) instead.

---

## Gotchas

- `event.wallTimeMs` is `undefined` on Durable Object errors; always guard with `?? null`.
- Tail Workers have a **10 ms CPU time** budget; keep classification synchronous and
  avoid network calls inside the classifier.
- `TraceItem.exceptions` can be an empty array even when `outcome === 'exception'`
  if the Worker threw a non-Error value.
- D1 batch inserts must stay under **1 MB** per statement. Truncate `message` to 512
  chars to keep rows small.

---

## Verification

```bash
# Confirm rows are arriving
npx wrangler d1 execute example project-db --remote \
  --command "SELECT error_class, COUNT(*) AS n FROM tail_error_events \
             WHERE ts > (unixepoch('now')*1000)-3600000 GROUP BY error_class;"

# Tail live to watch classification in real time
npx wrangler tail example project-tail --format json | \
  jq '.logs[] | select(.level=="log") | .message'
```

---

## Related

- `tail-worker-exception-deduplication-fingerprinting-d1.md`
- `tail-worker-structured-log-sampling-strategies.md`
- `d1-query-latency-histogram-analytics-engine.md`
- `workers-tail-real-time-log-streaming.md`
- `cloudflare-analytics-engine-custom-metrics.md`

---

## Sources

- Cloudflare Tail Workers docs: https://developers.cloudflare.com/workers/observability/tail-workers/
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Analytics Engine writeDataPoint: https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- TraceItem type reference: https://github.com/cloudflare/workers-types
