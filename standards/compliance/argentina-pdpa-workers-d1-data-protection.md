# Argentina PDPA (Law 25,326) — Cloudflare Workers & D1 Data Protection

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers application processes personal data of Argentine residents and must comply with Law 25,326 (Personal Data Protection Act / PDPA, known locally as Ley de Protección de Datos Personales). You need to register databases with AAIP (Agencia de Acceso a la Información Pública), implement habeas data rights (access, rectification, deletion, confidentiality) with a 30-day response deadline tracked in D1, enforce onward transfer restrictions, and apply the PDPA's security measures requirement across your Workers stack.

## Context

Argentina's Law 25,326 has been in force since 2000 and was among the first Latin American data protection laws to gain EU adequacy status (Commission Decision 2003/490/EC). AAIP acts as the supervisory authority and maintains the National Personal Data Protection Directorate (DNPDP) register of personal data databases. Every data file, register, database, or data bank containing personal information — including cloud databases like D1 — must be registered with AAIP. Habeas data is a constitutional right in Argentina (Art. 43 of the Constitution), giving individuals enforceable rights to access, correct, update, delete, or classify their personal data. Controllers have 30 calendar days to respond to habeas data requests. Law 25,326 distinguishes between sensitive data (racial origin, political opinions, religious beliefs, union membership, health/sex life) which may not be created without law authorisation, and ordinary personal data.

## D1 Schema: requests and data_inventory

```typescript
// migrations/0001_argentina_pdpa.sql
export const PDPA_SCHEMA = `
CREATE TABLE IF NOT EXISTS pdpa_requests (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  subject_id  TEXT NOT NULL,
  type        TEXT NOT NULL CHECK(type IN ('access','rectification','deletion','confidentiality','objection')),
  status      TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','in_review','completed','denied')),
  received_at TEXT NOT NULL DEFAULT (datetime('now')),
  deadline_at TEXT NOT NULL,    -- 30 calendar days from received_at
  resolved_at TEXT,
  denial_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_pdpa_requests_deadline ON pdpa_requests(deadline_at, status);

CREATE TABLE IF NOT EXISTS aaip_database_registry (
  id               TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  database_name    TEXT NOT NULL UNIQUE,
  aaip_reg_number  TEXT,           -- Registration number from AAIP
  registered_at    TEXT,
  purpose          TEXT NOT NULL,
  sensitivity      TEXT NOT NULL CHECK(sensitivity IN ('ordinary','sensitive')),
  owner_name       TEXT NOT NULL,
  owner_cuit       TEXT NOT NULL,
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transfer_log (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  destination_country TEXT NOT NULL,
  legal_basis     TEXT NOT NULL CHECK(legal_basis IN ('adequacy','consent','contractual','vital_interest')),
  data_categories TEXT NOT NULL,
  transferred_at  TEXT NOT NULL DEFAULT (datetime('now')),
  volume_estimate INTEGER
);
`;
```

## Workers API: Habeas Data Rights Endpoint

```typescript
// src/pdpa-habeas.ts
import { Env } from './types';

const PDPA_DEADLINE_DAYS = 30;

export async function handleHabeasData(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === 'POST' && url.pathname === '/habeas-data/request') {
    return createRequest(request, env);
  }
  if (request.method === 'GET' && url.pathname.startsWith('/habeas-data/request/')) {
    const id = url.pathname.split('/').pop()!;
    return getRequest(id, env);
  }
  if (request.method === 'PATCH' && url.pathname.startsWith('/habeas-data/request/')) {
    const id = url.pathname.split('/').pop()!;
    return updateRequest(id, request, env);
  }
  return new Response('Not found', { status: 404 });
}

async function createRequest(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{
    subject_id: string;
    type: 'access' | 'rectification' | 'deletion' | 'confidentiality' | 'objection';
  }>();

  const deadline = new Date();
  deadline.setDate(deadline.getDate() + PDPA_DEADLINE_DAYS);

  const result = await env.DB.prepare(
    `INSERT INTO pdpa_requests (subject_id, type, deadline_at) VALUES (?, ?, ?) RETURNING id`
  )
    .bind(body.subject_id, body.type, deadline.toISOString())
    .first<{ id: string }>();

  // Alert internal team
  await fetch(env.DPO_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request_id: result?.id, type: body.type, deadline: deadline.toISOString() }),
  });

  return new Response(JSON.stringify({ id: result?.id, deadline: deadline.toISOString() }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function getRequest(id: string, env: Env): Promise<Response> {
  const row = await env.DB.prepare(
    `SELECT id, subject_id, type, status, received_at, deadline_at, resolved_at FROM pdpa_requests WHERE id = ?`
  )
    .bind(id)
    .first();
  if (!row) return new Response('Not found', { status: 404 });
  return new Response(JSON.stringify(row), { headers: { 'Content-Type': 'application/json' } });
}

async function updateRequest(
  id: string,
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{ status: string; denial_reason?: string }>();
  await env.DB.prepare(
    `UPDATE pdpa_requests SET status = ?, resolved_at = datetime('now'), denial_reason = ? WHERE id = ?`
  )
    .bind(body.status, body.denial_reason ?? null, id)
    .run();
  return new Response(JSON.stringify({ updated: true }), { headers: { 'Content-Type': 'application/json' } });
}
```

## Cron Worker: 30-Day Deadline Alert

```typescript
// src/pdpa-cron.ts
// wrangler.toml: [triggers] crons = ["0 9 * * *"]

export async function handleScheduled(env: Env): Promise<void> {
  // Alert for requests approaching or past their 30-day deadline
  const alertWindow = new Date();
  alertWindow.setDate(alertWindow.getDate() + 3); // alert 3 days before deadline

  const approaching = await env.DB.prepare(
    `SELECT id, subject_id, type, deadline_at
     FROM pdpa_requests
     WHERE status IN ('pending', 'in_review')
     AND deadline_at <= ?
     ORDER BY deadline_at ASC`
  )
    .bind(alertWindow.toISOString())
    .all();

  if (approaching.results.length > 0) {
    await fetch(env.DPO_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alert: 'PDPA_DEADLINE_APPROACHING',
        count: approaching.results.length,
        requests: approaching.results,
      }),
    });
  }

  // Separately flag overdue requests
  const overdue = await env.DB.prepare(
    `SELECT id, subject_id, type, deadline_at FROM pdpa_requests
     WHERE status IN ('pending','in_review') AND deadline_at < datetime('now')`
  )
    .all();

  if (overdue.results.length > 0) {
    await fetch(env.ESCALATION_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert: 'PDPA_OVERDUE', overdue: overdue.results }),
    });
  }
}
```

## Security Measures Requirement: Workers Stack Mapping

Law 25,326 Art. 9 requires technical and organisational security measures appropriate to the risks of processing. Map these to your Workers stack:

| PDPA Requirement | Workers Implementation |
|---|---|
| HTTPS-only transmission | Workers enforce TLS; disable HTTP via `workers.dev` HTTPS redirect |
| Access controls | KV allowlist for internal API keys; `X-Internal-Key` header validation |
| Audit logging | Write access events to D1 `audit_log` table with timestamp and actor |
| Encryption at rest | D1 encryption-at-rest is enabled by default on Cloudflare infrastructure |
| Pseudonymisation | Hash PII fields (email, IP) before storage using `crypto.subtle.digest` |
| Data minimisation | Store only fields required for declared purpose in `aaip_database_registry` |

## Onward Transfer to Third Countries

Argentina's AAIP maintains a list of countries with adequate data protection. Currently includes EU/EEA countries, UK, Israel, New Zealand, Switzerland, Uruguay, and others. For transfers to non-adequate countries:

- Obtain explicit consent of the data subject specifically for the international transfer, or
- Execute contractual clauses approved by AAIP, or
- Invoke an Art. 12 exception (vital interest, legal claim, public interest).

Record all outbound transfers in `transfer_log` with the legal basis.

## Anti-patterns

- **Creating a database of sensitive data without legal authorisation** — PDPA Art. 7 prohibits creating files or databases of sensitive personal data (health, religion, political opinion, etc.) without specific legal grounds; attempting to do so exposes the controller to AAIP fines.
- **Failing to register D1 databases with AAIP** — Cloud databases are subject to AAIP registration; many controllers incorrectly assume cloud SaaS is exempt.
- **Treating the 30-day deadline as a soft guideline** — AAIP enforcement actions have cited deadline violations; implement the Cron Worker alert from day one.

## Gotchas

- AAIP registration must be renewed whenever the purpose, structure, or ownership of the database changes materially.
- Argentina's adequacy under EU law (Commission Decision 2003/490/EC) applies to transfers FROM the EU TO Argentina; it does not govern transfers in the other direction.
- The "confidentiality" habeas data right (clasificación) allows subjects to request that their data be treated as confidential from third parties — this is distinct from erasure and must be tracked separately.

## Verification

```bash
# Check AAIP registration status
wrangler d1 execute example project-db --command \
  "SELECT database_name, aaip_reg_number, registered_at FROM aaip_database_registry;"

# Alert on approaching deadlines
wrangler d1 execute example project-db --command \
  "SELECT id, type, deadline_at FROM pdpa_requests WHERE status IN ('pending','in_review') AND deadline_at <= datetime('now','+3 days');"

# Audit transfer log for non-adequate destinations
wrangler d1 execute example project-db --command \
  "SELECT destination_country, legal_basis, transferred_at FROM transfer_log WHERE legal_basis != 'adequacy' ORDER BY transferred_at DESC LIMIT 20;"

# Verify HTTPS enforcement in wrangler.toml (no plain HTTP routes)
grep -E 'http[^s]' wrangler.toml || echo 'No plain HTTP routes found — OK'
```

## Related

- `philippines-dpa-2012-workers-d1-data-subject-rights.md`
- `turkey-kvkk-workers-d1-personal-data-processing.md`
- `saudi-arabia-pdpl-workers-d1-consent-management.md`

## Sources

- Law 25,326 Full Text — https://servicios.infoleg.gob.ar/infolegInternet/anexos/60000-64999/64790/texact.htm
- AAIP Database Registration — https://www.argentina.gob.ar/aaip/datospersonales/registrodebasesdedatos
- AAIP Official Site — https://www.argentina.gob.ar/aaip
- EU Adequacy Decision for Argentina — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32003D0490
- AAIP Habeas Data Guide — https://www.argentina.gob.ar/aaip/datospersonales/ejercerderechos
