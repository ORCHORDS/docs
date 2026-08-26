# Tail Worker Exception Deduplication with Fingerprinting and D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A high-traffic Worker throws the same `TypeError: Failed to fetch` on thousands of requests per minute. Each occurrence floods PagerDuty with duplicate alerts and fills the Logpush destination with redundant payloads. You need a Tail Worker that groups identical exceptions into a single canonical record, emitting one alert per unique error fingerprint rather than one per invocation.

## Context

Tail Workers receive a `TailEvent` for every observed Worker invocation. When the same logical bug fires at scale, naive forwarding produces O(RPS) duplicate events. The deduplication strategy: hash a fingerprint from `{errorName, normalizedMessage, topFrameLocation}` and write it to a D1 table with a `last_seen` timestamp and an `occurrence_count`. If the fingerprint already exists and was last seen within a suppression window (e.g. 60 seconds), skip the downstream alert; otherwise upsert the count and notify. This keeps alert volume constant regardless of traffic spikes while preserving all occurrence metadata for post-incident analysis.

D1 provides the shared mutable state needed across Tail Worker invocations. Because Tail Workers run in a separate isolate, in-memory deduplication within a single instance is insufficient at scale — D1's global replication ensures the fingerprint store is coherent across all Cloudflare edge PoPs where the Tail Worker executes.

## Exception Fingerprinting

```typescript
// src/fingerprint.ts

export interface ExceptionFingerprint {
  hash: string;
  errorName: string;
  normalizedMessage: string;
  topFrame: string;
}

/**
 * Strip dynamic tokens (UUIDs, IDs, numbers) from an error message so that
 * "Row 42 not found" and "Row 99 not found" map to the same fingerprint.
 */
function normalizeMessage(raw: string): string {
  return raw
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, '<uuid>')
    .replace(/\b\d{4,}\b/g, '<id>')
    .replace(/https?:\/\/[^\s]+/g, '<url>')
    .trim()
    .slice(0, 256);
}

export async function fingerprint(
  ex: { name: string; message: string; stack?: string }
): Promise<ExceptionFingerprint> {
  const normalizedMessage = normalizeMessage(ex.message);

  // Extract the first meaningful frame (skip anonymous/internal frames)
  const topFrame = (ex.stack ?? '')
    .split('\n')
    .map(l => l.trim())
    .find(l => l.startsWith('at ') && !l.includes('<anonymous>') && !l.includes('native'))
    ?? 'unknown';

  const raw = `${ex.name}::${normalizedMessage}::${topFrame}`;
  const encoded = new TextEncoder().encode(raw);
  const hashBuf = await crypto.subtle.digest('SHA-256', encoded);
  const hash = Array.from(new Uint8Array(hashBuf))
    .slice(0, 8)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  return { hash, errorName: ex.name, normalizedMessage, topFrame };
}
```

## D1 Schema and Upsert Logic

```sql
-- migrations/0001_exception_fingerprints.sql
CREATE TABLE IF NOT EXISTS exception_fingerprints (
  hash              TEXT    PRIMARY KEY,
  error_name        TEXT    NOT NULL,
  normalized_msg    TEXT    NOT NULL,
  top_frame         TEXT    NOT NULL,
  first_seen_ms     INTEGER NOT NULL,
  last_seen_ms      INTEGER NOT NULL,
  occurrence_count  INTEGER NOT NULL DEFAULT 1,
  last_alerted_ms   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_efp_last_seen ON exception_fingerprints(last_seen_ms);
```

```typescript
// src/store.ts
export interface FingerprintRow {
  hash: string;
  error_name: string;
  normalized_msg: string;
  top_frame: string;
  first_seen_ms: number;
  last_seen_ms: number;
  occurrence_count: number;
  last_alerted_ms: number;
}

/**
 * Upsert the fingerprint row and return the current row state (post-upsert).
 * D1 does not yet support RETURNING on INSERT OR REPLACE in all versions;
 * use two statements in a batch.
 */
export async function upsertFingerprint(
  db: D1Database,
  hash: string,
  errorName: string,
  normalizedMsg: string,
  topFrame: string,
  nowMs: number
): Promise<FingerprintRow> {
  const [, selectResult] = await db.batch([
    db.prepare(`
      INSERT INTO exception_fingerprints
        (hash, error_name, normalized_msg, top_frame, first_seen_ms, last_seen_ms, occurrence_count, last_alerted_ms)
      VALUES (?, ?, ?, ?, ?, ?, 1, 0)
      ON CONFLICT(hash) DO UPDATE SET
        last_seen_ms      = excluded.last_seen_ms,
        occurrence_count  = occurrence_count + 1
    `).bind(hash, errorName, normalizedMsg, topFrame, nowMs, nowMs),
    db.prepare('SELECT * FROM exception_fingerprints WHERE hash = ?').bind(hash),
  ]);

  return selectResult.results[0] as FingerprintRow;
}

export async function markAlerted(
  db: D1Database,
  hash: string,
  nowMs: number
): Promise<void> {
  await db.prepare(
    'UPDATE exception_fingerprints SET last_alerted_ms = ? WHERE hash = ?'
  ).bind(nowMs, hash).run();
}
```

## Tail Worker Main Handler

```typescript
// src/index.ts
import { fingerprint } from './fingerprint';
import { upsertFingerprint, markAlerted, FingerprintRow } from './store';

export interface Env {
  DB: D1Database;
  ALERT_WEBHOOK: string;    // e.g. PagerDuty Events API v2 URL
  ALERT_ROUTING_KEY: string;
  /** Minimum milliseconds between alerts for the same fingerprint. */
  SUPPRESS_WINDOW_MS: number; // set via wrangler.toml [vars] or secret
}

const DEFAULT_SUPPRESS_MS = 60_000; // 1 minute

export default {
  async tail(events: TailEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    const suppressMs = Number(env.SUPPRESS_WINDOW_MS ?? DEFAULT_SUPPRESS_MS);
    const nowMs = Date.now();

    for (const event of events) {
      for (const ex of event.exceptions) {
        const fp = await fingerprint({ name: ex.name, message: ex.message });
        const row = await upsertFingerprint(
          env.DB, fp.hash, fp.errorName, fp.normalizedMessage, fp.topFrame, nowMs
        );

        const shouldAlert = (nowMs - row.last_alerted_ms) >= suppressMs;
        if (!shouldAlert) continue;

        ctx.waitUntil(
          sendAlert(env, fp, row, event, nowMs)
            .then(() => markAlerted(env.DB, fp.hash, nowMs))
        );
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function sendAlert(
  env: Env,
  fp: { hash: string; errorName: string; normalizedMessage: string; topFrame: string },
  row: FingerprintRow,
  event: TailEvent,
  nowMs: number
): Promise<void> {
  const body = {
    routing_key: env.ALERT_ROUTING_KEY,
    event_action: 'trigger',
    dedup_key: fp.hash,  // PagerDuty native dedup on the same fingerprint
    payload: {
      summary: `[${fp.errorName}] ${fp.normalizedMessage}`,
      severity: 'error',
      source: event.scriptName ?? 'unknown-worker',
      timestamp: new Date(nowMs).toISOString(),
      custom_details: {
        fingerprint_hash: fp.hash,
        top_frame: fp.topFrame,
        occurrence_count: row.occurrence_count,
        first_seen: new Date(row.first_seen_ms).toISOString(),
        worker_outcome: event.outcome,
      },
    },
  };

  const res = await fetch(env.ALERT_WEBHOOK, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    console.error('Alert webhook failed', res.status, await res.text());
  }
}
```

## wrangler.toml

```toml
name = "exception-dedup-tail"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[tail_consumers]]
service = "my-api-worker"

[[d1_databases]]
binding = "DB"
database_name = "exception-fingerprints"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
SUPPRESS_WINDOW_MS = "60000"
```

## Anti-patterns

- **In-memory dedup only**: A single Tail Worker instance sees a fraction of invocations. Suppress state stored in memory vanishes on isolate eviction and is invisible to the other instances handling the remaining traffic.
- **Hashing the raw message**: Dynamic tokens (`Row 42 not found` vs `Row 99 not found`) produce distinct hashes for logically identical errors. Always normalize before hashing.
- **Alert per occurrence without `dedup_key`**: Even with D1 dedup, PagerDuty will open a new incident for each webhook POST if you omit the `dedup_key` field. Use the fingerprint hash as the `dedup_key` so PagerDuty collapses repeated alerts into one open incident.
- **Blocking the Tail Worker on D1 writes**: Use `ctx.waitUntil()` for the alert dispatch so the Tail Worker response returns promptly. The D1 upsert itself must be awaited before deciding to alert, but the outbound webhook should not hold up other event processing.

## Gotchas

- **D1 batch size limit**: D1 batches accept up to 100 statements. If one Tail Worker invocation carries exceptions from many events (the `events` array can contain up to 50 tail events per invocation), ensure your batch loop does not exceed this limit.
- **Fingerprint hash collisions**: An 8-byte (16 hex char) SHA-256 prefix gives ~1.8 × 10¹⁹ unique values. Birthday collision probability is negligible for typical error counts, but if you need stronger guarantees use the full 32-byte hash as the primary key at the cost of a wider index.
- **D1 replication lag**: D1 uses primary-plus-read-replica topology. A read immediately after a write may hit a replica that has not yet received the upsert, causing two Tail Worker instances to both decide `shouldAlert = true` within the suppress window. Tolerate occasional duplicate alerts — they are far fewer than the unbounded duplicates you had before.
- **Tail Worker CPU limit**: Tail Workers share the same 50 ms CPU budget as regular Workers (as of 2025). The SHA-256 digest via `crypto.subtle` is fast (~0.1 ms for short strings) but avoid processing stacks longer than ~10 KB per exception.

## Verification

```bash
# Apply migration
wrangler d1 execute exception-fingerprints --file migrations/0001_exception_fingerprints.sql

# Trigger a test exception in the observed Worker, then query D1
wrangler d1 execute exception-fingerprints \
  --command "SELECT hash, error_name, occurrence_count, last_alerted_ms FROM exception_fingerprints ORDER BY last_seen_ms DESC LIMIT 10"

# Confirm only one PagerDuty alert fired despite multiple occurrences
# by checking occurrence_count > 1 with last_alerted_ms set only once.
```

## Related

- `tail-worker-otel-span-export.md` — exporting spans from Tail Workers to OTLP backends
- `workers-tail-real-time-log-streaming.md` — streaming logs from Tail Workers
- `workers-tail-worker-sampling-high-traffic.md` — sampling strategies for high-RPS Workers
- `cloudflare-notifications-pagerduty-webhook.md` — Cloudflare Notifications to PagerDuty setup

## Sources

- Cloudflare Tail Workers documentation: https://developers.cloudflare.com/workers/observability/tail-workers/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- PagerDuty Events API v2 dedup_key: https://developer.pagerduty.com/docs/events-api-v2/trigger-an-incident/
