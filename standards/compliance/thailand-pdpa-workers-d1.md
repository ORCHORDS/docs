# Thailand PDPA Compliance in Cloudflare Workers: Consent Withdrawal, Cross-Border Transfers, and PDPC Breach Notification

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You process personal data of individuals located in Thailand and must comply with the Personal Data Protection Act B.E. 2562 (PDPA). You need to record consents, allow withdrawal within 30 days of request, check whether cross-border data transfers target whitelisted countries, and notify the Personal Data Protection Committee (PDPC) when a breach affects 100 or more data subjects.

---

## Context

Thailand's PDPA (effective June 2022) mirrors GDPR's architecture: a lawful-basis requirement, data subject rights, cross-border transfer restrictions, and mandatory breach notification. The PDPC has ruled that consent withdrawal must be as easy as granting consent and must be actioned within 30 days. Cross-border transfers are permitted only to countries on the PDPC whitelist or where specific safeguards (BCRs, SCCs) are in place. Breach notification to the PDPC is required within 72 hours when a breach is likely to result in a high risk to the rights and freedoms of data subjects; for incidents affecting 100 or more subjects this threshold is presumed met. Cloudflare KV is used to store the whitelist countries so it can be updated without a Worker redeploy.

---

## Section 1 — D1 Schema

```sql
-- pdpa_consents: consent records per data subject and purpose
CREATE TABLE IF NOT EXISTS pdpa_consents (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_hash    TEXT NOT NULL,           -- SHA-256 of identifier
  purpose         TEXT NOT NULL,
  lawful_basis    TEXT NOT NULL DEFAULT 'consent'
                    CHECK(lawful_basis IN
                      ('consent','contract','vital_interest',
                       'public_task','legitimate_interest','legal_obligation')),
  granted_at      TEXT NOT NULL DEFAULT (datetime('now')),
  withdrawn_at    TEXT,
  withdrawal_deadline TEXT,               -- granted_at + 30 days
  ip_hash         TEXT,
  channel         TEXT                    -- 'web','app','paper','api'
);

CREATE INDEX IF NOT EXISTS idx_pdpa_consents_subject ON pdpa_consents(subject_hash);

-- pdpa_requests: data subject rights requests
CREATE TABLE IF NOT EXISTS pdpa_requests (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_hash    TEXT NOT NULL,
  request_type    TEXT NOT NULL CHECK(request_type IN
                    ('access','rectification','erasure','portability',
                     'restriction','objection','withdrawal')),
  status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','processing','completed','rejected')),
  received_at     TEXT NOT NULL DEFAULT (datetime('now')),
  deadline_at     TEXT NOT NULL           -- received_at + 30 days
                    DEFAULT (datetime('now', '+30 days')),
  completed_at    TEXT,
  rejection_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_pdpa_requests_deadline ON pdpa_requests(deadline_at);

-- pdpa_breach_log: incident records for PDPC notification
CREATE TABLE IF NOT EXISTS pdpa_breach_log (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
  description     TEXT NOT NULL,
  affected_count  INTEGER NOT NULL DEFAULT 0,
  high_risk       INTEGER NOT NULL DEFAULT 0,  -- boolean
  notified_pdpc   INTEGER NOT NULL DEFAULT 0,
  notified_at     TEXT,
  controller      TEXT NOT NULL DEFAULT 'example.com'
);
```

---

## Section 2 — Worker Implementation

```typescript
import { Hono } from 'hono';
import { createHash } from 'node:crypto';

export interface Env {
  DB: D1Database;
  PDPA_KV: KVNamespace;  // stores cross-border transfer whitelist
}

const app = new Hono<{ Bindings: Env }>();

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

// POST /pdpa/consent — record a new consent
app.post('/pdpa/consent', async (c) => {
  const body = await c.req.json<{
    identifier: string;  // email or user ID — will be hashed
    purpose: string;
    lawful_basis?: string;
    channel?: string;
  }>();

  const subjectHash = sha256(body.identifier);
  const ipHash = sha256(c.req.header('CF-Connecting-IP') ?? 'unknown');

  await c.env.DB.prepare(
    `INSERT INTO pdpa_consents
       (subject_hash, purpose, lawful_basis, ip_hash, channel, withdrawal_deadline)
     VALUES (?, ?, ?, ?, ?, datetime('now', '+30 days'))`
  ).bind(
    subjectHash,
    body.purpose,
    body.lawful_basis ?? 'consent',
    ipHash,
    body.channel ?? 'web'
  ).run();

  return c.json({ status: 'recorded' }, 201);
});

// POST /pdpa/consent/withdraw — withdraw consent; must complete within 30 days
app.post('/pdpa/consent/withdraw', async (c) => {
  const body = await c.req.json<{ identifier: string; purpose: string }>();
  const subjectHash = sha256(body.identifier);

  // Insert a rights request for withdrawal
  const { meta } = await c.env.DB.prepare(
    `INSERT INTO pdpa_requests (subject_hash, request_type)
     VALUES (?, 'withdrawal')`
  ).bind(subjectHash).run();

  // Immediately mark consent as withdrawn
  await c.env.DB.prepare(
    `UPDATE pdpa_consents
     SET withdrawn_at = datetime('now')
     WHERE subject_hash = ? AND purpose = ? AND withdrawn_at IS NULL`
  ).bind(subjectHash, body.purpose).run();

  return c.json({ request_id: meta.last_row_id, status: 'withdrawal_queued' }, 202);
});

// GET /pdpa/transfer-check?country=XX — cross-border transfer whitelist check
app.get('/pdpa/transfer-check', async (c) => {
  const country = (c.req.query('country') ?? '').toUpperCase();
  if (!country) return c.json({ error: 'country required' }, 400);

  // KV key: 'pdpa:whitelist' — value: JSON array of ISO 3166-1 alpha-2 codes
  const whitelistRaw = await c.env.PDPA_KV.get('pdpa:whitelist');
  const whitelist: string[] = whitelistRaw ? JSON.parse(whitelistRaw) : [];

  const permitted = whitelist.includes(country);
  return c.json({
    country,
    permitted,
    reason: permitted
      ? 'Country on PDPC adequacy whitelist'
      : 'Country not whitelisted — additional safeguards required (BCR/SCCs)',
  });
});

export default app;
```

---

## Section 3 — PDPC Breach Notification Handler

```typescript
// POST /pdpa/breach — log a breach and dispatch PDPC notification if needed
export async function handlePdpaBreachNotification(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    description: string;
    affected_count: number;
    high_risk?: boolean;
  }>();

  // Breaches affecting >= 100 subjects are presumed high-risk by PDPC guidance
  const highRisk = body.high_risk ?? body.affected_count >= 100;

  const { meta } = await env.DB.prepare(
    `INSERT INTO pdpa_breach_log (description, affected_count, high_risk)
     VALUES (?, ?, ?)`
  ).bind(body.description, body.affected_count, highRisk ? 1 : 0).run();

  const breachId = meta.last_row_id;

  if (highRisk) {
    // Build PDPC notification payload (structure per PDPC Form DB1)
    const pdpcPayload = {
      controller_name: 'example.com',
      dpo_contact: 'dpo@example.com',
      incident_date: new Date().toISOString(),
      incident_description: body.description,
      estimated_affected: body.affected_count,
      breach_id: breachId,
    };

    // Stub: replace with PDPC e-Saraban portal API or email relay
    console.log('[PDPA] PDPC notification payload:', JSON.stringify(pdpcPayload));

    await env.DB.prepare(
      `UPDATE pdpa_breach_log
       SET notified_pdpc = 1, notified_at = datetime('now')
       WHERE id = ?`
    ).bind(breachId).run();
  }

  return new Response(
    JSON.stringify({ breach_id: breachId, notified_pdpc: highRisk }),
    { status: 202, headers: { 'Content-Type': 'application/json' } }
  );
}

// Scheduled Cron: alert on overdue withdrawal requests (> 30 days unactioned)
export async function scheduledPdpaAudit(env: Env): Promise<void> {
  const overdue = await env.DB.prepare(
    `SELECT id, subject_hash, request_type, received_at
     FROM pdpa_requests
     WHERE status = 'pending'
       AND deadline_at < datetime('now')`
  ).all();

  for (const row of overdue.results as Array<Record<string, unknown>>) {
    console.error(
      `[PDPA] Overdue request ${row['id']} (type: ${row['request_type']}, ` +
      `received: ${row['received_at']})`
    );
  }

  // Also flag high-risk breaches not notified within 72 h
  const unnotified = await env.DB.prepare(
    `SELECT id FROM pdpa_breach_log
     WHERE high_risk = 1
       AND notified_pdpc = 0
       AND datetime(detected_at, '+72 hours') < datetime('now')`
  ).all();

  for (const row of unnotified.results as Array<Record<string, unknown>>) {
    console.error(`[PDPA] Breach ${row['id']} exceeds 72-hour PDPC notification window`);
  }
}
```

---

## Anti-patterns

- **Hardcoding the country whitelist in Worker code** — The PDPC whitelist changes; store it in KV so you can update it without a redeploy.
- **Conflating PDPA withdrawal with GDPR right to erasure** — Withdrawal of consent only stops future processing; it does not automatically trigger data deletion unless no other lawful basis applies.
- **Setting the 30-day deadline from the withdrawal *completion* date** — The deadline starts from the *receipt* of the withdrawal request, not when you process it.
- **Notifying only when affected_count is exactly known** — If you cannot determine the count at incident time, treat it as >= 100 (presumed high risk) and over-notify rather than under-notify.

---

## Gotchas

- Thailand's PDPC whitelist of adequate countries is published as ministerial regulations and is not identical to the EU's adequacy list; check the PDPC website for the current list before seeding KV.
- PDPA exempts certain categories (national security, journalism, household activities); verify your processing activity isn't exempt before building the full consent stack.
- The PDPC e-Saraban portal does not yet expose a public REST API; breach notification currently requires a web form submission — the stub should trigger an operator alert.
- D1 `datetime('now', '+30 days')` computes in UTC; ensure your front-end displays deadlines in Thailand Standard Time (UTC+7).

---

## Verification

```bash
# Apply schema
wrangler d1 execute pdpa-db --file=schema.sql

# Seed the country whitelist
wrangler kv key put --namespace-id=<KV_ID> 'pdpa:whitelist' \
  '["JP","KR","NZ","AU","GB"]'

# Record consent
curl -X POST https://your-worker.dev/pdpa/consent \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"user@example.com","purpose":"analytics","channel":"web"}'

# Withdraw consent
curl -X POST https://your-worker.dev/pdpa/consent/withdraw \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"user@example.com","purpose":"analytics"}'

# Check cross-border transfer to Japan
curl 'https://your-worker.dev/pdpa/transfer-check?country=JP'

# Simulate breach affecting 250 subjects
curl -X POST https://your-worker.dev/pdpa/breach \
  -H 'Content-Type: application/json' \
  -d '{"description":"DB credentials exposed","affected_count":250}'

# Verify breach log
wrangler d1 execute pdpa-db --command "SELECT * FROM pdpa_breach_log;"
```

---

## Related

- `brazil-lgpd-workers-d1-consent.md`
- `nigeria-ndpr-workers-d1.md`
- `workers-data-retention-policy-engine.md`
- `workers-privacy-by-design-data-minimisation.md`

---

## Sources

- Personal Data Protection Act B.E. 2562 (2019) — https://www.etda.or.th/getattachment/b4715bc7-0de4-48a2-a8c0-fd9f8cc9fe3c/PDPA-EN.pdf
- PDPC Notification on Cross-Border Transfer Criteria — https://pdpc.or.th/en/laws-regulations/
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
