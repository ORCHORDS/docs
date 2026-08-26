# Saudi Arabia PDPL — Cloudflare Workers & D1 Consent Management

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers application processes personal data of Saudi Arabian residents and must comply with the Personal Data Protection Law (PDPL, Royal Decree M/19 of 1443H / 2021). You need to geo-detect Saudi users, implement explicit opt-in consent with D1 storage, handle data localisation for sensitive personal data, and manage cross-border transfer authorisation via SDAIA (Saudi Data and AI Authority).

## Context

Saudi Arabia's PDPL took effect 14 September 2023 (after a two-year grace period). SDAIA serves as the primary supervisory authority during the initial period, with oversight eventually transitioning to the National Data Management Office (NDMO). Consent is the dominant lawful basis under PDPL; legitimate interest as a standalone basis is much narrower than under GDPR and requires advance regulatory approval in most cases. Sensitive personal data — health, genetic, biometric, criminal record, financial, location revealing private matters, and data revealing racial, ethnic, religious, or political opinions — must be stored within the Kingdom of Saudi Arabia (KSA) and cannot be transferred abroad without SDAIA authorisation. Controllers are required to appoint a Privacy Officer and publish a privacy notice in Arabic.

## Geo-Detection and Routing for Saudi Users

```typescript
// src/pdpl-router.ts
import { Env } from './types';

const SENSITIVE_PATHS = ['/health', '/finance', '/biometric', '/location'];

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  const cf = (request as any).cf as { country?: string };
  const isSaudiUser = cf?.country === 'SA';
  const url = new URL(request.url);
  const isSensitivePath = SENSITIVE_PATHS.some(p => url.pathname.startsWith(p));

  if (isSaudiUser && isSensitivePath) {
    // Sensitive personal data for SA users must stay in KSA
    return routeToKSABackend(request, env);
  }

  if (isSaudiUser) {
    // Attach PDPL consent verification header
    return handleSaudiUser(request, env);
  }

  return handleGlobalUser(request, env);
}

async function routeToKSABackend(request: Request, env: Env): Promise<Response> {
  const ksaUrl = env.KSA_BACKEND_URL + new URL(request.url).pathname;
  const proxied = new Request(ksaUrl, {
    method: request.method,
    headers: { ...Object.fromEntries(request.headers), 'X-Data-Residency': 'KSA' },
    body: request.body,
  });
  return fetch(proxied);
}

async function handleSaudiUser(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  // Check consent before any data processing
  const subjectId = request.headers.get('X-Subject-ID');
  if (subjectId) {
    const hasConsent = await verifyConsent(subjectId, url.pathname, env);
    if (!hasConsent) {
      return new Response(JSON.stringify({ error: 'PDPL consent required', redirect: '/privacy/consent' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  }
  return handleGlobalUser(request, env);
}

async function handleGlobalUser(request: Request, env: Env): Promise<Response> {
  return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } });
}

async function verifyConsent(subjectId: string, purpose: string, env: Env): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT id FROM pdpl_consent WHERE subject_id = ? AND purpose_path = ? AND withdrawn_at IS NULL LIMIT 1`
  )
    .bind(subjectId, purpose)
    .first();
  return row !== null;
}
```

## D1 Schema: Explicit Opt-In Consent Storage

```typescript
// migrations/0001_pdpl.sql
export const PDPL_SCHEMA = `
CREATE TABLE IF NOT EXISTS pdpl_consent (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id   TEXT NOT NULL,
  purpose_path TEXT NOT NULL,     -- endpoint or feature the consent covers
  purpose_desc TEXT NOT NULL,
  data_categories TEXT NOT NULL,  -- JSON array, e.g. '["name","email"]'
  is_sensitive INTEGER NOT NULL DEFAULT 0,
  granted_at   TEXT NOT NULL DEFAULT (datetime('now')),
  withdrawn_at TEXT,
  consent_version TEXT NOT NULL DEFAULT '1.0',
  ip_hash      TEXT,
  language     TEXT NOT NULL DEFAULT 'ar'  -- PDPL privacy notices must be in Arabic
);

CREATE INDEX IF NOT EXISTS idx_pdpl_consent_subject ON pdpl_consent(subject_id, withdrawn_at);

CREATE TABLE IF NOT EXISTS pdpl_dsr (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id   TEXT NOT NULL,
  request_type TEXT NOT NULL CHECK(request_type IN ('access','correction','deletion','withdraw_consent','objection')),
  status       TEXT NOT NULL DEFAULT 'pending',
  received_at  TEXT NOT NULL DEFAULT (datetime('now')),
  deadline_at  TEXT NOT NULL,    -- PDPL: respond within 30 days
  resolved_at  TEXT
);

CREATE TABLE IF NOT EXISTS pdpl_cross_border_transfer (
  id             TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  destination    TEXT NOT NULL,
  data_categories TEXT NOT NULL,
  sdaia_auth_ref TEXT,           -- SDAIA authorisation reference number
  authorised_at  TEXT,
  expires_at     TEXT,
  status         TEXT NOT NULL DEFAULT 'pending'
);
`;
```

## Consent Endpoint and PDPL-Compliant Opt-In Form

```typescript
// src/pdpl-consent.ts
const PDPL_DSR_DEADLINE_DAYS = 30;

export async function handleConsentAPI(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === 'POST' && url.pathname === '/privacy/consent') {
    const body = await request.json<{
      subject_id: string;
      purpose_path: string;
      purpose_desc: string;
      data_categories: string[];
      is_sensitive: boolean;
      language?: string;
    }>();

    const ipHash = await hashIp(request.headers.get('CF-Connecting-IP') ?? '');
    await env.DB.prepare(
      `INSERT INTO pdpl_consent (subject_id, purpose_path, purpose_desc, data_categories, is_sensitive, ip_hash, language)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        body.subject_id,
        body.purpose_path,
        body.purpose_desc,
        JSON.stringify(body.data_categories),
        body.is_sensitive ? 1 : 0,
        ipHash,
        body.language ?? 'ar'
      )
      .run();

    return new Response(JSON.stringify({ status: 'consent_granted' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (request.method === 'POST' && url.pathname === '/privacy/request') {
    const body = await request.json<{ subject_id: string; request_type: string }>();
    const deadline = new Date();
    deadline.setDate(deadline.getDate() + PDPL_DSR_DEADLINE_DAYS);
    const result = await env.DB.prepare(
      `INSERT INTO pdpl_dsr (subject_id, request_type, deadline_at) VALUES (?, ?, ?) RETURNING id`
    )
      .bind(body.subject_id, body.request_type, deadline.toISOString())
      .first<{ id: string }>();
    return new Response(JSON.stringify({ id: result?.id, deadline: deadline.toISOString() }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  return new Response('Not found', { status: 404 });
}

async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(ip));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Cross-Border Transfer Authorisation via SDAIA

Sensitive personal data originating from SA users cannot leave KSA without:

1. SDAIA prior authorisation (submit a transfer request via ndmo.gov.sa).
2. Ensuring the destination country provides adequate protection or contractual safeguards are in place.
3. Recording the SDAIA authorisation reference number in `pdpl_cross_border_transfer.sdaia_auth_ref`.

For non-sensitive personal data, cross-border transfer is permitted if the destination meets PDPL adequacy requirements or the individual has given explicit consent to the specific transfer.

## Anti-patterns

- **Pre-ticked consent boxes** — PDPL requires unambiguous, freely given, specific, and informed consent; pre-ticked checkboxes invalidate the consent.
- **Single consent for multiple purposes** — Each distinct processing purpose requires a separate, granular consent record; bundling purposes into one tick is non-compliant.
- **Routing KSA sensitive data through Cloudflare's global network to D1** — D1 is globally distributed; sensitive personal data of SA residents must reside on KSA-resident infrastructure, not D1 global.

## Gotchas

- Privacy notices must be available in Arabic as the primary language; English supplements are optional.
- SDAIA can issue implementation regulations that augment PDPL requirements; monitor ndmo.gov.sa for updates.
- The Privacy Officer (equivalent to DPO) is mandatory for controllers processing large-scale or sensitive personal data; their contact must be published in the privacy notice.

## Verification

```bash
# Audit sensitive consents currently active for SA users
wrangler d1 execute example project-db --command \
  "SELECT subject_id, purpose_path, granted_at FROM pdpl_consent WHERE is_sensitive = 1 AND withdrawn_at IS NULL;"

# Check cross-border transfer authorisations
wrangler d1 execute example project-db --command \
  "SELECT destination, sdaia_auth_ref, expires_at FROM pdpl_cross_border_transfer WHERE status = 'approved';"

# Verify DSR queue is not overdue
wrangler d1 execute example project-db --command \
  "SELECT id, request_type, deadline_at FROM pdpl_dsr WHERE status = 'pending' AND deadline_at < datetime('now');"
```

## Related

- `china-pipl-workers-d1-cross-border-data-transfer.md`
- `turkey-kvkk-workers-d1-personal-data-processing.md`
- `argentina-pdpa-workers-d1-data-protection.md`

## Sources

- Saudi PDPL Royal Decree M/19 — https://www.ndmo.gov.sa/en/data-regulations
- SDAIA Data Regulations Portal — https://sdaia.gov.sa/en/
- NDMO Implementation Regulations — https://www.ndmo.gov.sa/en/data-regulations
- Cloudflare Workers cf.country reference — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
