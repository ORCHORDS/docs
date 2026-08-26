# GDPR Right-to-Erasure Pipeline in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SaaS product must honour GDPR Article 17 "right to erasure" requests. Users submit deletion requests via a support form or an API endpoint, and your backend — running on Cloudflare Workers — must cascade deletes across D1 tables, remove R2 objects stored under the user's prefix, invalidate KV keys scoped to that user, write an audit event, and return a confirmation within the 30-day statutory SLA.

## Context

Cloudflare Workers are stateless compute units that orchestrate several durable storage layers:

- **D1** — SQLite-compatible relational database for structured user records.
- **R2** — S3-compatible object storage for user-uploaded files, avatars, exports.
- **KV** — globally-replicated key-value cache keyed by user-scoped namespaces.
- **Queues** — for durable, retryable async work so the HTTP response returns fast.
- **D1 (deletion_jobs table)** — idempotency store; re-submitting the same request is a no-op.

The deletion pipeline must be idempotent (network retries must not double-delete or double-log), auditable (immutable log entry per job), and bounded (30-day SLA from request receipt).

## Solution

```typescript
// worker.ts — GDPR erasure pipeline
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  USER_FILES: R2Bucket;
  USER_CACHE: KVNamespace;
  DELETION_QUEUE: Queue<DeletionMessage>;
  AUDIT_BUCKET: R2Bucket;
}

interface DeletionMessage {
  jobId: string;
  userId: string;
  requestedAt: string;
  requestedBy: 'user' | 'admin' | 'dpa';
}

const app = new Hono<{ Bindings: Env }>();

// ── 1. Intake endpoint ──────────────────────────────────────────────────────
app.post('/gdpr/deletion-request', async (c) => {
  const { userId, requestedBy = 'user' } = await c.req.json<{
    userId: string;
    requestedBy?: 'user' | 'admin' | 'dpa';
  }>();

  if (!userId) return c.json({ error: 'userId required' }, 400);

  const { DB, DELETION_QUEUE } = c.env;

  // Idempotency: check for existing non-failed job
  const existing = await DB.prepare(
    `SELECT job_id, status, requested_at FROM deletion_jobs
     WHERE user_id = ? AND status IN ('pending','processing','completed')
     ORDER BY requested_at DESC LIMIT 1`
  )
    .bind(userId)
    .first<{ job_id: string; status: string; requested_at: string }>();

  if (existing) {
    return c.json({
      jobId: existing.job_id,
      status: existing.status,
      message: 'Deletion request already registered',
      requestedAt: existing.requested_at,
      slaDeadline: slaDeadline(existing.requested_at),
    });
  }

  const jobId = crypto.randomUUID();
  const now = new Date().toISOString();

  await DB.prepare(
    `INSERT INTO deletion_jobs (job_id, user_id, status, requested_by, requested_at)
     VALUES (?, ?, 'pending', ?, ?)`
  )
    .bind(jobId, userId, requestedBy, now)
    .run();

  const msg: DeletionMessage = { jobId, userId, requestedAt: now, requestedBy };
  await DELETION_QUEUE.send(msg);

  return c.json({
    jobId,
    status: 'pending',
    message: 'Erasure request accepted',
    slaDeadline: slaDeadline(now),
  }, 202);
});

// ── 2. Status endpoint ──────────────────────────────────────────────────────
app.get('/gdpr/deletion-request/:jobId', async (c) => {
  const { jobId } = c.req.param();
  const row = await c.env.DB.prepare(
    `SELECT job_id, user_id, status, requested_at, completed_at, error_detail
     FROM deletion_jobs WHERE job_id = ?`
  )
    .bind(jobId)
    .first<{
      job_id: string; user_id: string; status: string;
      requested_at: string; completed_at: string | null; error_detail: string | null;
    }>();

  if (!row) return c.json({ error: 'Job not found' }, 404);

  return c.json({
    jobId: row.job_id,
    userId: row.user_id,
    status: row.status,
    requestedAt: row.requested_at,
    completedAt: row.completed_at,
    slaDeadline: slaDeadline(row.requested_at),
    errorDetail: row.error_detail,
  });
});

// ── 3. Queue consumer ───────────────────────────────────────────────────────
export default {
  fetch: app.fetch,

  async queue(batch: MessageBatch<DeletionMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const { jobId, userId } = message.body;
      try {
        await processErasure(env, jobId, userId);
        message.ack();
      } catch (err) {
        console.error(`[erasure] job=${jobId} error=${String(err)}`);
        // Retry up to queue's maxRetries; after that mark failed
        if (message.attempts >= 3) {
          await markJob(env.DB, jobId, 'failed', String(err));
          message.ack(); // ack to stop retries; error is persisted
        } else {
          message.retry();
        }
      }
    }
  },
};

// ── 4. Core erasure logic ───────────────────────────────────────────────────
async function processErasure(env: Env, jobId: string, userId: string): Promise<void> {
  await markJob(env.DB, jobId, 'processing', null);

  // 4a. Cascade D1 deletes (order matters for FK constraints)
  const tables = [
    'user_sessions',
    'user_preferences',
    'user_subscriptions',
    'user_payments',
    'user_profiles',
    'users',
  ];
  for (const table of tables) {
    await env.DB.prepare(`DELETE FROM ${table} WHERE user_id = ?`)
      .bind(userId)
      .run();
  }

  // 4b. Remove R2 objects under user prefix
  await deleteR2Prefix(env.USER_FILES, `users/${userId}/`);

  // 4c. Invalidate KV keys in user namespace
  await deleteKVPrefix(env.USER_CACHE, `user:${userId}:`);

  // 4d. Write immutable audit event
  await writeAuditLog(env.AUDIT_BUCKET, {
    eventType: 'gdpr.erasure.completed',
    jobId,
    userId,
    completedAt: new Date().toISOString(),
    tablesCleared: tables,
  });

  await markJob(env.DB, jobId, 'completed', null);
}

async function deleteR2Prefix(bucket: R2Bucket, prefix: string): Promise<void> {
  let cursor: string | undefined;
  do {
    const listed = await bucket.list({ prefix, cursor, limit: 1000 });
    const keys = listed.objects.map((o) => o.key);
    if (keys.length > 0) {
      await bucket.delete(keys);
    }
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);
}

async function deleteKVPrefix(ns: KVNamespace, prefix: string): Promise<void> {
  let cursor: string | undefined;
  do {
    const listed = await ns.list({ prefix, cursor, limit: 1000 });
    await Promise.all(listed.keys.map((k) => ns.delete(k.name)));
    cursor = listed.list_complete ? undefined : listed.cursor;
  } while (cursor);
}

async function writeAuditLog(bucket: R2Bucket, event: Record<string, unknown>): Promise<void> {
  const key = `audit/${new Date().toISOString().replace(/[:.]/g, '-')}-${crypto.randomUUID()}.json`;
  const body = JSON.stringify(event, null, 2);
  const checksum = await sha256Hex(body);
  await bucket.put(key, body, {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: { 'x-sha256': checksum },
  });
}

async function markJob(
  db: D1Database,
  jobId: string,
  status: string,
  errorDetail: string | null
): Promise<void> {
  await db.prepare(
    `UPDATE deletion_jobs
     SET status = ?, completed_at = CASE WHEN ? IN ('completed','failed') THEN datetime('now') ELSE NULL END,
         error_detail = ?
     WHERE job_id = ?`
  )
    .bind(status, status, errorDetail, jobId)
    .run();
}

function slaDeadline(requestedAt: string): string {
  const d = new Date(requestedAt);
  d.setDate(d.getDate() + 30);
  return d.toISOString();
}

async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

## Implementation Details

**D1 schema — run once during migration:**

```sql
CREATE TABLE IF NOT EXISTS deletion_jobs (
  job_id       TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|completed|failed
  requested_by TEXT NOT NULL DEFAULT 'user',
  requested_at TEXT NOT NULL,
  completed_at TEXT,
  error_detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_deletion_jobs_user ON deletion_jobs (user_id, status);
```

**wrangler.toml bindings:**

```toml
[[queues.consumers]]
queue = "gdpr-deletion-queue"
max_batch_size = 10
max_retries = 3
max_batch_timeout = 30

[[r2_buckets]]
binding = "AUDIT_BUCKET"
bucket_name = "compliance-audit-logs"
```

**Ordering of D1 deletes** is critical. If foreign-key enforcement is enabled (`PRAGMA foreign_keys = ON`), child tables must be deleted before parent tables. Map your FK graph before constructing `tables`.

**KV list pagination** uses the `cursor` from `list_complete === false`. Always drain the full cursor chain or you will leave orphaned keys.

**R2 batch delete** accepts up to 1 000 keys per call. The loop above pages through arbitrarily large prefixes safely.

## Anti-patterns

- **Deleting synchronously in the HTTP handler.** A slow R2 prefix scan will exceed the 30-second CPU limit and leave the job half-done with no retry mechanism.
- **Not checking idempotency.** Re-submissions from impatient users or DPAs will create duplicate audit entries and may race on D1 deletes.
- **Deleting child rows after parent rows** when FK constraints are active — this causes constraint violations that silently roll back only the current statement in D1.
- **Using `ns.list()` without draining the cursor** — KV `list()` returns at most 1 000 keys; users with many cached keys will have residual data.
- **Writing the audit log before confirming D1/R2 deletes succeed** — the log becomes misleading if the deletion later fails.

## Gotchas

- `R2Bucket.delete()` accepts an array of keys but the method signature also accepts a single string. Always pass an array for batch operations.
- D1's `database.batch()` can run multiple statements in one round-trip but they share a transaction only when wrapped in `BEGIN`/`COMMIT`. For FK-ordered deletes use sequential `.run()` calls or an explicit transaction batch.
- KV `list()` does not guarantee order. Do not assume keys are returned alphabetically.
- The `message.attempts` property on a Queue message is 1-indexed (first delivery = 1).
- R2 Object Lock (immutability) must be enabled at bucket creation time and cannot be toggled after the fact. Use a separate `AUDIT_BUCKET` with Object Lock, not the same bucket as `USER_FILES`.

## Verification

```bash
# 1. Submit a test erasure request
curl -X POST https://your-worker.example.com/gdpr/deletion-request \
  -H 'Content-Type: application/json' \
  -d '{"userId": "usr_test_001", "requestedBy": "admin"}'
# → {"jobId": "...", "status": "pending", ...}

# 2. Poll the status endpoint until completed
curl https://your-worker.example.com/gdpr/deletion-request/<jobId>

# 3. Confirm D1 rows gone
wrangler d1 execute <DB_NAME> --command \
  "SELECT COUNT(*) FROM users WHERE user_id = 'usr_test_001'"
# → 0

# 4. Confirm R2 objects gone
wrangler r2 object list <BUCKET> --prefix users/usr_test_001/
# → (empty)

# 5. Check audit log written
wrangler r2 object list compliance-audit-logs --prefix audit/
# → at least one .json entry
```

## Related

- `documentation/categories/compliance/workers-audit-log-immutable-r2.md`
- `documentation/categories/compliance/workers-pii-detection-scrubber.md`
- Cloudflare Queues — consumer configuration
- D1 — foreign key constraints

## Sources

- GDPR Article 17 — Right to erasure ('right to be forgotten'): https://gdpr-info.eu/art-17-gdpr/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Cloudflare R2 — Object delete: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare KV — list keys: https://developers.cloudflare.com/kv/api/list-keys/
