# HIPAA-Compliant Audit Logging in Cloudflare Workers with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a healthcare Worker that accesses Protected Health Information (PHI) and must maintain a tamper-evident audit log for six years as required by HIPAA. Every PHI read or write must be captured in a D1 `access_logs` table via middleware, and older records must be automatically archived to R2 before being pruned.

---

## Context

HIPAA's Security Rule (45 CFR §164.312(b)) mandates audit controls that record and examine activity in information systems containing PHI. D1 provides a serverless SQL store suitable for append-only audit logs when UPDATE and DELETE are prohibited by application policy. A Cloudflare Cron Trigger can enforce the 6-year retention window by copying aged rows to R2 Parquet-compatible JSON archives before deletion. The immutability guarantee is enforced at the application layer since D1 does not yet offer row-level write locks.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS access_logs (
  id            TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  actor_id      TEXT    NOT NULL,          -- user or service account making the request
  resource_type TEXT    NOT NULL,          -- e.g. 'patient_record', 'lab_result'
  resource_id   TEXT    NOT NULL,          -- primary key of the accessed resource
  action        TEXT    NOT NULL,          -- 'READ' | 'CREATE' | 'UPDATE' | 'DELETE' | 'EXPORT'
  phi_accessed  INTEGER NOT NULL DEFAULT 0, -- 1 if record contained PHI, else 0
  ip            TEXT,
  user_agent    TEXT,
  ts            INTEGER NOT NULL           -- Unix epoch ms
);

CREATE INDEX IF NOT EXISTS idx_al_actor    ON access_logs(actor_id, ts);
CREATE INDEX IF NOT EXISTS idx_al_resource ON access_logs(resource_type, resource_id, ts);
CREATE INDEX IF NOT EXISTS idx_al_ts       ON access_logs(ts);

-- Tracks archival jobs
CREATE TABLE IF NOT EXISTS audit_archive_runs (
  id          TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  started_at  INTEGER NOT NULL,
  finished_at INTEGER,
  rows_archived INTEGER DEFAULT 0,
  r2_key      TEXT,
  status      TEXT NOT NULL DEFAULT 'running'
);
```

---

## Section 2 — Worker Implementation

```typescript
import type { ScheduledEvent } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  AUDIT_ARCHIVE: R2Bucket;
}

const SIX_YEARS_MS  = 6 * 365.25 * 24 * 60 * 60 * 1000;
const ARCHIVE_BATCH = 5_000; // rows per archival batch

// ---------------------------------------------------------------------------
// Middleware helper — call from every route that touches PHI
// ---------------------------------------------------------------------------
export async function recordAuditLog(
  env: Env,
  entry: {
    actor_id: string;
    resource_type: string;
    resource_id: string;
    action: 'READ' | 'CREATE' | 'UPDATE' | 'DELETE' | 'EXPORT';
    phi_accessed: boolean;
    ip?: string;
    user_agent?: string;
  }
): Promise<void> {
  await env.DB
    .prepare(
      `INSERT INTO access_logs
         (actor_id, resource_type, resource_id, action, phi_accessed, ip, user_agent, ts)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      entry.actor_id,
      entry.resource_type,
      entry.resource_id,
      entry.action,
      entry.phi_accessed ? 1 : 0,
      entry.ip ?? null,
      entry.user_agent ?? null,
      Date.now()
    )
    .run();
}

// ---------------------------------------------------------------------------
// Example PHI route with audit middleware applied
// ---------------------------------------------------------------------------
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'GET' && url.pathname.startsWith('/v1/patients/')) {
      const patientId = url.pathname.split('/').pop() ?? '';
      const actorId   = request.headers.get('X-Actor-Id') ?? 'anonymous';

      // Fetch PHI from D1
      const row = await env.DB
        .prepare('SELECT * FROM patients WHERE id = ?')
        .bind(patientId)
        .first();

      // Append audit log — fire-and-forget is acceptable if latency is a concern
      await recordAuditLog(env, {
        actor_id:      actorId,
        resource_type: 'patient_record',
        resource_id:   patientId,
        action:        'READ',
        phi_accessed:  row !== null,
        ip:            request.headers.get('CF-Connecting-IP') ?? undefined,
        user_agent:    request.headers.get('User-Agent') ?? undefined,
      });

      if (!row) return new Response('Not Found', { status: 404 });
      return Response.json(row);
    }

    return new Response('Not Found', { status: 404 });
  },

  // ---------------------------------------------------------------------------
  // Cron Trigger: archive rows older than 6 years, then delete from D1
  // Schedule: "0 2 * * 0" — weekly at 02:00 UTC on Sunday
  // ---------------------------------------------------------------------------
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Date.now() - SIX_YEARS_MS;
    const runId  = crypto.randomUUID();
    const startedAt = Date.now();

    await env.DB
      .prepare(
        `INSERT INTO audit_archive_runs (id, started_at) VALUES (?, ?)`
      )
      .bind(runId, startedAt)
      .run();

    let totalArchived = 0;
    let r2Key = '';

    try {
      // Paginate to stay within D1 row limits
      while (true) {
        const batch = await env.DB
          .prepare(
            `SELECT * FROM access_logs WHERE ts < ? ORDER BY ts ASC LIMIT ?`
          )
          .bind(cutoff, ARCHIVE_BATCH)
          .all();

        if (batch.results.length === 0) break;

        const archiveDate = new Date().toISOString().slice(0, 10);
        r2Key = `hipaa-audit/${archiveDate}/${runId}-part${totalArchived}.json`;

        const ndjson = batch.results
          .map((r) => JSON.stringify(r))
          .join('\n');

        await env.AUDIT_ARCHIVE.put(r2Key, ndjson, {
          httpMetadata: { contentType: 'application/x-ndjson' },
        });

        // Delete archived rows
        const ids = batch.results.map((r) => (r as { id: string }).id);
        const placeholders = ids.map(() => '?').join(',');
        await env.DB
          .prepare(`DELETE FROM access_logs WHERE id IN (${placeholders})`)
          .bind(...ids)
          .run();

        totalArchived += batch.results.length;
        if (batch.results.length < ARCHIVE_BATCH) break;
      }

      await env.DB
        .prepare(
          `UPDATE audit_archive_runs
           SET finished_at = ?, rows_archived = ?, r2_key = ?, status = 'complete'
           WHERE id = ?`
        )
        .bind(Date.now(), totalArchived, r2Key, runId)
        .run();

    } catch (err) {
      await env.DB
        .prepare(
          `UPDATE audit_archive_runs SET status = 'failed', finished_at = ? WHERE id = ?`
        )
        .bind(Date.now(), runId)
        .run();
      throw err;
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Verification Queries

```sql
-- Count PHI access events in the last 24 hours
SELECT action, COUNT(*) AS cnt
FROM access_logs
WHERE phi_accessed = 1
  AND ts > (unixepoch('now') * 1000 - 86400000)
GROUP BY action;

-- Find all accesses by a specific actor
SELECT resource_type, resource_id, action, datetime(ts/1000, 'unixepoch') AS when_
FROM access_logs
WHERE actor_id = 'user-abc'
ORDER BY ts DESC
LIMIT 100;

-- Confirm no rows exist older than 6 years (post-archive)
SELECT COUNT(*) AS old_rows
FROM access_logs
WHERE ts < (unixepoch('now') * 1000 - CAST(6 * 365.25 * 86400 * 1000 AS INTEGER));
```

---

## Anti-patterns

- **Allowing UPDATE or DELETE on `access_logs`** — Any mutation of the audit trail violates HIPAA's integrity controls; enforce this via application policy and code review.
- **Logging only failures** — HIPAA requires recording all access attempts, successful or not.
- **Storing audit logs in the same table as PHI** — Separation ensures the audit trail survives even if PHI tables are restructured or purged.
- **Missing `phi_accessed` flag** — Without it, you cannot quickly extract the subset of records subject to breach notification rules.

---

## Gotchas

- D1 does not enforce immutability natively; an accidental `DELETE FROM access_logs` in a migration script will silently succeed.
- `crypto.randomUUID()` is available in Workers runtime without importing anything.
- The Cron Trigger `scheduled()` handler has a 30-second CPU time limit on the Free plan and 15 minutes on Paid — batch your archival accordingly.
- R2 has no native object expiry; set a lifecycle rule via the Cloudflare dashboard or API if you want archived files auto-deleted after a further retention period.
- D1 `batch()` API can reduce round-trips when inserting multiple audit rows in high-throughput scenarios.

---

## Verification

```bash
# Tail live audit log
npx wrangler d1 execute MY_DB \
  --command "SELECT actor_id, resource_type, action, phi_accessed, ts FROM access_logs ORDER BY ts DESC LIMIT 20"

# Manually trigger the Cron archival handler (local dev)
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+2+*+*+0"

# List R2 archival objects
npx wrangler r2 object list AUDIT_ARCHIVE --prefix hipaa-audit/

# Check archival run status
npx wrangler d1 execute MY_DB \
  --command "SELECT * FROM audit_archive_runs ORDER BY started_at DESC LIMIT 5"
```

---

## Related

- `workers-gdpr-right-to-erasure-d1.md`
- `workers-pci-dss-card-tokenization.md`
- `workers-gdpr-data-portability-r2.md`

---

## Sources

- HIPAA Security Rule 45 CFR §164.312(b) — https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare R2 — https://developers.cloudflare.com/r2/
