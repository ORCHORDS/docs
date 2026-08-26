# Indonesia UU PDP 2022 Compliance with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your service processes personal data of Indonesian residents. You need to comply with Indonesia's Personal Data Protection Law (Undang-Undang Nomor 27 Tahun 2022 tentang Perlindungan Data Pribadi, UU PDP), which came into full effect in October 2024. Requirements include: fulfilling data subject rights (access, correction, deletion, portability) within 14 days, appointing a Data Protection Officer (DPO) for controllers processing sensitive data, and restricting cross-border transfers of personal data.

## Context

UU PDP is Indonesia's first comprehensive personal data protection law. Key articles:

- **Article 8–12** — data subject rights: access, correction, deletion (right to erasure), and portability.
- **Article 14** — controllers must respond to data subject requests within **14 calendar days**, extendable by 14 days with notice.
- **Article 21** — controllers processing sensitive personal data must **appoint a DPO**.
- **Article 34–36** — cross-border transfers require the destination country to have equivalent protection or the controller to use approved safeguards (standard clauses or binding corporate rules).
- **Article 57** — criminal penalties up to IDR 5 billion; administrative fines up to 2 % of annual revenue.
- Sensitive personal data includes health, biometric, genetic, sexual orientation, political views, financial data, and children's data.

## D1 Schema — data_subject_requests

```sql
CREATE TABLE IF NOT EXISTS data_subject_requests (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id        TEXT    NOT NULL,
  type           TEXT    NOT NULL CHECK(type IN
                   ('access','correction','deletion','portability','restriction')),
  status         TEXT    NOT NULL DEFAULT 'pending'
                   CHECK(status IN ('pending','in_progress','fulfilled','rejected','extended')),
  requested_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  deadline_at    TEXT    NOT NULL,   -- requested_at + 14 days
  extended_until TEXT,              -- optional: up to +14 more days
  fulfilled_at   TEXT,
  rejection_reason TEXT,
  notes          TEXT
);

CREATE INDEX IF NOT EXISTS idx_dsr_user ON data_subject_requests(user_id, status);
CREATE INDEX IF NOT EXISTS idx_dsr_deadline ON data_subject_requests(deadline_at, status);

CREATE TABLE IF NOT EXISTS dpo_registry (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  email        TEXT NOT NULL,
  appointed_at TEXT NOT NULL DEFAULT (datetime('now')),
  active       INTEGER NOT NULL DEFAULT 1
);
```

## Data Subject Rights Worker

```typescript
// workers/pdp-rights.ts
import { Env } from './types';

type DSRType = 'access' | 'correction' | 'deletion' | 'portability' | 'restriction';

function addDays(date: Date, days: number): string {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const method = request.method;

    if (method === 'POST' && url.pathname === '/dsr/submit') {
      return handleSubmit(request, env);
    }
    if (method === 'GET' && url.pathname === '/dsr/status') {
      return handleStatus(request, env);
    }
    if (method === 'POST' && url.pathname === '/dsr/fulfill') {
      return handleFulfill(request, env);
    }
    if (method === 'POST' && url.pathname === '/dsr/portability') {
      return handlePortability(request, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleSubmit(request: Request, env: Env): Promise<Response> {
  const { userId, type, notes } = await request.json<{
    userId: string;
    type: DSRType;
    notes?: string;
  }>();

  if (!userId || !type) {
    return new Response(JSON.stringify({ error: 'userId and type required' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const now = new Date();
  const deadlineAt = addDays(now, 14); // UU PDP Article 14: 14 days

  const ins = await env.DB.prepare(
    `INSERT INTO data_subject_requests (user_id, type, deadline_at, notes)
     VALUES (?, ?, ?, ?)`
  ).bind(userId, type, deadlineAt, notes ?? null).run();

  return new Response(JSON.stringify({
    requestId: ins.meta.last_row_id,
    deadline_at: deadlineAt,
    law: 'UU PDP 2022 Article 14',
  }), { status: 201, headers: { 'Content-Type': 'application/json' } });
}

async function handleStatus(request: Request, env: Env): Promise<Response> {
  const userId = new URL(request.url).searchParams.get('userId');
  if (!userId) return new Response('userId required', { status: 400 });

  const { results } = await env.DB.prepare(
    `SELECT id, type, status, requested_at, deadline_at, fulfilled_at
     FROM data_subject_requests WHERE user_id = ?
     ORDER BY requested_at DESC`
  ).bind(userId).all();

  return new Response(JSON.stringify({ requests: results }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  });
}

async function handleFulfill(request: Request, env: Env): Promise<Response> {
  const { requestId } = await request.json<{ requestId: number }>();

  await env.DB.prepare(
    `UPDATE data_subject_requests
     SET status = 'fulfilled', fulfilled_at = datetime('now')
     WHERE id = ? AND status IN ('pending','in_progress')`
  ).bind(requestId).run();

  return new Response(JSON.stringify({ fulfilled: true }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  });
}

async function handlePortability(request: Request, env: Env): Promise<Response> {
  const { userId } = await request.json<{ userId: string }>();

  // Gather all personal data held — portability right (Article 10 UU PDP)
  const [profile, dsrs, consents] = await Promise.all([
    env.DB.prepare('SELECT id, email_enc, created_at FROM users WHERE id = ?').bind(userId).first(),
    env.DB.prepare('SELECT * FROM data_subject_requests WHERE user_id = ?').bind(userId).all(),
    env.DB.prepare('SELECT * FROM consent_records WHERE user_id = ?').bind(userId).all(),
  ]);

  return new Response(JSON.stringify({
    format: 'JSON',
    law: 'UU PDP 2022 Article 10',
    data: { profile, data_subject_requests: dsrs.results, consents: consents.results },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
```

## Cron Alert — 14-Day Deadline Approaching

```typescript
// workers/pdp-deadline-alert.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Find DSRs due within next 2 days and still pending
    const { results } = await env.DB.prepare(
      `SELECT id, user_id, type, deadline_at
       FROM data_subject_requests
       WHERE status IN ('pending','in_progress')
         AND deadline_at <= datetime('now', '+2 days')`
    ).all();

    if (results.length === 0) return;

    await fetch(env.SLACK_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: `UU PDP: ${results.length} data subject request(s) due within 2 days:\n` +
          results.map((r: any) => `• #${r.id} ${r.type} (${r.user_id}) — due ${r.deadline_at}`).join('\n'),
      }),
    });
  },
};
```

## DPO Appointment Check

```typescript
// Run at startup / health-check endpoint
export async function checkDPOAppointed(env: Env): Promise<boolean> {
  const dpo = await env.DB.prepare(
    'SELECT id FROM dpo_registry WHERE active = 1 LIMIT 1'
  ).first();
  if (!dpo) {
    console.error('UU PDP Article 21: No active DPO registered — required for sensitive data processing');
    return false;
  }
  return true;
}
```

## Cross-Border Transfer Restriction

UU PDP Article 34-36: transfers to countries without equivalent protection require Ministerial approval or standard contractual clauses. Log all cross-border transfers.

```sql
CREATE TABLE IF NOT EXISTS cross_border_transfers (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  destination_country TEXT NOT NULL,
  data_categories TEXT NOT NULL,  -- JSON array
  legal_basis     TEXT NOT NULL,  -- 'adequacy' | 'scc' | 'bcr' | 'consent'
  transferred_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Anti-patterns

- Failing to respond within 14 days — no extensions granted without prior notice to data subject.
- Not appointing a DPO when processing health, biometric, or children's data — criminal liability for controllers.
- Transferring personal data to non-adequate countries without standard contractual clauses.
- Treating UU PDP as an internal policy document — it is enforceable law with criminal penalties.

## Gotchas

- Unlike GDPR, UU PDP imposes **criminal penalties** directly on individuals (directors, DPOs) in addition to organisations.
- Indonesia's list of "adequate" countries is not yet published; assume SCCs are required for all cross-border transfers until official guidance issues.
- The 14-day deadline runs from **receipt** of the request, not from verification of identity; verify identity as fast as possible to avoid consuming the window.
- UU PDP's implementing regulations (Peraturan Pemerintah) were pending as of mid-2024; monitor BSSN/Kominfo guidance for updates.

## Verification

```bash
# Check pending DSRs approaching deadline
wrangler d1 execute example project-db --command \
  "SELECT id, type, user_id, deadline_at FROM data_subject_requests \
   WHERE status = 'pending' AND deadline_at <= datetime('now', '+3 days');"

# Confirm DPO registration
wrangler d1 execute example project-db --command \
  "SELECT * FROM dpo_registry WHERE active = 1;"

# Test portability endpoint
curl -X POST https://privacy.example.com/dsr/portability \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u_001"}'
```

## Related

- `documentation/categories/compliance/south-korea-pipa-workers-d1-consent.md`
- `documentation/categories/compliance/hong-kong-pdpo-workers-d1.md`
- `documentation/categories/compliance/australia-privacy-act-workers-d1.md`

## Sources

- UU PDP 2022 (Undang-Undang No. 27/2022): https://jdih.kominfo.go.id/
- BSSN Personal Data Protection: https://bssn.go.id/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1: https://developers.cloudflare.com/d1/
