# Immutable Audit Log Storage in R2 with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your compliance team requires a tamper-proof audit trail of all privileged actions (logins, data exports, permission changes, billing events). The log must be:

1. **Append-only** — existing entries cannot be modified or deleted.
2. **Queryable** — security teams can search by time range, user, or event type without reading every object.
3. **Verifiable** — each entry carries a SHA-256 checksum so downstream systems can confirm the log has not been altered.
4. **Non-blocking** — writing a log entry must not add latency to the originating request.

## Context

R2 is Cloudflare's S3-compatible object storage with zero egress fees. Combined with **R2 Object Lock** (WORM — Write Once Read Many), you can create buckets where objects cannot be overwritten or deleted for a configurable retention period.

Cloudflare **Queues** provide a durable, at-least-once delivery channel. By publishing audit events to a Queue rather than writing them synchronously inside the request handler, you decouple latency-sensitive request paths from the slower R2 write.

A lightweight **D1** index table stores event metadata (timestamp, type, userId, objectKey) so queries can locate specific objects without listing the entire bucket.

## Solution

```typescript
// audit-log.ts
import { Hono } from 'hono';

export interface Env {
  AUDIT_BUCKET: R2Bucket;      // Object Lock enabled, 7-year retention
  AUDIT_INDEX: D1Database;     // metadata index for fast queries
  AUDIT_QUEUE: Queue<AuditEvent>;
}

export interface AuditEvent {
  eventId: string;
  eventType: string;           // e.g. 'user.login', 'data.export', 'acl.change'
  userId: string;
  actorIp: string;
  resource: string;            // affected resource identifier
  outcome: 'success' | 'failure';
  metadata: Record<string, unknown>;
  occurredAt: string;          // ISO-8601
}

// ── Public helper: emit an audit event (non-blocking) ───────────────────────
export async function emitAuditEvent(
  queue: Queue<AuditEvent>,
  partial: Omit<AuditEvent, 'eventId' | 'occurredAt'>
): Promise<string> {
  const event: AuditEvent = {
    ...partial,
    eventId: crypto.randomUUID(),
    occurredAt: new Date().toISOString(),
  };
  await queue.send(event);
  return event.eventId;
}

// ── Queue consumer: persists to R2 + D1 ────────────────────────────────────
export const auditConsumer = {
  async queue(batch: MessageBatch<AuditEvent>, env: Env): Promise<void> {
    const writes: Promise<void>[] = [];
    for (const msg of batch.messages) {
      writes.push(persistAuditEvent(env, msg.body).then(() => msg.ack()).catch((err) => {
        console.error('[audit] persist failed', msg.body.eventId, err);
        msg.retry();
      }));
    }
    await Promise.allSettled(writes);
  },
};

async function persistAuditEvent(env: Env, event: AuditEvent): Promise<void> {
  const body = JSON.stringify(event, null, 2);
  const checksum = await sha256Hex(body);

  // Key format: YYYY/MM/DD/HH/<eventType>/<eventId>.json
  // — allows date-range listing without scanning the whole bucket
  const d = new Date(event.occurredAt);
  const key = [
    String(d.getUTCFullYear()),
    pad(d.getUTCMonth() + 1),
    pad(d.getUTCDate()),
    pad(d.getUTCHours()),
    event.eventType.replace(/[^a-z0-9._-]/gi, '_'),
    `${event.eventId}.json`,
  ].join('/');

  // Write to R2 with checksum in metadata
  await env.AUDIT_BUCKET.put(key, body, {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: {
      'x-event-id': event.eventId,
      'x-event-type': event.eventType,
      'x-user-id': event.userId,
      'x-sha256': checksum,
    },
  });

  // Index in D1 for queryable metadata
  await env.AUDIT_INDEX.prepare(
    `INSERT OR IGNORE INTO audit_index
       (event_id, event_type, user_id, outcome, occurred_at, r2_key, sha256)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      event.eventId,
      event.eventType,
      event.userId,
      event.outcome,
      event.occurredAt,
      key,
      checksum
    )
    .run();
}

// ── Query API ───────────────────────────────────────────────────────────────
const app = new Hono<{ Bindings: Env }>();

app.get('/audit/events', async (c) => {
  const {
    userId,
    eventType,
    from = new Date(Date.now() - 86_400_000).toISOString(),
    to = new Date().toISOString(),
    limit = '50',
    cursor,
  } = c.req.query();

  const conditions: string[] = ['occurred_at >= ? AND occurred_at <= ?'];
  const bindings: unknown[] = [from, to];

  if (userId) { conditions.push('user_id = ?'); bindings.push(userId); }
  if (eventType) { conditions.push('event_type = ?'); bindings.push(eventType); }
  if (cursor) { conditions.push('event_id > ?'); bindings.push(cursor); }

  const rows = await c.env.AUDIT_INDEX.prepare(
    `SELECT event_id, event_type, user_id, outcome, occurred_at, r2_key, sha256
     FROM audit_index
     WHERE ${conditions.join(' AND ')}
     ORDER BY occurred_at ASC
     LIMIT ?`
  )
    .bind(...bindings, Number(limit))
    .all<{
      event_id: string; event_type: string; user_id: string;
      outcome: string; occurred_at: string; r2_key: string; sha256: string;
    }>();

  return c.json({
    events: rows.results,
    nextCursor: rows.results.length === Number(limit)
      ? rows.results.at(-1)?.event_id
      : null,
  });
});

// Retrieve + verify a single event
app.get('/audit/events/:eventId', async (c) => {
  const { eventId } = c.req.param();
  const row = await c.env.AUDIT_INDEX.prepare(
    'SELECT r2_key, sha256 FROM audit_index WHERE event_id = ?'
  )
    .bind(eventId)
    .first<{ r2_key: string; sha256: string }>();

  if (!row) return c.json({ error: 'Event not found' }, 404);

  const obj = await c.env.AUDIT_BUCKET.get(row.r2_key);
  if (!obj) return c.json({ error: 'R2 object missing — storage inconsistency' }, 500);

  const body = await obj.text();
  const computedChecksum = await sha256Hex(body);

  return c.json({
    event: JSON.parse(body),
    integrity: {
      storedChecksum: row.sha256,
      computedChecksum,
      valid: computedChecksum === row.sha256,
    },
  });
});

export default { fetch: app.fetch, ...auditConsumer };

// ── Helpers ─────────────────────────────────────────────────────────────────
async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}
```

## Implementation Details

**D1 schema:**

```sql
CREATE TABLE IF NOT EXISTS audit_index (
  event_id    TEXT PRIMARY KEY,
  event_type  TEXT NOT NULL,
  user_id     TEXT NOT NULL,
  outcome     TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  r2_key      TEXT NOT NULL,
  sha256      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_user_time  ON audit_index (user_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_type_time  ON audit_index (event_type, occurred_at);
```

**Enabling Object Lock on the audit bucket (via Wrangler or dashboard):**

Object Lock must be set at bucket creation time. It cannot be enabled retroactively.

```bash
# Create bucket with Object Lock
wrangler r2 bucket create compliance-audit-logs --object-lock-mode=COMPLIANCE --object-lock-days=2555
# 2555 days ≈ 7 years (common financial/compliance retention period)
```

With COMPLIANCE mode, even the account root cannot delete locked objects before the retention period expires.

**wrangler.toml excerpt:**

```toml
[[r2_buckets]]
binding = "AUDIT_BUCKET"
bucket_name = "compliance-audit-logs"

[[queues.producers]]
binding = "AUDIT_QUEUE"
queue = "audit-event-queue"

[[queues.consumers]]
queue = "audit-event-queue"
max_batch_size = 25
max_retries = 5
max_batch_timeout = 10
```

**Using `emitAuditEvent` in another handler:**

```typescript
import { emitAuditEvent } from './audit-log';

app.post('/admin/export-user-data', async (c) => {
  const { userId } = await c.req.json();
  // ... perform export ...
  await emitAuditEvent(c.env.AUDIT_QUEUE, {
    eventType: 'data.export',
    userId,
    actorIp: c.req.header('cf-connecting-ip') ?? 'unknown',
    resource: `user:${userId}`,
    outcome: 'success',
    metadata: { exportedAt: new Date().toISOString() },
  });
  return c.json({ ok: true });
});
```

## Anti-patterns

- **Writing audit events synchronously in the request path.** R2 puts can take 50–200 ms. Inline writes add latency and block the handler if storage is momentarily slow.
- **Using KV for the audit log.** KV values can be overwritten; it is not append-only and does not support Object Lock.
- **Flat R2 key structure** (e.g., `audit/<eventId>.json`). With millions of events, `bucket.list()` without a prefix becomes expensive. The hierarchical date-based key scheme enables targeted listing.
- **Storing event bodies only in D1.** D1 has a 10 GB size limit per database and is not designed for blob storage. Keep bodies in R2 and metadata in D1.
- **Skipping the checksum** — without it, you cannot prove during a compliance audit that the stored log matches what was originally written.

## Gotchas

- R2 Object Lock in COMPLIANCE mode blocks even `wrangler r2 object delete`. Plan for this in runbooks.
- D1's `INSERT OR IGNORE` is necessary because Queue at-least-once delivery may replay a message after a partial failure. Without it, a replay causes a UNIQUE constraint error.
- `crypto.subtle.digest` returns an `ArrayBuffer`, not a string. Cast via `new Uint8Array(buf)` before converting to hex.
- The Queue consumer's `batch.messages` array is limited to `max_batch_size`. Do not assume all events in a heavy spike arrive in a single batch.
- D1 has no `RETURNING` clause in `INSERT OR IGNORE` when the row already exists. Use a separate `SELECT` to confirm if needed.

## Verification

```bash
# 1. Emit a test event (trigger via your app or directly via queue)
curl -X POST https://your-worker.example.com/admin/export-user-data \
  -H 'Content-Type: application/json' \
  -d '{"userId": "usr_test_001"}'

# 2. Query the index
curl 'https://your-worker.example.com/audit/events?userId=usr_test_001'

# 3. Retrieve + verify integrity
curl 'https://your-worker.example.com/audit/events/<eventId>'
# Look for: {"integrity":{"valid":true}}

# 4. Confirm object is in R2
wrangler r2 object list compliance-audit-logs --prefix 2026/

# 5. Attempt to delete (should fail with COMPLIANCE lock)
wrangler r2 object delete compliance-audit-logs <key>
# → Error: object is locked
```

## Related

- `documentation/categories/compliance/workers-gdpr-data-deletion-pipeline.md`
- `documentation/categories/compliance/workers-data-residency-routing.md`
- Cloudflare R2 Object Lock documentation
- Cloudflare Queues — consumer batching

## Sources

- Cloudflare R2 Object Lock: https://developers.cloudflare.com/r2/buckets/object-lock/
- Cloudflare Queues overview: https://developers.cloudflare.com/queues/
- D1 — database: https://developers.cloudflare.com/d1/
- Web Crypto API — SubtleCrypto.digest(): https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
