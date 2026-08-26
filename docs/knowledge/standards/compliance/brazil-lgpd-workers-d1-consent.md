# Brazil LGPD Compliance in Cloudflare Workers: Consent Management and Data Subject Rights

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application processes personal data of Brazilian residents and must comply with the Lei Geral de Proteção de Dados (LGPD, Law 13.709/2018). You need to record consent against the 10 legal bases, honour data subject rights requests (access, correction, deletion, portability), maintain a DPA appointment record, and send a 72-hour breach notification stub to the Autoridade Nacional de Proteção de Dados (ANPD).

---

## Context

LGPD applies to any organisation that processes personal data of individuals located in Brazil, regardless of where the organisation is headquartered. It defines 10 legal bases for processing (Art. 7), grants data subjects six core rights (Art. 18), and mandates breach notification to the ANPD within a reasonable period — the ANPD has operationally interpreted this as 72 hours for serious incidents. Controllers must appoint a Data Protection Officer (Encarregado) and record that appointment. Cloudflare D1 is well-suited for storing consent records and rights-request queues because it provides durable, queryable SQLite storage at the edge with Workers.

---

## Section 1 — D1 Schema

```sql
-- lgpd_consent: one row per data-subject / legal-basis / purpose combination
CREATE TABLE IF NOT EXISTS lgpd_consent (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id    TEXT NOT NULL,          -- hashed identifier (SHA-256 of email)
  legal_basis   TEXT NOT NULL,          -- e.g. 'consent', 'contract', 'legitimate_interest'
  purpose       TEXT NOT NULL,
  granted_at    TEXT NOT NULL DEFAULT (datetime('now')),
  withdrawn_at  TEXT,
  ip_hash       TEXT,                   -- SHA-256 of IP, not raw IP
  user_agent    TEXT,
  metadata      TEXT                    -- JSON blob for extra context
);

CREATE INDEX IF NOT EXISTS idx_lgpd_consent_subject ON lgpd_consent(subject_id);
CREATE INDEX IF NOT EXISTS idx_lgpd_consent_basis   ON lgpd_consent(legal_basis);

-- lgpd_rights_requests: tracks Art. 18 data subject requests
CREATE TABLE IF NOT EXISTS lgpd_rights_requests (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id    TEXT NOT NULL,
  request_type  TEXT NOT NULL CHECK(request_type IN
                  ('access','correction','deletion','portability',
                   'anonymisation','blocking','objection','revocation')),
  status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','in_progress','completed','rejected')),
  received_at   TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at  TEXT,
  notes         TEXT
);

-- lgpd_dpa_record: Data Processing Agreement / DPO appointment record
CREATE TABLE IF NOT EXISTS lgpd_dpa_record (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  dpo_name        TEXT NOT NULL,
  dpo_email       TEXT NOT NULL,
  appointed_at    TEXT NOT NULL DEFAULT (datetime('now')),
  organisation    TEXT NOT NULL,
  contact_channel TEXT
);

-- lgpd_breach_log: incident records for ANPD notification
CREATE TABLE IF NOT EXISTS lgpd_breach_log (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
  description     TEXT NOT NULL,
  affected_count  INTEGER,
  notified_anpd   INTEGER NOT NULL DEFAULT 0,  -- boolean
  notified_at     TEXT,
  severity        TEXT CHECK(severity IN ('low','medium','high','critical'))
);
```

---

## Section 2 — Worker Implementation

```typescript
import { Hono } from 'hono';
import { createHash } from 'node:crypto';

export interface Env {
  DB: D1Database;
}

const VALID_LEGAL_BASES = [
  'consent',
  'contract',
  'legal_obligation',
  'vital_interests',
  'public_interest',
  'legitimate_interest',
  'credit_protection',
  'research_health',
  'regulatory',
  'fraud_prevention',
] as const;

type LegalBasis = typeof VALID_LEGAL_BASES[number];

function hashIdentifier(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

const app = new Hono<{ Bindings: Env }>();

// POST /lgpd/consent — record consent for a specific legal basis + purpose
app.post('/lgpd/consent', async (c) => {
  const body = await c.req.json<{
    email: string;
    legal_basis: LegalBasis;
    purpose: string;
    metadata?: Record<string, unknown>;
  }>();

  if (!VALID_LEGAL_BASES.includes(body.legal_basis)) {
    return c.json({ error: 'Invalid legal basis' }, 400);
  }

  const subjectId = hashIdentifier(body.email);
  const ipHash = hashIdentifier(c.req.header('CF-Connecting-IP') ?? 'unknown');

  const result = await c.env.DB.prepare(
    `INSERT INTO lgpd_consent (subject_id, legal_basis, purpose, ip_hash, user_agent, metadata)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    subjectId,
    body.legal_basis,
    body.purpose,
    ipHash,
    c.req.header('User-Agent') ?? null,
    body.metadata ? JSON.stringify(body.metadata) : null
  ).run();

  return c.json({ id: result.meta.last_row_id, status: 'recorded' }, 201);
});

// DELETE /lgpd/consent — withdraw consent (Art. 8 §5)
app.delete('/lgpd/consent', async (c) => {
  const { email, purpose } = await c.req.json<{ email: string; purpose: string }>();
  const subjectId = hashIdentifier(email);

  await c.env.DB.prepare(
    `UPDATE lgpd_consent
     SET withdrawn_at = datetime('now')
     WHERE subject_id = ? AND purpose = ? AND withdrawn_at IS NULL`
  ).bind(subjectId, purpose).run();

  return c.json({ status: 'withdrawn' });
});

// POST /lgpd/rights — submit a data subject rights request (Art. 18)
app.post('/lgpd/rights', async (c) => {
  const body = await c.req.json<{ email: string; request_type: string }>();
  const subjectId = hashIdentifier(body.email);

  const result = await c.env.DB.prepare(
    `INSERT INTO lgpd_rights_requests (subject_id, request_type)
     VALUES (?, ?)`
  ).bind(subjectId, body.request_type).run();

  // Portability: immediately export available data
  if (body.request_type === 'portability') {
    const rows = await c.env.DB.prepare(
      `SELECT legal_basis, purpose, granted_at, withdrawn_at
       FROM lgpd_consent WHERE subject_id = ?`
    ).bind(subjectId).all();
    return c.json({ id: result.meta.last_row_id, export: rows.results });
  }

  return c.json({ id: result.meta.last_row_id, status: 'queued' }, 202);
});

export default app;
```

---

## Section 3 — Breach Notification Handler

```typescript
// Attach to your Hono app or export as a separate Worker

// POST /lgpd/breach — log a breach and trigger 72-hour ANPD notification stub
export async function handleBreachNotification(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    description: string;
    affected_count: number;
    severity: 'low' | 'medium' | 'high' | 'critical';
  }>();

  const { meta } = await env.DB.prepare(
    `INSERT INTO lgpd_breach_log (description, affected_count, severity)
     VALUES (?, ?, ?)`
  ).bind(body.description, body.affected_count, body.severity).run();

  const breachId = meta.last_row_id;

  // Severity >= high requires ANPD notification within 72 hours
  if (body.severity === 'high' || body.severity === 'critical') {
    // In production: replace with actual ANPD portal API call or email relay
    const anpdPayload = {
      controller: 'example.com',
      incident_id: breachId,
      detected_at: new Date().toISOString(),
      description: body.description,
      affected_count: body.affected_count,
      severity: body.severity,
    };

    // Stub: log to console; replace with real notification channel
    console.log('[LGPD] ANPD notification payload:', JSON.stringify(anpdPayload));

    await env.DB.prepare(
      `UPDATE lgpd_breach_log
       SET notified_anpd = 1, notified_at = datetime('now')
       WHERE id = ?`
    ).bind(breachId).run();
  }

  return new Response(JSON.stringify({ breach_id: breachId }), {
    status: 202,
    headers: { 'Content-Type': 'application/json' },
  });
}

// Scheduled check: mark breaches older than 72 h that were never notified
export async function scheduledBreachAudit(env: Env): Promise<void> {
  const overdue = await env.DB.prepare(
    `SELECT id, description, affected_count, severity
     FROM lgpd_breach_log
     WHERE notified_anpd = 0
       AND severity IN ('high','critical')
       AND datetime(detected_at, '+72 hours') < datetime('now')`
  ).all();

  for (const row of overdue.results as Array<Record<string, unknown>>) {
    console.error(
      `[LGPD] OVERDUE ANPD notification for breach ${
        row['id']
      } (${row['severity']} severity, ${row['affected_count']} subjects)`
    );
    // Trigger alert (PagerDuty, email, Slack webhook, etc.)
  }
}
```

---

## Anti-patterns

- **Storing raw email addresses as consent keys** — Always hash identifiers with SHA-256 before persisting; the hash still lets you look up a subject's records without storing PII in the consent table.
- **Single catch-all "consent" legal basis** — LGPD enumerates 10 distinct bases; using a generic flag makes compliance audits fail. Record the exact basis per processing activity.
- **Deleting consent records on withdrawal** — Withdrawal must be logged with a `withdrawn_at` timestamp, not a hard delete, so you can prove the timeline of consent if audited.
- **Blocking the response until ANPD notification completes** — Use `ctx.waitUntil()` or a queue to fire the notification asynchronously; do not hold the HTTP response open.

---

## Gotchas

- LGPD's 72-hour notification window is not explicitly in the statute — it was set by ANPD Resolution CD/ANPD/No. 2/2022; verify the current resolution before going live.
- D1's `randomblob(16)` produces a UUID-like value but is not RFC 4122 compliant; use a proper UUID library if interoperability is required.
- The `portability` export must be machine-readable (Art. 18 V); returning JSON satisfies this, but confirm the format with your DPO.
- Brazil is not on the EU adequacy list; if you transfer data to EU processors you still need LGPD Chapter V safeguards.

---

## Verification

```bash
# Apply schema
wrangler d1 execute lgpd-db --file=schema.sql

# Record consent
curl -X POST https://your-worker.dev/lgpd/consent \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","legal_basis":"consent","purpose":"marketing"}'

# Submit access request
curl -X POST https://your-worker.dev/lgpd/rights \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","request_type":"access"}'

# Simulate a high-severity breach
curl -X POST https://your-worker.dev/lgpd/breach \
  -H 'Content-Type: application/json' \
  -d '{"description":"Unauthorised DB export","affected_count":500,"severity":"high"}'

# Check overdue notifications
wrangler d1 execute lgpd-db \
  --command "SELECT * FROM lgpd_breach_log WHERE notified_anpd=0 AND severity IN ('high','critical');"
```

---

## Related

- `thailand-pdpa-workers-d1.md`
- `nigeria-ndpr-workers-d1.md`
- `workers-data-retention-policy-engine.md`
- `workers-privacy-by-design-data-minimisation.md`

---

## Sources

- Lei Geral de Proteção de Dados (Law 13.709/2018) — https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- ANPD Resolution CD/ANPD/No. 2/2022 (breach notification) — https://www.gov.br/anpd/pt-br/documentos-e-publicacoes/resolucao-cd-anpd-no-2-2022.pdf
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
