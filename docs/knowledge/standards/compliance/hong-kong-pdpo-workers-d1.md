# Hong Kong PDPO Compliance with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your service collects or holds personal data of Hong Kong residents. You need to comply with the Personal Data (Privacy) Ordinance (PDPO, Cap. 486) enforced by the Privacy Commissioner for Personal Data (PCPD), including: handling Data Access Requests (DARs) within 40 days, maintaining data accuracy (DPP 2), applying security controls (DPP 4), and notifying the PCPD of data breaches per the 2021 amendments.

## Context

The PDPO (1995, substantially amended 2012 and 2021) enshrines six Data Protection Principles (DPPs):

| DPP | Topic |
|-----|-------|
| 1   | Purpose and manner of collection |
| 2   | Accuracy and retention |
| 3   | Use of personal data |
| 4   | Security of personal data |
| 5   | Information to be generally available |
| 6   | Access to and correction of personal data |

The 2021 Amendment Ordinance (Anti-doxxing) expanded criminal liability for doxxing and gave the PCPD new investigation and enforcement powers. Data breach notification remains voluntary in law but the PCPD's 2023 Guidance strongly recommends prompt notification. Fines: up to HKD 1 million + imprisonment for repeat offenders.

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS dar_requests (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL,
  requested_at TEXT NOT NULL DEFAULT (datetime('now')),
  deadline_at  TEXT NOT NULL,   -- 40 calendar days per PDPO s.20
  fulfilled_at TEXT,
  status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK(status IN ('pending','fulfilled','rejected','extended'))
);

CREATE INDEX IF NOT EXISTS idx_dar_deadline ON dar_requests(deadline_at, status);

CREATE TABLE IF NOT EXISTS pcpd_breach_notifications (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  description  TEXT NOT NULL,
  affected_count INTEGER NOT NULL DEFAULT 0,
  data_categories TEXT NOT NULL,  -- JSON array
  discovered_at TEXT NOT NULL,
  notified_pcpd_at TEXT,
  reference    TEXT               -- PCPD case reference number
);

CREATE TABLE IF NOT EXISTS data_corrections (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       TEXT NOT NULL,
  field_name    TEXT NOT NULL,
  old_value_enc TEXT,             -- encrypted previous value
  new_value_enc TEXT,             -- encrypted new value
  corrected_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## DPP 6 — Data Access Request Handler (40-Day Window)

```typescript
// workers/pdpo-dar.ts
import { Env } from './types';

const DAR_DEADLINE_DAYS = 40; // PDPO s.20(2)

function addDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/dar/submit') {
      return handleDARSubmit(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/dar/data') {
      return handleDARData(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/dar/correct') {
      return handleCorrection(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/breach/notify') {
      return handleBreachNotify(request, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleDARSubmit(request: Request, env: Env): Promise<Response> {
  const { userId } = await request.json<{ userId: string }>();
  if (!userId) {
    return new Response(JSON.stringify({ error: 'userId required' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const deadlineAt = addDays(DAR_DEADLINE_DAYS);

  const ins = await env.DB.prepare(
    `INSERT INTO dar_requests (user_id, deadline_at) VALUES (?, ?)`
  ).bind(userId, deadlineAt).run();

  return new Response(JSON.stringify({
    requestId: ins.meta.last_row_id,
    deadline_at: deadlineAt,
    law: 'PDPO Cap. 486 s.20 — 40-day response window',
  }), { status: 201, headers: { 'Content-Type': 'application/json' } });
}

async function handleDARData(request: Request, env: Env): Promise<Response> {
  const userId = new URL(request.url).searchParams.get('userId');
  if (!userId) return new Response('userId required', { status: 400 });

  // Retrieve all personal data held — DPP 6(1)(a)
  const [profile, corrections, consents, activityLogs] = await Promise.all([
    env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(userId).first(),
    env.DB.prepare(
      'SELECT field_name, corrected_at FROM data_corrections WHERE user_id = ? ORDER BY corrected_at DESC'
    ).bind(userId).all(),
    env.DB.prepare(
      'SELECT purpose, collected_at, withdrawn_at FROM consent_records WHERE user_id = ?'
    ).bind(userId).all(),
    env.DB.prepare(
      'SELECT action, occurred_at FROM audit_log WHERE user_id = ? ORDER BY occurred_at DESC LIMIT 500'
    ).bind(userId).all(),
  ]);

  if (!profile) {
    return new Response(JSON.stringify({ error: 'Data subject not found' }), {
      status: 404, headers: { 'Content-Type': 'application/json' },
    });
  }

  // Mark DAR fulfilled
  await env.DB.prepare(
    `UPDATE dar_requests SET status = 'fulfilled', fulfilled_at = datetime('now')
     WHERE user_id = ? AND status = 'pending'`
  ).bind(userId).run();

  return new Response(JSON.stringify({
    held_by: 'example.com',
    pdpo_reference: 'DPP 6 Cap. 486',
    personal_data: {
      profile,
      correction_history: corrections.results,
      consents: consents.results,
      activity: activityLogs.results,
    },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

// DPP 2 — Accuracy obligations: update endpoint
async function handleCorrection(request: Request, env: Env): Promise<Response> {
  const { userId, fieldName, newValueEnc, oldValueEnc } = await request.json<{
    userId: string;
    fieldName: string;
    newValueEnc: string;
    oldValueEnc?: string;
  }>();

  // Record correction for audit trail (DPP 2)
  await env.DB.prepare(
    `INSERT INTO data_corrections (user_id, field_name, old_value_enc, new_value_enc)
     VALUES (?, ?, ?, ?)`
  ).bind(userId, fieldName, oldValueEnc ?? null, newValueEnc).run();

  // Apply the update (field must be a known column)
  const allowed = ['email_enc', 'name_enc'];
  if (!allowed.includes(fieldName)) {
    return new Response(JSON.stringify({ error: 'Field not updatable' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  await env.DB.prepare(
    `UPDATE users SET ${fieldName} = ? WHERE id = ?`
  ).bind(newValueEnc, userId).run();

  return new Response(JSON.stringify({ corrected: true, field: fieldName }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  });
}

// PCPD Breach Notification (strongly recommended per 2023 PCPD Guidance)
async function handleBreachNotify(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{
    description: string;
    affectedCount: number;
    dataCategories: string[];
    discoveredAt: string;
  }>();

  const ins = await env.DB.prepare(
    `INSERT INTO pcpd_breach_notifications
       (description, affected_count, data_categories, discovered_at)
     VALUES (?, ?, ?, ?)`
  ).bind(
    body.description,
    body.affectedCount,
    JSON.stringify(body.dataCategories),
    body.discoveredAt
  ).run();

  const notificationId = ins.meta.last_row_id;

  // Notify PCPD via their online breach notification platform
  // https://www.pcpd.org.hk/english/infocentre/breach_notification.html
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `PDPO Breach #${notificationId}: ${body.description}. Submit to PCPD breach portal and notify DPO.`,
    }),
  });

  return new Response(JSON.stringify({
    notificationId,
    next_step: 'Submit to PCPD breach notification platform within 2 business days per 2023 Guidance',
  }), { status: 201, headers: { 'Content-Type': 'application/json' } });
}
```

## DPP 4 — Security: Encryption at Rest Notes for D1

DPP 4 requires all practicable steps to protect personal data from unauthorised or accidental access, processing, erasure, loss, or use. For D1:

- Cloudflare encrypts D1 data at rest with AES-256; this satisfies the baseline DPP 4 infrastructure requirement.
- Add application-layer encryption (AES-GCM via Web Crypto) for sensitive fields — see `australia-privacy-act-workers-d1.md` `encryptField` helper.
- Enable Cloudflare Access or mTLS on Worker routes serving DAR data.
- Log all access to personal data in `audit_log` (action, user_id, occurred_at).

## Anti-patterns

- Responding to DARs after the 40-day statutory deadline without extension — constitutes a breach of DPP 6.
- Storing the PCPD breach notification reference externally but not linking it in D1 — creates audit gap.
- Accepting correction requests without an allowlist check on `fieldName` — opens SQL injection via column name interpolation.
- Treating the PCPD's breach notification guidance as optional because it is not yet mandatory by statute — PCPD enforcement action can follow failure to notify.

## Gotchas

- The PDPO does **not** currently impose a statutory mandatory breach notification timeline; the 2023 PCPD Guidance recommends notification within **2 business days** of becoming aware — treat this as a de-facto requirement.
- Data users must provide personal data in a **form that the data subject can read** — do not return raw encrypted blobs in DAR responses; decrypt before returning.
- DPP 3 restricts use of personal data to the purpose notified at collection; re-use for new purposes requires fresh consent.
- PCPD can order data users to cease processing and impose fines without going to court under the 2021 amendments.

## Verification

```bash
# Check pending DARs approaching deadline
wrangler d1 execute example project-db --command \
  "SELECT id, user_id, deadline_at FROM dar_requests \
   WHERE status = 'pending' AND deadline_at <= datetime('now', '+5 days');"

# Test DAR submission
curl -X POST https://privacy.example.com/dar/submit \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u_001"}'

# Retrieve all data for a user (simulate DAR fulfillment)
curl 'https://privacy.example.com/dar/data?userId=u_001'

# Confirm correction audit trail
wrangler d1 execute example project-db --command \
  "SELECT * FROM data_corrections ORDER BY corrected_at DESC LIMIT 5;"
```

## Related

- `documentation/docs/policies/compliance/australia-privacy-act-workers-d1.md`
- `documentation/docs/policies/compliance/canada-pipeda-workers-d1-breach.md`
- `documentation/docs/policies/compliance/south-korea-pipa-workers-d1-consent.md`
- `documentation/docs/policies/compliance/indonesia-pdp-law-workers-d1.md`

## Sources

- PDPO Cap. 486: https://www.elegislation.gov.hk/hk/cap486
- PCPD official site: https://www.pcpd.org.hk/
- PCPD Data Breach Guidance (2023): https://www.pcpd.org.hk/english/infocentre/breach_notification.html
- PDPO 2021 Amendment (Anti-doxxing): https://www.pcpd.org.hk/english/data_privacy_law/ordinance_at_a_Glance/overview.html
- Cloudflare D1 security: https://developers.cloudflare.com/d1/
