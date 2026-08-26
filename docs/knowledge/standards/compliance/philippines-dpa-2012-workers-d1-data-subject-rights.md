# Philippines Data Privacy Act 2012 — Cloudflare Workers & D1 Implementation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application collects personal information from users in the Philippines and you need to comply with Republic Act 10173 (Data Privacy Act of 2012). You must register with the National Privacy Commission (NPC) as a Personal Information Controller (PIC), implement data subject rights endpoints, and build a 72-hour breach notification pipeline — all within a Cloudflare Workers + D1 architecture.

## Context

The Philippines DPA 2012, enforced by the NPC, applies to any entity processing personal information of Philippine residents regardless of where the controller is based. PICs handling sensitive personal information (SPI) — health data, biometrics, government IDs, sexual life, financial records — face stricter obligations than those handling ordinary personal data. The NPC requires mandatory registration for PICs with 250+ employees or those processing SPI. A mandatory Privacy Impact Assessment (PIA) must be documented before launching new systems touching personal data. Data subjects have six core rights: access, rectification, erasure/blocking, damages, data portability, and the right to object.

## D1 Schema: personal_data_inventory and data_subject_requests

```typescript
// migrations/0001_philippines_dpa.sql
export const SCHEMA = `
CREATE TABLE IF NOT EXISTS personal_data_inventory (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  data_type   TEXT NOT NULL,          -- 'ordinary' | 'sensitive'
  category    TEXT NOT NULL,          -- e.g. 'health', 'financial', 'biometric'
  purpose     TEXT NOT NULL,
  legal_basis TEXT NOT NULL,
  retention_days INTEGER NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS data_subject_requests (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id   TEXT NOT NULL,
  request_type TEXT NOT NULL CHECK(request_type IN ('access','rectification','erasure','portability','object')),
  status       TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','denied')),
  received_at  TEXT NOT NULL DEFAULT (datetime('now')),
  deadline_at  TEXT NOT NULL,         -- 15 calendar days per NPC rules
  resolved_at  TEXT,
  notes        TEXT
);

CREATE TABLE IF NOT EXISTS breach_log (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
  notify_deadline TEXT NOT NULL,      -- detected_at + 72 hours
  npc_notified_at TEXT,
  affected_count  INTEGER,
  description     TEXT NOT NULL,
  severity        TEXT NOT NULL CHECK(severity IN ('low','medium','high','critical'))
);
`;
```

## Workers API: Data Subject Rights Endpoints

```typescript
// src/dpa-rights.ts
import { Env } from './types';

const DSR_DEADLINE_DAYS = 15;

export async function handleDSR(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;

  if (request.method === 'POST' && path === '/privacy/request') {
    return createDSR(request, env);
  }
  if (request.method === 'GET' && path.startsWith('/privacy/request/')) {
    const id = path.split('/').pop()!;
    return getDSRStatus(id, env);
  }
  return new Response('Not found', { status: 404 });
}

async function createDSR(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{
    subject_id: string;
    request_type: string;
    details?: string;
  }>();

  const validTypes = ['access', 'rectification', 'erasure', 'portability', 'object'];
  if (!validTypes.includes(body.request_type)) {
    return new Response(JSON.stringify({ error: 'Invalid request_type' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const deadlineAt = new Date();
  deadlineAt.setDate(deadlineAt.getDate() + DSR_DEADLINE_DAYS);

  const result = await env.DB.prepare(
    `INSERT INTO data_subject_requests (subject_id, request_type, deadline_at, notes)
     VALUES (?, ?, ?, ?) RETURNING id`
  )
    .bind(body.subject_id, body.request_type, deadlineAt.toISOString(), body.details ?? null)
    .first<{ id: string }>();

  return new Response(JSON.stringify({ id: result?.id, deadline: deadlineAt.toISOString() }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function getDSRStatus(id: string, env: Env): Promise<Response> {
  const row = await env.DB.prepare(
    `SELECT id, request_type, status, received_at, deadline_at, resolved_at FROM data_subject_requests WHERE id = ?`
  )
    .bind(id)
    .first();

  if (!row) return new Response('Not found', { status: 404 });
  return new Response(JSON.stringify(row), { headers: { 'Content-Type': 'application/json' } });
}
```

## 72-Hour Breach Notification Pipeline

```typescript
// src/breach-detection.ts
export async function logBreach(
  env: Env,
  description: string,
  affectedCount: number,
  severity: 'low' | 'medium' | 'high' | 'critical'
): Promise<string> {
  const notifyDeadline = new Date(Date.now() + 72 * 60 * 60 * 1000);

  const result = await env.DB.prepare(
    `INSERT INTO breach_log (description, affected_count, severity, notify_deadline)
     VALUES (?, ?, ?, ?) RETURNING id`
  )
    .bind(description, affectedCount, severity, notifyDeadline.toISOString())
    .first<{ id: string }>();

  // Alert via webhook for immediate response
  if (severity === 'high' || severity === 'critical') {
    await fetch(env.BREACH_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        breach_id: result?.id,
        severity,
        affected_count: affectedCount,
        npc_notify_deadline: notifyDeadline.toISOString(),
        description,
      }),
    });
  }

  return result?.id ?? '';
}

// Cron Worker: check for approaching 72-hour NPC notification deadlines
export async function checkBreachDeadlines(env: Env): Promise<void> {
  const cutoff = new Date(Date.now() + 6 * 60 * 60 * 1000).toISOString(); // 6 hours ahead
  const pending = await env.DB.prepare(
    `SELECT id, notify_deadline, description FROM breach_log
     WHERE npc_notified_at IS NULL AND notify_deadline <= ?`
  )
    .bind(cutoff)
    .all();

  for (const breach of pending.results) {
    await fetch(env.NPC_ALERT_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urgent: true, breach }),
    });
  }
}
```

## NPC Registration and PIA Documentation Pattern

PICs must register via the NPC online portal (https://www.privacy.gov.ph). Document in your PIA:

- **Data flows**: what personal data is collected, from whom, for what purpose, stored where, shared with whom.
- **Risk assessment**: likelihood and severity of privacy risks per NPC PIA methodology.
- **Mitigation measures**: encryption at rest (D1 encryption), HTTPS-only Workers, IP allowlisting via KV.
- **Retention schedule**: populate `personal_data_inventory.retention_days` per purpose.
- **DPO details**: designated Data Protection Officer name and contact must be filed with NPC.

Store PIA documents in R2 with restricted access and reference them in the `personal_data_inventory` table via a `pia_ref` column.

## Anti-patterns

- **Ignoring SPI classification** — treating health or biometric data the same as a display name causes under-protection; always tag rows with `data_type = 'sensitive'` and apply stricter access controls.
- **Missing deadline tracking** — the 15-day DSR response window is a hard NPC requirement; failing to set and monitor `deadline_at` leads to violations.
- **Self-certifying a breach as low severity to avoid notification** — NPC rules require notification for any breach involving SPI regardless of internal severity classification.

## Gotchas

- The NPC can extend jurisdiction to foreign PIPs (Personal Information Processors) that process data of Philippine residents — register even if headquartered abroad.
- Data portability responses must be in a structured, commonly used, machine-readable format (JSON or CSV is acceptable).
- Consent must be time-stamped and purposefully specific; blanket consent forms are deemed invalid by NPC.

## Verification

```bash
# Check DSR table for overdue requests
wrangler d1 execute example project-db --command \
  "SELECT id, request_type, status, deadline_at FROM data_subject_requests WHERE status NOT IN ('completed','denied') AND deadline_at < datetime('now');"

# Confirm breach notification deadlines within 6 hours
wrangler d1 execute example project-db --command \
  "SELECT id, severity, notify_deadline FROM breach_log WHERE npc_notified_at IS NULL AND notify_deadline <= datetime('now','+6 hours');"

# Verify inventory schema
wrangler d1 execute example project-db --command "SELECT * FROM personal_data_inventory LIMIT 5;"
```

## Related

- `turkey-kvkk-workers-d1-personal-data-processing.md`
- `saudi-arabia-pdpl-workers-d1-consent-management.md`
- `argentina-pdpa-workers-d1-data-protection.md`

## Sources

- Republic Act 10173 — https://www.privacy.gov.ph/data-privacy-act/
- NPC Registration Portal — https://www.privacy.gov.ph/registration/
- NPC PIA Guidelines — https://www.privacy.gov.ph/privacy-impact-assessment/
- NPC Circular 16-03 (Breach Notification) — https://www.privacy.gov.ph/npc-circular-16-03/
