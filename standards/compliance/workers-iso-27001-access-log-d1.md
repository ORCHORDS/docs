# ISO 27001 A.9 Access Control: API Access Logging to D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

ISO 27001 Annex A.9 requires organisations to log every access to information assets, retain those logs for the audit period, and be able to export evidence on demand. When your API runs on Cloudflare Workers you need a lightweight, durable log store that survives Worker restarts and can be queried by auditors without giving them production credentials.

## Context

- Runtime: Cloudflare Workers (ES2022, TypeScript)
- Storage: Cloudflare D1 (SQLite-compatible)
- Scheduler: Workers Cron Triggers (retention sweep)
- Auth: JWT bearer tokens (sub = user ID)
- ISO 27001:2022 control: A.9.4.2 (Secure log-on procedures), A.9.2.1 (User registration)

---

## Section 1: D1 Schema

Create the access log table in a migration file.

```sql
-- migrations/0001_access_log.sql
CREATE TABLE IF NOT EXISTS access_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  user_id     TEXT    NOT NULL,
  ip          TEXT    NOT NULL,
  method      TEXT    NOT NULL,
  resource    TEXT    NOT NULL,
  action      TEXT    NOT NULL,  -- READ | WRITE | DELETE | ADMIN
  status_code INTEGER NOT NULL,
  user_agent  TEXT,
  request_id  TEXT
);

CREATE INDEX IF NOT EXISTS idx_access_log_user ON access_log(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_access_log_ts   ON access_log(ts);
```

Apply via Wrangler:

```bash
npx wrangler d1 migrations apply ACCESS_LOG_DB --remote
```

---

## Section 2: Worker — Middleware Logger

```typescript
// src/middleware/accessLog.ts
import { Env } from '../types';

export interface LogEntry {
  user_id: string;
  ip: string;
  method: string;
  resource: string;
  action: string;
  status_code: number;
  user_agent: string | null;
  request_id: string | null;
}

export async function writeAccessLog(
  db: D1Database,
  entry: LogEntry
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO access_log
         (user_id, ip, method, resource, action, status_code, user_agent, request_id)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      entry.user_id,
      entry.ip,
      entry.method,
      entry.resource,
      entry.action,
      entry.status_code,
      entry.user_agent,
      entry.request_id
    )
    .run();
}

function deriveAction(method: string, pathname: string): string {
  if (method === 'GET')    return 'READ';
  if (method === 'DELETE') return 'DELETE';
  if (pathname.includes('/admin/')) return 'ADMIN';
  return 'WRITE';
}

// Wraps a fetch handler; must be called after JWT validation sets request headers
export function withAccessLog(
  handler: (req: Request, env: Env, ctx: ExecutionContext) => Promise<Response>
) {
  return async (req: Request, env: Env, ctx: ExecutionContext): Promise<Response> => {
    const response = await handler(req, env, ctx);
    const url = new URL(req.url);

    const entry: LogEntry = {
      user_id:     req.headers.get('X-User-Id')  ?? 'anonymous',
      ip:          req.headers.get('CF-Connecting-IP') ?? '0.0.0.0',
      method:      req.method,
      resource:    url.pathname,
      action:      deriveAction(req.method, url.pathname),
      status_code: response.status,
      user_agent:  req.headers.get('User-Agent'),
      request_id:  req.headers.get('CF-Ray'),
    };

    // Use waitUntil so the log write does not block the response
    ctx.waitUntil(writeAccessLog(env.ACCESS_LOG_DB, entry));
    return response;
  };
}
```

---

## Section 3: Retention Sweep Cron

ISO 27001 commonly requires 1-year log retention. This cron deletes rows older than the configured retention window.

```typescript
// src/cron/retentionSweep.ts
import { Env } from '../types';

const RETENTION_DAYS = 365; // adjust per your ISMS policy

export async function runRetentionSweep(env: Env): Promise<void> {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - RETENTION_DAYS);
  const cutoffISO = cutoff.toISOString().replace('T', ' ').slice(0, 19);

  const result = await env.ACCESS_LOG_DB
    .prepare('DELETE FROM access_log WHERE ts < ?')
    .bind(cutoffISO)
    .run();

  console.log(`[retention-sweep] deleted ${result.meta.changes} rows older than ${cutoffISO}`);
}
```

```typescript
// src/index.ts (scheduled handler)
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runRetentionSweep(env));
  },
  async fetch(req: Request, env: Env, ctx: ExecutionContext) {
    return withAccessLog(mainRouter)(req, env, ctx);
  },
};
```

```toml
# wrangler.toml
[[d1_databases]]
binding = "ACCESS_LOG_DB"
database_name = "access-log"
database_id   = "<your-d1-id>"

[triggers]
crons = ["0 2 * * *"]  # 02:00 UTC daily sweep
```

---

## Section 4: Audit Evidence Export

Provide a protected `/admin/audit-export` endpoint that streams a CSV of logs for a date range. Only your ISMS team should have the `ADMIN` role.

```typescript
// src/routes/auditExport.ts
export async function handleAuditExport(
  req: Request,
  db: D1Database
): Promise<Response> {
  const url  = new URL(req.url);
  const from = url.searchParams.get('from') ?? '2000-01-01';
  const to   = url.searchParams.get('to')   ?? new Date().toISOString();

  const rows = await db
    .prepare(
      `SELECT id, ts, user_id, ip, method, resource, action, status_code, request_id
       FROM access_log
       WHERE ts BETWEEN ? AND ?
       ORDER BY ts ASC`
    )
    .bind(from, to)
    .all();

  const header = 'id,ts,user_id,ip,method,resource,action,status_code,request_id\n';
  const lines  = (rows.results as Record<string, unknown>[]).map((r) =>
    [
      r.id, r.ts, r.user_id, r.ip,
      r.method, r.resource, r.action,
      r.status_code, r.request_id,
    ].join(',')
  );

  return new Response(header + lines.join('\n'), {
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': `attachment; filename="access-log-${from}-${to}.csv"`,
    },
  });
}
```

---

## Anti-patterns

- Logging inside the same transaction as the business operation — a rollback wipes the audit record.
- Writing logs synchronously before returning the HTTP response — adds latency; use `ctx.waitUntil`.
- Storing raw passwords or full JWT payloads in the log — violates A.9.4 and GDPR simultaneously.
- Deleting logs without verifying the retention window against your documented ISMS policy.
- Exporting logs over unauthenticated endpoints.

## Gotchas

- D1 `run()` does not throw on constraint violations by default; check `result.meta.last_row_id` to confirm the insert landed.
- `CF-Connecting-IP` is the real client IP behind Cloudflare; do not use `X-Forwarded-For` which is user-spoofable.
- `CF-Ray` uniquely identifies a request across Workers and is the best correlation ID for audit purposes.
- D1 free tier has a 100k write/day limit; at high throughput batch inserts or use an intermediate KV buffer.

---

## Verification

```bash
# Apply migration
npx wrangler d1 migrations apply ACCESS_LOG_DB --remote

# Trigger a real request and verify the row
npx wrangler d1 execute ACCESS_LOG_DB --remote \
  --command "SELECT * FROM access_log ORDER BY id DESC LIMIT 5;"

# Test export endpoint (replace token)
curl -H "Authorization: Bearer $ADMIN_JWT" \
  "https://api.example.com/admin/audit-export?from=2026-01-01&to=2026-12-31" \
  -o audit.csv
head audit.csv

# Verify retention sweep removes old rows
npx wrangler d1 execute ACCESS_LOG_DB --remote \
  --command "SELECT COUNT(*) FROM access_log WHERE ts < date('now','-365 days');"
```

---

## Related

- `documentation/categories/compliance/workers-nist-csf-incident-response-d1.md`
- `documentation/categories/compliance/workers-glba-financial-safeguards-encryption.md`
- `documentation/workers/d1-pagination-large-tables.md`

## Sources

- https://www.iso.org/standard/27001 (ISO/IEC 27001:2022 Annex A.9)
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
