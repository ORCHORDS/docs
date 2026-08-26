# Turkey KVKK — Cloudflare Workers & D1 Personal Data Processing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers-based application processes personal data of Turkish residents and must comply with Law No. 6698 on Protection of Personal Data (KVKK). You need to register as a data controller with the VERBIS authority, implement explicit consent collection stored in D1, build a data subject rights endpoint, and set up 72-hour breach notification to the Personal Data Protection Authority (KVKK Board).

## Context

KVKK, enacted in 2016 and closely modelled on the pre-GDPR EU Directive 95/46/EC, applies to data controllers that process personal data of Turkish residents whether the controller is domiciled in Turkey or abroad. Data controllers with employees or operating in Turkey must register with VERBIS (Veri Sorumluları Sicili Bilgi Sistemi). Cross-border transfer requires either the destination country to appear on the Turkish adequacy list, or the use of binding corporate rules / undertakings approved by the KVKK Board. Unlike GDPR, KVKK still treats consent as a primary lawful basis for most processing; legitimate interest is not enumerated in the same way.

## D1 Schema: consent_log and data_subject_requests

```typescript
// migrations/0001_kvkk.sql
export const KVKK_SCHEMA = `
CREATE TABLE IF NOT EXISTS consent_log (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id   TEXT NOT NULL,
  purpose      TEXT NOT NULL,
  legal_basis  TEXT NOT NULL DEFAULT 'explicit_consent',
  granted_at   TEXT NOT NULL DEFAULT (datetime('now')),
  withdrawn_at TEXT,
  ip_hash      TEXT,
  user_agent   TEXT
);

CREATE INDEX IF NOT EXISTS idx_consent_subject ON consent_log(subject_id);

CREATE TABLE IF NOT EXISTS kvkk_dsr (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id   TEXT NOT NULL,
  request_type TEXT NOT NULL CHECK(request_type IN ('access','deletion','objection','rectification','restriction')),
  channel      TEXT NOT NULL DEFAULT 'api',
  status       TEXT NOT NULL DEFAULT 'pending',
  received_at  TEXT NOT NULL DEFAULT (datetime('now')),
  deadline_at  TEXT NOT NULL,
  resolved_at  TEXT,
  response_notes TEXT
);

CREATE TABLE IF NOT EXISTS breach_log (
  id               TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  detected_at      TEXT NOT NULL DEFAULT (datetime('now')),
  kvkk_notify_deadline TEXT NOT NULL,
  notified_at      TEXT,
  severity         TEXT NOT NULL,
  description      TEXT NOT NULL,
  affected_records INTEGER
);
`;
```

## Workers API: Consent Collection and VERBIS Data Controller Registration

```typescript
// src/kvkk-consent.ts
import { Env } from './types';

export async function handleConsent(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === 'POST' && url.pathname === '/privacy/consent') {
    return grantConsent(request, env);
  }
  if (request.method === 'DELETE' && url.pathname.startsWith('/privacy/consent/')) {
    const subjectId = url.pathname.split('/').pop()!;
    return withdrawConsent(subjectId, env);
  }
  return new Response('Not found', { status: 404 });
}

async function grantConsent(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ subject_id: string; purpose: string }>();
  const ipHash = await hashIp(request.headers.get('CF-Connecting-IP') ?? '');
  const ua = request.headers.get('User-Agent') ?? '';

  await env.DB.prepare(
    `INSERT INTO consent_log (subject_id, purpose, ip_hash, user_agent) VALUES (?, ?, ?, ?)`
  )
    .bind(body.subject_id, body.purpose, ipHash, ua.substring(0, 255))
    .run();

  return new Response(JSON.stringify({ status: 'consent_recorded' }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function withdrawConsent(subjectId: string, env: Env): Promise<void | Response> {
  await env.DB.prepare(
    `UPDATE consent_log SET withdrawn_at = datetime('now') WHERE subject_id = ? AND withdrawn_at IS NULL`
  )
    .bind(subjectId)
    .run();
  return new Response(JSON.stringify({ status: 'consent_withdrawn' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(ip));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Data Subject Rights Endpoint (/gdpr/request)

```typescript
// src/kvkk-dsr.ts
const KVKK_RESPONSE_DAYS = 30; // KVKK Art. 13: respond within 30 days

export async function handleDSR(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

  const body = await request.json<{
    subject_id: string;
    request_type: 'access' | 'deletion' | 'objection' | 'rectification' | 'restriction';
    channel?: string;
  }>();

  const deadline = new Date();
  deadline.setDate(deadline.getDate() + KVKK_RESPONSE_DAYS);

  const result = await env.DB.prepare(
    `INSERT INTO kvkk_dsr (subject_id, request_type, channel, deadline_at)
     VALUES (?, ?, ?, ?) RETURNING id`
  )
    .bind(body.subject_id, body.request_type, body.channel ?? 'api', deadline.toISOString())
    .first<{ id: string }>();

  // Notify DPO team
  await fetch(env.DPO_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dsr_id: result?.id, type: body.request_type, deadline: deadline.toISOString() }),
  });

  return new Response(JSON.stringify({ request_id: result?.id, deadline: deadline.toISOString() }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## 72-Hour Breach Notification to KVKK Board

```typescript
// src/kvkk-breach.ts
export async function recordBreach(
  env: Env,
  description: string,
  severity: 'low' | 'medium' | 'high' | 'critical',
  affectedRecords: number
): Promise<string> {
  const notifyDeadline = new Date(Date.now() + 72 * 3600 * 1000).toISOString();

  const result = await env.DB.prepare(
    `INSERT INTO breach_log (description, severity, affected_records, kvkk_notify_deadline)
     VALUES (?, ?, ?, ?) RETURNING id`
  )
    .bind(description, severity, affectedRecords, notifyDeadline)
    .first<{ id: string }>();

  if (['high', 'critical'].includes(severity)) {
    await fetch(env.KVKK_ALERT_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        breach_id: result?.id,
        kvkk_notify_deadline: notifyDeadline,
        severity,
        affected_records: affectedRecords,
      }),
    });
  }
  return result?.id ?? '';
}
```

## Cross-Border Transfer: Turkey Adequacy List vs BCRs

Turkey does not have a formal adequacy decision from the EU, and Turkey's own adequacy list (published by KVKK Board) is separate. For transfers to countries not on the Turkish adequacy list:

- Execute binding corporate rules (BCRs) approved by the KVKK Board, or
- Obtain an undertaking approved by the Board, or
- Rely on one of KVKK Art. 9 exceptions (explicit consent, vital interests, public task).

KVKK has not issued SCCs equivalent to EU SCCs; BCRs or undertakings are the primary mechanism for routine transfers.

## Anti-patterns

- **Relying on GDPR SCCs for Turkey transfers** — KVKK does not recognise EU SCCs; a separate Turkish Board-approved undertaking is required.
- **Skipping VERBIS registration** — Data controllers processing personal data of Turkish residents are required to register; non-registration can result in administrative fines up to TRY 1,964,456 (2024 threshold).
- **Treating consent withdrawal as account deletion** — KVKK allows continued processing under another lawful basis (e.g. statutory obligation) after consent withdrawal; log the withdrawal but evaluate continued processing grounds.

## Gotchas

- KVKK Board can extend the 30-day DSR response window by another 30 days in complex cases, but must notify the data subject of the extension within the first 30 days.
- The 72-hour breach notification clock runs from the moment the controller becomes aware, not when the breach occurred.
- VERBIS registration must be renewed annually and updated whenever data processing activities change materially.

## Verification

```bash
# Check overdue DSRs (past 30-day deadline)
wrangler d1 execute example project-db --command \
  "SELECT id, subject_id, request_type, deadline_at FROM kvkk_dsr WHERE status = 'pending' AND deadline_at < datetime('now');"

# Audit active consents for a subject
wrangler d1 execute example project-db --command \
  "SELECT purpose, granted_at FROM consent_log WHERE subject_id = 'sub_123' AND withdrawn_at IS NULL;"

# Check breach notification deadlines
wrangler d1 execute example project-db --command \
  "SELECT id, severity, kvkk_notify_deadline FROM breach_log WHERE notified_at IS NULL AND kvkk_notify_deadline <= datetime('now','+6 hours');"
```

## Related

- `philippines-dpa-2012-workers-d1-data-subject-rights.md`
- `saudi-arabia-pdpl-workers-d1-consent-management.md`
- `argentina-pdpa-workers-d1-data-protection.md`

## Sources

- KVKK Law No. 6698 (Official Gazette) — https://www.kvkk.gov.tr/Icerik/6649/6698-SAYILI-KANUN
- VERBIS Registration Portal — https://verbis.kvkk.gov.tr
- KVKK Board Decisions Database — https://www.kvkk.gov.tr/Icerik/5642/Kararlar
- KVKK Cross-Border Transfer Guidelines — https://www.kvkk.gov.tr/Icerik/6742/Yurt-Disina-Aktarim
