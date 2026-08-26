# Nigeria NDPR Compliance in Cloudflare Workers: DPIA Records, Consent Middleware, NITDA Breach Notification, and Annual Audit Cron

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You operate a digital service that processes personal data of Nigerian residents and must comply with the Nigeria Data Protection Regulation 2019 (NDPR) issued by the National Information Technology Development Agency (NITDA). You need to store Data Protection Impact Assessment (DPIA) records in D1, enforce a consent-before-collection middleware in Workers, send a 72-hour breach notification to NITDA, and generate an annual audit report via a scheduled Cron that aggregates processing activities.

---

## Context

The NDPR (and its 2023 successor, the Nigeria Data Protection Act) requires organisations processing personal data of more than 2,000 data subjects per year to appoint a Data Protection Compliance Organisation (DPCO) and conduct annual audits. Consent must be obtained before collection for non-exempt categories. DPIAs are mandatory for high-risk processing (large-scale profiling, sensitive data, automated decision-making). NITDA must be notified of breaches within 72 hours of becoming aware. Cloudflare D1 provides the durable storage layer for all three record types; Workers middleware enforces the consent gate before any data reaches backend services.

---

## Section 1 — D1 Schema

```sql
-- ndpr_consents: consent-before-collection records
CREATE TABLE IF NOT EXISTS ndpr_consents (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_hash    TEXT NOT NULL,
  purpose         TEXT NOT NULL,
  data_categories TEXT NOT NULL,     -- JSON array: ['name','email','phone']
  granted_at      TEXT NOT NULL DEFAULT (datetime('now')),
  withdrawn_at    TEXT,
  ip_hash         TEXT,
  evidence_ref    TEXT               -- URL or ref to stored consent proof
);

CREATE INDEX IF NOT EXISTS idx_ndpr_consents_subject ON ndpr_consents(subject_hash);

-- ndpr_dpia: Data Protection Impact Assessment records
CREATE TABLE IF NOT EXISTS ndpr_dpia (
  id                TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  processing_name   TEXT NOT NULL,
  description       TEXT NOT NULL,
  risk_level        TEXT NOT NULL CHECK(risk_level IN ('low','medium','high')),
  mitigations       TEXT,            -- JSON array of mitigation measures
  dpo_approved_by   TEXT,
  approved_at       TEXT,
  review_due_at     TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ndpr_processing_activities: annual audit source of truth
CREATE TABLE IF NOT EXISTS ndpr_processing_activities (
  id                TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  activity_name     TEXT NOT NULL,
  purpose           TEXT NOT NULL,
  lawful_basis      TEXT NOT NULL,
  data_categories   TEXT NOT NULL,   -- JSON array
  recipients        TEXT,            -- JSON array of recipient categories
  retention_period  TEXT,
  cross_border      INTEGER NOT NULL DEFAULT 0,
  recorded_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ndpr_breach_log: breach records for NITDA notification
CREATE TABLE IF NOT EXISTS ndpr_breach_log (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
  description     TEXT NOT NULL,
  affected_count  INTEGER NOT NULL DEFAULT 0,
  notified_nitda  INTEGER NOT NULL DEFAULT 0,
  notified_at     TEXT,
  dpco_ref        TEXT
);

-- ndpr_annual_audit_log: output of each Cron audit run
CREATE TABLE IF NOT EXISTS ndpr_annual_audit_log (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  audit_year      INTEGER NOT NULL,
  generated_at    TEXT NOT NULL DEFAULT (datetime('now')),
  total_consents  INTEGER,
  total_dpia      INTEGER,
  total_breaches  INTEGER,
  report_json     TEXT               -- full JSON report blob
);
```

---

## Section 2 — Worker Consent Middleware

```typescript
import { Hono, MiddlewareHandler } from 'hono';
import { createHash } from 'node:crypto';

export interface Env {
  DB: D1Database;
}

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

// Paths that require prior consent before data is collected
const CONSENT_REQUIRED_PATHS = [
  '/api/profile',
  '/api/newsletter',
  '/api/survey',
];

/**
 * ndprConsentGate: middleware that blocks requests from subjects who have not
 * granted consent for the endpoint's stated purpose.
 */
export const ndprConsentGate: MiddlewareHandler<{ Bindings: Env }> = async (
  c,
  next
) => {
  const path = new URL(c.req.url).pathname;
  const requiresConsent = CONSENT_REQUIRED_PATHS.some((p) =>
    path.startsWith(p)
  );

  if (!requiresConsent) return next();

  const identifier =
    c.req.header('X-Subject-ID') ??
    c.req.header('CF-Connecting-IP') ??
    'anonymous';

  const subjectHash = sha256(identifier);

  const consent = await c.env.DB.prepare(
    `SELECT id FROM ndpr_consents
     WHERE subject_hash = ?
       AND purpose = ?
       AND withdrawn_at IS NULL
     LIMIT 1`
  ).bind(subjectHash, path).first();

  if (!consent) {
    return c.json(
      {
        error: 'Consent required',
        message:
          'NDPR Art. 2.2: Personal data may not be collected without prior consent. ' +
          'Please grant consent at /ndpr/consent before accessing this endpoint.',
      },
      403
    );
  }

  return next();
};

const app = new Hono<{ Bindings: Env }>();
app.use('*', ndprConsentGate);

// POST /ndpr/consent — grant consent before data collection
app.post('/ndpr/consent', async (c) => {
  const body = await c.req.json<{
    identifier: string;
    purpose: string;
    data_categories: string[];
    evidence_ref?: string;
  }>();

  const subjectHash = sha256(body.identifier);
  const ipHash = sha256(c.req.header('CF-Connecting-IP') ?? 'unknown');

  await c.env.DB.prepare(
    `INSERT INTO ndpr_consents
       (subject_hash, purpose, data_categories, ip_hash, evidence_ref)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    subjectHash,
    body.purpose,
    JSON.stringify(body.data_categories),
    ipHash,
    body.evidence_ref ?? null
  ).run();

  return c.json({ status: 'consent_recorded' }, 201);
});

// POST /ndpr/dpia — record a Data Protection Impact Assessment
app.post('/ndpr/dpia', async (c) => {
  const body = await c.req.json<{
    processing_name: string;
    description: string;
    risk_level: 'low' | 'medium' | 'high';
    mitigations: string[];
    dpo_approved_by: string;
  }>();

  const reviewDue = new Date();
  reviewDue.setFullYear(reviewDue.getFullYear() + 1);

  await c.env.DB.prepare(
    `INSERT INTO ndpr_dpia
       (processing_name, description, risk_level, mitigations, dpo_approved_by,
        approved_at, review_due_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'), ?)`
  ).bind(
    body.processing_name,
    body.description,
    body.risk_level,
    JSON.stringify(body.mitigations),
    body.dpo_approved_by,
    reviewDue.toISOString()
  ).run();

  return c.json({ status: 'dpia_recorded' }, 201);
});

export default app;
```

---

## Section 3 — NITDA Breach Notification and Annual Audit Cron

```typescript
import type { Env } from './types';

// POST /ndpr/breach — log a breach and trigger NITDA notification stub
export async function handleNdprBreach(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    description: string;
    affected_count: number;
    dpco_ref: string;
  }>();

  const { meta } = await env.DB.prepare(
    `INSERT INTO ndpr_breach_log (description, affected_count, dpco_ref)
     VALUES (?, ?, ?)`
  ).bind(body.description, body.affected_count, body.dpco_ref).run();

  const breachId = meta.last_row_id;

  // NITDA notification stub — replace with actual NITDA portal submission
  const nitdaPayload = {
    organisation: 'example.com',
    dpco_ref: body.dpco_ref,
    breach_id: breachId,
    detected_at: new Date().toISOString(),
    affected_count: body.affected_count,
    description: body.description,
    contact_email: 'dpo@example.com',
  };

  console.log('[NDPR] NITDA notification payload:', JSON.stringify(nitdaPayload));

  await env.DB.prepare(
    `UPDATE ndpr_breach_log
     SET notified_nitda = 1, notified_at = datetime('now')
     WHERE id = ?`
  ).bind(breachId).run();

  return new Response(
    JSON.stringify({ breach_id: breachId, notified_nitda: true }),
    { status: 202, headers: { 'Content-Type': 'application/json' } }
  );
}

// Scheduled Cron: annual audit report (run on 1 Jan each year)
export async function scheduledNdprAnnualAudit(
  event: ScheduledEvent,
  env: Env
): Promise<void> {
  const year = new Date(event.scheduledTime).getUTCFullYear() - 1; // audit previous year
  const start = `${year}-01-01`;
  const end = `${year}-12-31`;

  const [consents, dpias, breaches, activities] = await Promise.all([
    env.DB.prepare(
      `SELECT COUNT(*) as count FROM ndpr_consents
       WHERE granted_at BETWEEN ? AND ?`
    ).bind(start, end).first<{ count: number }>(),
    env.DB.prepare(
      `SELECT COUNT(*) as count FROM ndpr_dpia
       WHERE created_at BETWEEN ? AND ?`
    ).bind(start, end).first<{ count: number }>(),
    env.DB.prepare(
      `SELECT COUNT(*) as count FROM ndpr_breach_log
       WHERE detected_at BETWEEN ? AND ?`
    ).bind(start, end).first<{ count: number }>(),
    env.DB.prepare(
      `SELECT activity_name, purpose, lawful_basis, data_categories
       FROM ndpr_processing_activities
       WHERE recorded_at BETWEEN ? AND ?`
    ).bind(start, end).all(),
  ]);

  const report = {
    audit_year: year,
    generated_at: new Date().toISOString(),
    total_consents: consents?.count ?? 0,
    total_dpia: dpias?.count ?? 0,
    total_breaches: breaches?.count ?? 0,
    processing_activities: activities.results,
  };

  await env.DB.prepare(
    `INSERT INTO ndpr_annual_audit_log
       (audit_year, total_consents, total_dpia, total_breaches, report_json)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    year,
    report.total_consents,
    report.total_dpia,
    report.total_breaches,
    JSON.stringify(report)
  ).run();

  console.log(`[NDPR] Annual audit for ${year} completed:`, JSON.stringify(report));
}

// wrangler.toml excerpt:
// [[d1_databases]]
// binding = "DB"
// database_name = "ndpr-db"
// database_id = "<your-d1-id>"
//
// [triggers]
// crons = ["0 0 1 1 *"]  # 00:00 UTC on 1 January
```

---

## Anti-patterns

- **Running the consent middleware only on POST requests** — Data collection can happen via GET query parameters (analytics, search logs); apply the gate to all methods that log or persist subject data.
- **Recording DPIA only at project start** — DPIAs must be reviewed when processing changes; store `review_due_at` and alert when it passes.
- **Treating NITDA notification as optional for small breaches** — The NDPR does not set a minimum affected-subject threshold; all breaches involving personal data must be assessed and notified if they pose a risk.
- **Storing the full audit report only in memory** — Use `ndpr_annual_audit_log` to persist the report so it survives Worker restarts and can be exported for the DPCO.

---

## Gotchas

- The Nigeria Data Protection Act 2023 (NDPA) supersedes the 2019 NDPR; verify which version your processing agreements reference and update `lawful_basis` values accordingly.
- NITDA does not publish a public breach notification API; the stub must trigger an operator workflow (email, ticketing system) that results in a manual portal submission.
- The annual audit must be submitted to a DPCO (licensed compliance organisation), not directly to NITDA; store the `dpco_ref` in your breach and audit records.
- `datetime('now')` in D1 returns UTC; when generating human-readable reports for Nigerian stakeholders, convert to WAT (UTC+1).

---

## Verification

```bash
# Apply schema
wrangler d1 execute ndpr-db --file=schema.sql

# Grant consent
curl -X POST https://your-worker.dev/ndpr/consent \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"user@example.com","purpose":"/api/newsletter",\
       "data_categories":["email","name"]}'

# Attempt access without consent (should return 403)
curl https://your-worker.dev/api/newsletter

# Record a DPIA
curl -X POST https://your-worker.dev/ndpr/dpia \
  -H 'Content-Type: application/json' \
  -d '{"processing_name":"Email marketing","description":"Newsletter sends",\
       "risk_level":"medium","mitigations":["Encryption at rest"],\
       "dpo_approved_by":"Jane DPO"}'

# Log a breach
curl -X POST https://your-worker.dev/ndpr/breach \
  -H 'Content-Type: application/json' \
  -d '{"description":"Customer list exported","affected_count":1500,\
       "dpco_ref":"DPCO-NG-0042"}'

# Trigger annual audit manually
wrangler d1 execute ndpr-db \
  --command "SELECT * FROM ndpr_annual_audit_log ORDER BY generated_at DESC LIMIT 1;"
```

---

## Related

- `brazil-lgpd-workers-d1-consent.md`
- `thailand-pdpa-workers-d1.md`
- `workers-data-retention-policy-engine.md`
- `workers-privacy-by-design-data-minimisation.md`

---

## Sources

- Nigeria Data Protection Regulation 2019 — https://nitda.gov.ng/wp-content/uploads/2019/01/NigeriaDataProtectionRegulation.pdf
- Nigeria Data Protection Act 2023 — https://ndpb.gov.ng/Files/Nigeria_Data_Protection_Act_2023.pdf
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
