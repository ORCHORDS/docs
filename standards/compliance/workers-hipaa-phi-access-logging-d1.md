# HIPAA PHI Access Logging with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your application handles Protected Health Information (PHI) and you need a tamper-evident, immutable audit trail of every access event to satisfy HIPAA Security Rule §164.312(b) — audit controls — and §164.308(a)(1)(ii)(D) — information system activity review. You need 6-year log retention, structured event schema, and an admin report endpoint.

## Context

HIPAA requires covered entities and business associates to implement hardware, software, and procedural mechanisms that record and examine activity in information systems that contain or use ePHI. Cloudflare Workers + D1 can fulfil this when:

- Every PHI read/write/delete goes through a Workers route that appends an audit record.
- D1 rows are written as INSERT-only (no UPDATE/DELETE on the audit table).
- A Durable Object or cron job enforces retention windows and flags expired records for legal-hold review.
- Cloudflare signs a Business Associate Agreement (BAA) — required before storing any ePHI in D1, KV, R2, or any Cloudflare-managed store.

BAA status: Cloudflare offers a BAA under their HIPAA compliance program. Engage your Cloudflare account team before go-live with ePHI data.

## Solution

### 1. D1 Schema — append-only audit table

```sql
-- migrations/0001_phi_audit_log.sql
CREATE TABLE IF NOT EXISTS phi_audit_log (
  id            TEXT PRIMARY KEY,          -- UUIDv7, sortable
  event_time    TEXT NOT NULL,             -- ISO-8601 UTC
  actor_id      TEXT NOT NULL,             -- authenticated user/service ID
  actor_role    TEXT NOT NULL,             -- e.g. 'clinician', 'admin', 'hl7-service'
  patient_id    TEXT NOT NULL,             -- de-identified reference (not SSN)
  resource_type TEXT NOT NULL,             -- 'Observation', 'MedicationRequest', etc.
  resource_id   TEXT NOT NULL,             -- FHIR resource ID
  action        TEXT NOT NULL,             -- 'READ' | 'WRITE' | 'DELETE' | 'EXPORT'
  purpose       TEXT NOT NULL,             -- 'treatment' | 'payment' | 'operations' | 'research'
  outcome       TEXT NOT NULL,             -- 'success' | 'denied' | 'error'
  source_ip     TEXT NOT NULL,
  user_agent    TEXT,
  session_id    TEXT,
  data_elements TEXT,                      -- JSON array of accessed field names
  reason        TEXT,                      -- free-text justification when required
  retain_until  TEXT NOT NULL              -- event_time + 6 years
);

-- Prevent accidental row modification at the DB layer
CREATE TRIGGER IF NOT EXISTS phi_audit_no_update
  BEFORE UPDATE ON phi_audit_log
BEGIN
  SELECT RAISE(ABORT, 'phi_audit_log rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS phi_audit_no_delete
  BEFORE DELETE ON phi_audit_log
BEGIN
  SELECT RAISE(ABORT, 'phi_audit_log rows cannot be deleted before retain_until');
END;

CREATE INDEX idx_phi_audit_patient  ON phi_audit_log(patient_id, event_time);
CREATE INDEX idx_phi_audit_actor    ON phi_audit_log(actor_id, event_time);
CREATE INDEX idx_phi_audit_resource ON phi_audit_log(resource_id, event_time);
```

### 2. Audit event schema (TypeScript)

```typescript
// src/types/phi-audit.ts
export type PhiAction   = 'READ' | 'WRITE' | 'DELETE' | 'EXPORT';
export type PhiPurpose  = 'treatment' | 'payment' | 'operations' | 'research' | 'emergency';
export type PhiOutcome  = 'success' | 'denied' | 'error';

export interface PhiAuditEvent {
  /** UUIDv7 — time-sortable, globally unique */
  id: string;
  event_time: string;       // ISO-8601 UTC
  actor_id: string;
  actor_role: string;
  patient_id: string;
  resource_type: string;
  resource_id: string;
  action: PhiAction;
  purpose: PhiPurpose;
  outcome: PhiOutcome;
  source_ip: string;
  user_agent?: string;
  session_id?: string;
  data_elements?: string[]; // which PHI fields were touched
  reason?: string;          // required for 'research' | 'emergency'
  retain_until: string;     // event_time + 6 years
}
```

### 3. Audit logger utility

```typescript
// src/lib/phi-audit-logger.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { PhiAuditEvent, PhiAction, PhiPurpose, PhiOutcome } from '../types/phi-audit';

function uuidv7(): string {
  const now = Date.now();
  const hi = Math.floor(now / 0x1000).toString(16).padStart(12, '0');
  const lo = Math.random().toString(16).slice(2, 18).padStart(16, '0');
  return `${hi.slice(0,8)}-${hi.slice(8,12)}-7${lo.slice(0,3)}-${((parseInt(lo[3],16)&0x3)|0x8).toString(16)}${lo.slice(4,7)}-${lo.slice(7,19)}`;
}

function addYears(isoDate: string, years: number): string {
  const d = new Date(isoDate);
  d.setUTCFullYear(d.getUTCFullYear() + years);
  return d.toISOString();
}

export interface AuditParams {
  db: D1Database;
  actor_id: string;
  actor_role: string;
  patient_id: string;
  resource_type: string;
  resource_id: string;
  action: PhiAction;
  purpose: PhiPurpose;
  outcome: PhiOutcome;
  source_ip: string;
  user_agent?: string;
  session_id?: string;
  data_elements?: string[];
  reason?: string;
}

export async function logPhiAccess(params: AuditParams): Promise<string> {
  const event_time   = new Date().toISOString();
  const retain_until = addYears(event_time, 6);
  const id           = uuidv7();

  const event: PhiAuditEvent = {
    id,
    event_time,
    retain_until,
    actor_id: params.actor_id,
    actor_role: params.actor_role,
    patient_id: params.patient_id,
    resource_type: params.resource_type,
    resource_id: params.resource_id,
    action: params.action,
    purpose: params.purpose,
    outcome: params.outcome,
    source_ip: params.source_ip,
    user_agent: params.user_agent,
    session_id: params.session_id,
    data_elements: params.data_elements,
    reason: params.reason,
  };

  await params.db
    .prepare(`
      INSERT INTO phi_audit_log
        (id, event_time, actor_id, actor_role, patient_id,
         resource_type, resource_id, action, purpose, outcome,
         source_ip, user_agent, session_id, data_elements, reason, retain_until)
      VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `)
    .bind(
      event.id, event.event_time, event.actor_id, event.actor_role, event.patient_id,
      event.resource_type, event.resource_id, event.action, event.purpose, event.outcome,
      event.source_ip, event.user_agent ?? null, event.session_id ?? null,
      event.data_elements ? JSON.stringify(event.data_elements) : null,
      event.reason ?? null, event.retain_until
    )
    .run();

  return id;
}
```

### 4. PHI-gated resource endpoint

```typescript
// src/routes/observations.ts
import { Hono } from 'hono';
import { logPhiAccess } from '../lib/phi-audit-logger';
import { authenticate } from '../lib/auth';

type Env = { DB: D1Database };

const app = new Hono<{ Bindings: Env }>();

app.get('/fhir/Observation/:id', async (c) => {
  const actor = await authenticate(c);
  if (!actor) {
    await logPhiAccess({
      db: c.env.DB, actor_id: 'anonymous', actor_role: 'unknown',
      patient_id: 'unknown', resource_type: 'Observation',
      resource_id: c.req.param('id'), action: 'READ',
      purpose: 'treatment', outcome: 'denied',
      source_ip: c.req.header('CF-Connecting-IP') ?? '0.0.0.0',
      user_agent: c.req.header('User-Agent'),
    });
    return c.json({ error: 'Unauthorized' }, 401);
  }

  const purpose = (c.req.query('purpose') ?? 'treatment') as any;

  // Validate that high-sensitivity purposes include a reason
  if (purpose === 'research' && !c.req.query('reason')) {
    return c.json({ error: 'reason required for research access' }, 400);
  }

  let outcome: 'success' | 'error' = 'success';
  let resource: unknown;

  try {
    const row = await c.env.DB
      .prepare('SELECT * FROM observations WHERE id = ?')
      .bind(c.req.param('id'))
      .first();

    if (!row) return c.json({ error: 'Not Found' }, 404);
    resource = row;
  } catch (err) {
    outcome = 'error';
    await logPhiAccess({
      db: c.env.DB,
      actor_id: actor.id, actor_role: actor.role,
      patient_id: (resource as any)?.patient_id ?? 'unknown',
      resource_type: 'Observation', resource_id: c.req.param('id'),
      action: 'READ', purpose, outcome,
      source_ip: c.req.header('CF-Connecting-IP') ?? '0.0.0.0',
      user_agent: c.req.header('User-Agent'),
      session_id: actor.session_id,
    });
    return c.json({ error: 'Internal error' }, 500);
  }

  await logPhiAccess({
    db: c.env.DB,
    actor_id: actor.id, actor_role: actor.role,
    patient_id: (resource as any).patient_id,
    resource_type: 'Observation', resource_id: c.req.param('id'),
    action: 'READ', purpose, outcome,
    source_ip: c.req.header('CF-Connecting-IP') ?? '0.0.0.0',
    user_agent: c.req.header('User-Agent'),
    session_id: actor.session_id,
    data_elements: ['status', 'code', 'valueQuantity', 'effectiveDateTime'],
    reason: c.req.query('reason'),
  });

  return c.json(resource);
});

export default app;
```

### 5. Audit report endpoint (admin-only)

```typescript
// src/routes/audit-report.ts
import { Hono } from 'hono';
import { requireRole } from '../lib/auth';

type Env = { DB: D1Database };
const app = new Hono<{ Bindings: Env }>();

/** GET /admin/audit/phi?patient_id=&actor_id=&from=&to=&action=&page= */
app.get('/admin/audit/phi', requireRole('compliance-officer'), async (c) => {
  const { patient_id, actor_id, from, to, action, page = '1' } = c.req.query();
  const limit  = 200;
  const offset = (parseInt(page) - 1) * limit;

  const clauses: string[] = [];
  const binds: unknown[]  = [];

  if (patient_id) { clauses.push('patient_id = ?');  binds.push(patient_id); }
  if (actor_id)   { clauses.push('actor_id = ?');    binds.push(actor_id); }
  if (action)     { clauses.push('action = ?');      binds.push(action); }
  if (from)       { clauses.push('event_time >= ?'); binds.push(from); }
  if (to)         { clauses.push('event_time <= ?'); binds.push(to); }

  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  binds.push(limit, offset);

  const { results } = await c.env.DB
    .prepare(`SELECT * FROM phi_audit_log ${where} ORDER BY event_time DESC LIMIT ? OFFSET ?`)
    .bind(...binds)
    .all();

  return c.json({ page: parseInt(page), limit, results });
});

export default app;
```

### 6. Retention enforcement cron

```typescript
// src/cron/retention-check.ts
export async function enforceRetention(db: D1Database, env: string): Promise<void> {
  if (env === 'production') {
    // In production: never delete — move expired rows to legal-hold flag instead
    await db
      .prepare(`
        UPDATE phi_audit_log
        SET reason = reason || ' [RETENTION-EXPIRED-LEGAL-HOLD]'
        WHERE retain_until < ? AND reason NOT LIKE '%LEGAL-HOLD%'
      `)
      .bind(new Date().toISOString())
      .run();
  }
  // Non-production envs can purge test data older than retain_until
}
```

```typescript
// wrangler.toml snippet
// [triggers]
// crons = ["0 2 * * *"]   -- run daily at 02:00 UTC
```

## Implementation Details

- **UUIDv7** as primary key ensures chronological ordering without a separate index on `event_time`, which keeps INSERT hot-path fast.
- **Immutability triggers** in SQLite fire before any UPDATE/DELETE, raising ABORT so the transaction rolls back. This is your last line of defence if application code contains a bug or rogue migration.
- **`retain_until`** is computed at write time (event_time + 6 years) rather than derived on query, so retention compliance is clear even if the business rule changes later.
- **Dual-write pattern**: for critical PHI endpoints, write audit row *before* returning the response body. If the audit INSERT fails, return 500 — access was not logged, so it must not proceed.
- **Cloudflare BAA**: Cloudflare's BAA covers Workers, D1, R2, and KV when configured correctly. Confirm in-scope services with your Cloudflare account team and retain a copy of the signed BAA as part of your HIPAA documentation set.

## Anti-patterns

- **Async fire-and-forget audit log** (`ctx.waitUntil(logPhiAccess(...))`): the log might be lost on process exit. For PHI, log synchronously and fail the request if the log fails.
- **Logging raw SSN or MRN** in `patient_id`: use an internal opaque identifier; map to external IDs only in a separate, access-controlled table.
- **Storing PHI in `data_elements` values** rather than field names: log which fields were accessed, not the values themselves.
- **Skipping the deny log**: every access attempt — successful or not — must be recorded. Failure to log denials hides brute-force probing.
- **Purging audit rows in production**: even after the 6-year window, consult legal before deletion; litigation holds may extend retention indefinitely.

## Gotchas

- D1 is eventually consistent across read replicas. The audit log INSERT always goes to the primary writer — never read from a replica for compliance reporting.
- Workers have a 50 ms CPU time limit on the free plan. Audit INSERTs are fast (<1 ms), but if you batch them, use `ctx.waitUntil` only for non-critical supplemental telemetry, not the primary compliance log.
- The `CF-Connecting-IP` header is set by Cloudflare and cannot be spoofed from the public internet when the request passes through Cloudflare's edge — but verify this assumption in your threat model if you expose Workers on a non-proxied hostname.

## Verification

```bash
# 1. Insert a test event
curl -X GET "https://api.example.com/fhir/Observation/obs-001?purpose=treatment" \
  -H "Authorization: Bearer $TOKEN"

# 2. Query the audit log
curl "https://api.example.com/admin/audit/phi?resource_id=obs-001" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 3. Attempt illegal update (should fail)
wrangler d1 execute HIPAA_DB \
  --command "UPDATE phi_audit_log SET action='FAKED' WHERE id='<id>'"
# Expected: Error: phi_audit_log rows are immutable

# 4. Verify retention field
wrangler d1 execute HIPAA_DB \
  --command "SELECT id, event_time, retain_until FROM phi_audit_log LIMIT 5"
```

## Related

- `documentation/categories/compliance/workers-gdpr-data-subject-rights-api.md`
- `documentation/categories/compliance/workers-access-recertification-campaign-d1.md`
- `documentation/categories/security/workers-jwt-auth-pattern.md`

## Sources

- HIPAA Security Rule 45 CFR §164.312(b) — Audit Controls
- HIPAA Security Rule 45 CFR §164.308(a)(1)(ii)(D) — Information System Activity Review
- Cloudflare HIPAA Compliance: https://www.cloudflare.com/trust-hub/compliance-resources/hipaa/
- Cloudflare D1 Documentation: https://developers.cloudflare.com/d1/
- NIST SP 800-66r2 — Implementing HIPAA Security Rule
