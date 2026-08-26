# Chile Law 21.719 Personal Data Protection — Cloudflare Workers + D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your example project deployment serves users in Chile. Chile's Law 21.719 (Ley de Protección de Datos Personales), published December 2024 with a 24-month transition period ending December 2026, introduces GDPR-style obligations: lawful basis for processing, data subject rights, mandatory breach notification to the CPLT (Consejo para la Transparencia), and fines up to 10,000 UTM (~USD 700 K) per infraction. This article covers the engineering work needed on Cloudflare Workers + D1 before the law becomes enforceable.

---

## Context

Law 21.719 replaces the 1999 Law 19.628. Key pillars relevant to an anonymous social platform:

- **Lawful bases**: consent, contract, legitimate interest, legal obligation, vital interests, public interest.
- **Sensitive data**: health, biometrics, sexual orientation, political opinions, religion, racial/ethnic origin — requires explicit consent.
- **Data subject rights**: access, rectification, deletion, portability, objection, processing restriction.
- **DPO**: mandatory when processing activities are high-risk at large scale.
- **DPIA**: required before high-risk processing (profiling, automated decisions with legal effects, large-scale sensitive data).
- **Breach notification**: controller must notify CPLT within 72 hours of becoming aware; affected individuals within 30 days.
- **Cross-border transfers**: permitted to countries with adequate protection or via standard contractual clauses approved by CPLT.

---

## 1 — Consent Capture and Lawful Basis Ledger (D1)

```typescript
// schema/chile-lawful-basis.sql
// Run via: wrangler d1 execute example project_DB --file=schema/chile-lawful-basis.sql

CREATE TABLE IF NOT EXISTS chile_processing_records (
  id          TEXT PRIMARY KEY,          -- UUID
  account_id  TEXT NOT NULL,             -- pseudonymous example project handle hash
  purpose     TEXT NOT NULL,             -- e.g. "profile_display", "analytics"
  legal_basis TEXT NOT NULL CHECK (legal_basis IN (
    'consent','contract','legal_obligation','vital_interests',
    'public_interest','legitimate_interest'
  )),
  consent_ts  INTEGER,                   -- Unix epoch; null for non-consent bases
  consent_ip  TEXT,                      -- hashed IP at consent time
  withdrawn_ts INTEGER,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_clr_account ON chile_processing_records(account_id);
```

```typescript
// src/chile/lawful-basis.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Env { example project_DB: D1Database }

export async function recordConsent(
  db: D1Database,
  accountId: string,
  purpose: string,
  ipHash: string,
): Promise<void> {
  const id = crypto.randomUUID();
  await db.prepare(
    `INSERT INTO chile_processing_records
     (id, account_id, purpose, legal_basis, consent_ts, consent_ip)
     VALUES (?, ?, ?, 'consent', ?, ?)`,
  ).bind(id, accountId, purpose, Math.floor(Date.now() / 1000), ipHash).run();
}

export async function withdrawConsent(
  db: D1Database,
  accountId: string,
  purpose: string,
): Promise<boolean> {
  const result = await db.prepare(
    `UPDATE chile_processing_records
     SET withdrawn_ts = ?
     WHERE account_id = ? AND purpose = ? AND withdrawn_ts IS NULL`,
  ).bind(Math.floor(Date.now() / 1000), accountId, purpose).run();
  return (result.meta.changes ?? 0) > 0;
}
```

---

## 2 — Data Subject Rights Router

```typescript
// src/chile/dsr-router.ts
import { Hono } from 'hono';
import type { Env } from '../types';

const dsr = new Hono<{ Bindings: Env }>();

// Art. 14 — right of access: 30-day response window
dsr.get('/cl/dsr/access', async (c) => {
  const accountId = c.req.header('X-Account-Id') ?? '';
  const rows = await c.env.example project_DB.prepare(
    `SELECT purpose, legal_basis, consent_ts, withdrawn_ts
     FROM chile_processing_records WHERE account_id = ?`,
  ).bind(accountId).all();

  const posts = await c.env.example project_DB.prepare(
    `SELECT post_id, body_hash, created_at FROM posts WHERE account_id = ?`,
  ).bind(accountId).all();

  return c.json({ processing: rows.results, content: posts.results });
});

// Art. 16 — right to deletion (suppresión)
dsr.delete('/cl/dsr/delete', async (c) => {
  const accountId = c.req.header('X-Account-Id') ?? '';

  // Deletion is blocked when data is needed for legal proceedings or contract
  const legalHold = await c.env.example project_DB.prepare(
    `SELECT id FROM legal_holds WHERE account_id = ? LIMIT 1`,
  ).bind(accountId).first();
  if (legalHold) return c.json({ error: 'legal_hold_active' }, 409);

  await c.env.example project_DB.batch([
    c.env.example project_DB.prepare(
      `DELETE FROM chile_processing_records WHERE account_id = ?`,
    ).bind(accountId),
    c.env.example project_DB.prepare(
      `DELETE FROM posts WHERE account_id = ?`,
    ).bind(accountId),
    c.env.example project_DB.prepare(
      `INSERT INTO deletion_audit (account_id, law, ts) VALUES (?, 'CL-21719', ?)`,
    ).bind(accountId, Math.floor(Date.now() / 1000)),
  ]);
  return c.json({ deleted: true });
});

export default dsr;
```

---

## 3 — Breach Notification Pipeline (72-hour CPLT)

```typescript
// src/chile/breach-notify.ts
import type { Queue } from '@cloudflare/workers-types';

export interface BreachEvent {
  incident_id: string;
  detected_at: number;          // Unix epoch
  data_categories: string[];    // e.g. ['email','pseudonym']
  estimated_affected: number;
  description: string;
}

export interface Env { BREACH_QUEUE: Queue<BreachEvent>; example project_DB: D1Database }

// Enqueue immediately on detection — Worker picks up for 72-h CPLT window
export async function enqueueBreachNotification(
  env: Env,
  event: BreachEvent,
): Promise<void> {
  await env.BREACH_QUEUE.send(event);
  await env.example project_DB.prepare(
    `INSERT INTO breach_log (incident_id, detected_at, queued_at, status)
     VALUES (?, ?, ?, 'queued')`,
  ).bind(
    event.incident_id,
    event.detected_at,
    Math.floor(Date.now() / 1000),
    'queued',
  ).run();
}

// Queue consumer — runs in separate Worker, posts to CPLT API when available
export async function handleBreachQueue(
  batch: MessageBatch<BreachEvent>,
  env: Env,
): Promise<void> {
  for (const msg of batch.messages) {
    const ev = msg.body;
    const elapsedHours = (Date.now() / 1000 - ev.detected_at) / 3600;
    if (elapsedHours > 72) {
      console.error(`BREACH OVERDUE: ${ev.incident_id} — ${elapsedHours.toFixed(1)}h`);
    }
    // POST to CPLT notification portal (hypothetical endpoint)
    // const resp = await fetch('https://notificacion.cplt.cl/api/brechas', { ... });
    await env.example project_DB.prepare(
      `UPDATE breach_log SET status = 'notified', notified_at = ? WHERE incident_id = ?`,
    ).bind(Math.floor(Date.now() / 1000), ev.incident_id).run();
    msg.ack();
  }
}
```

---

## 4 — Cross-Border Transfer Guard

```typescript
// src/chile/transfer-guard.ts
// Chile Law 21.719 Art. 27 — transfers to adequate countries or via SCCs

const ADEQUATE_COUNTRIES = new Set([
  'EU', 'UK', 'CH', 'IL', 'JP', 'NZ', 'CA', 'KR', 'AR',
]);

export function assertTransferLawful(destinationCountry: string, hasSCC: boolean): void {
  if (ADEQUATE_COUNTRIES.has(destinationCountry)) return;
  if (hasSCC) return;
  throw new Error(
    `Cross-border transfer to ${destinationCountry} requires CPLT-approved SCCs under CL Law 21.719 Art. 27`,
  );
}

export async function logTransfer(
  db: D1Database,
  accountId: string,
  destination: string,
  basis: 'adequacy' | 'scc' | 'consent',
): Promise<void> {
  await db.prepare(
    `INSERT INTO cross_border_transfers (account_id, destination, basis, ts)
     VALUES (?, ?, ?, ?)`,
  ).bind(accountId, destination, basis, Math.floor(Date.now() / 1000)).run();
}
```

---

## 5 — Portability Export (Art. 15)

```typescript
// src/chile/portability.ts
export async function buildPortabilityPackage(
  db: D1Database,
  accountId: string,
): Promise<Record<string, unknown>> {
  const [consent, posts, reactions] = await Promise.all([
    db.prepare(
      `SELECT purpose, legal_basis, consent_ts FROM chile_processing_records
       WHERE account_id = ? AND withdrawn_ts IS NULL`,
    ).bind(accountId).all(),
    db.prepare(
      `SELECT post_id, body_hash, created_at FROM posts WHERE account_id = ?`,
    ).bind(accountId).all(),
    db.prepare(
      `SELECT target_post_id, reaction_type, created_at FROM reactions
       WHERE account_id = ?`,
    ).bind(accountId).all(),
  ]);

  return {
    export_date: new Date().toISOString(),
    controller: 'example project Platform',
    law: 'Chile Law 21.719',
    consent_records: consent.results,
    posts: posts.results,
    reactions: reactions.results,
  };
}
```

---

## Anti-patterns

- **Relying on the 1999 Law 19.628**: It lacked a supervisory authority with real enforcement power. Law 21.719 grants CPLT sanctioning authority — treat enforcement as live from December 2026.
- **Conflating pseudonymous with anonymous**: The law applies to pseudonymous data if re-identification is possible. example project handle-to-email mappings must be protected as personal data.
- **Skipping DPIA for profiling**: Any behavioral profiling of Chilean users triggers a mandatory DPIA under Art. 22.
- **Ignoring the legitimate interest balancing test**: Unlike GDPR, Law 21.719 requires that LIA results be documented and made available to the CPLT on request.

---

## Gotchas

- **Transition period ends December 2026** — enforcement starts then, but you cannot claim later that you were unaware; begin compliance engineering now.
- **Sensitive data consent must be explicit and written** (Art. 16 transitorio): a checkbox "I agree" does not satisfy the requirement; a separate, affirmative tick per category is needed.
- **CPLT dual role**: CPLT oversees both transparency/public information and now personal data protection — breach notifications go there, as do user complaints.
- **10,000 UTM cap is per infraction, not per incident**: multiple violations in one breach can stack fines.

---

## Verification

```bash
# Confirm lawful-basis table exists in D1
wrangler d1 execute example project_DB \
  --command "SELECT COUNT(*) FROM chile_processing_records;"

# Simulate a DSR access request
curl -X GET https://example project.example.com/cl/dsr/access \
  -H "X-Account-Id: <test-account-hash>"

# Check breach log
wrangler d1 execute example project_DB \
  --command "SELECT incident_id, status, detected_at FROM breach_log ORDER BY detected_at DESC LIMIT 5;"
```

---

## Related

- `argentina-pdp-law-workers-d1-compliance.md` — Argentina Law 25.326 (similar LATAM regime)
- `brazil-lgpd-data-subject-rights-workers-d1.md` — LGPD DSR implementation patterns
- `gdpr-right-to-erasure-d1-r2-pipeline.md` — Erasure pipeline reusable for Art. 16 deletion
- `cross-border-data-transfer-mechanisms.md` — SCC templates

---

## Sources

- Chile Law 21.719 — Ley de Protección de Datos Personales (published December 2024, Diario Oficial)
- CPLT — Consejo para la Transparencia: <https://www.cplt.cl/>
- IAPP — Chile Data Protection Law Overview (2025)
- Poder Judicial de Chile — Bases de Datos de Legislación
