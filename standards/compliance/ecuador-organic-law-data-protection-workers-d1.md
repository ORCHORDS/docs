# Ecuador Organic Law on Personal Data Protection (LOPDP) — Cloudflare Workers + D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project serves users in Ecuador. Ecuador's Ley Orgánica de Protección de Datos Personales (LOPDP), enacted May 2021 and enforceable since May 2023, is the country's first comprehensive data protection law. It is closely modelled on the GDPR and introduces legal bases, data subject rights, DPO requirements, DPIAs, breach notification within **15 business days**, and cross-border transfer controls. The supervisory authority is the Superintendencia de Protección de Datos Personales (SPDP). Fines reach 2% of annual global turnover for serious violations and 4% for very serious violations.

---

## Context

Key LOPDP pillars for an anonymous social platform:

- **Legal bases** (Art. 17): consent, contract, legal obligation, vital interests, public task, legitimate interest — mirrors GDPR Art. 6.
- **Sensitive data** (Art. 26): biometric, genetic, health, sexual orientation, political opinion, religion, racial/ethnic origin, judicial background — requires explicit consent; processing for discriminatory profiling is prohibited.
- **Data subject rights** (Arts. 53-72): access, rectification, deletion/opposition, portability, restriction, not to be subject to solely automated decisions, lodge complaints with SPDP.
- **DPO** (Art. 43): mandatory when large-scale or high-risk processing occurs.
- **DPIA** (Art. 41): required before high-risk processing (profiling at scale, systematic monitoring of public areas, large-scale sensitive data).
- **Breach notification** (Art. 44): notify SPDP within **15 business days**; affected individuals "as soon as possible."
- **Cross-border transfers** (Art. 49): permitted to countries with adequate protection or via safeguards (BCRs, SCCs, SPDP-approved codes of conduct).

---

## 1 — Lawful Basis Ledger (D1 Schema)

```typescript
// schema/ec-lawful-basis.sql
CREATE TABLE IF NOT EXISTS ec_processing_records (
  id           TEXT PRIMARY KEY,
  account_id   TEXT NOT NULL,
  purpose      TEXT NOT NULL,
  legal_basis  TEXT NOT NULL CHECK (legal_basis IN (
    'consent','contract','legal_obligation',
    'vital_interests','public_task','legitimate_interest'
  )),
  consent_ts   INTEGER,
  withdrawn_ts INTEGER,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_ec_pr_account ON ec_processing_records(account_id);

CREATE TABLE IF NOT EXISTS ec_dsr_requests (
  id           TEXT PRIMARY KEY,
  account_id   TEXT NOT NULL,
  right_type   TEXT NOT NULL,
  requested_at INTEGER NOT NULL DEFAULT (unixepoch()),
  -- LOPDP does not set a single fixed response window; SPDP guidance: 15 business days
  deadline_at  INTEGER NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',
  completed_at INTEGER
);
```

```typescript
// src/ec/lawful-basis.ts
import type { D1Database } from '@cloudflare/workers-types';

const FIFTEEN_BUSINESS_DAYS_S = 15 * 24 * 3600; // approximate (ignores Ecuador public holidays)

export async function createDSRRequest(
  db: D1Database,
  accountId: string,
  rightType: string,
): Promise<string> {
  const id = crypto.randomUUID();
  const now = Math.floor(Date.now() / 1000);
  await db.prepare(
    `INSERT INTO ec_dsr_requests (id, account_id, right_type, requested_at, deadline_at)
     VALUES (?, ?, ?, ?, ?)`,
  ).bind(id, accountId, rightType, now, now + FIFTEEN_BUSINESS_DAYS_S).run();
  return id;
}
```

---

## 2 — Consent Collection (Art. 17 & 20)

```typescript
// src/ec/consent.ts
// LOPDP Art. 20: consent must be free, specific, informed, unambiguous, and verifiable.
// Sensitive data (Art. 26) additionally requires EXPLICIT consent.

export interface LOPDPConsentPayload {
  accountId: string;
  purpose: string;
  isSensitive: boolean;
  consentText: string;    // Exact text shown to the user
  ipCountry: string;
}

export async function captureConsent(
  db: D1Database,
  payload: LOPDPConsentPayload,
): Promise<void> {
  if (payload.isSensitive && !payload.consentText.includes('EXPLICIT')) {
    // Guard: sensitive consent flows must include explicit affirmation wording
    throw new Error('LOPDP Art. 26: sensitive data requires explicit consent notice text.');
  }

  const id = crypto.randomUUID();
  const textHash = await sha256(payload.consentText);
  await db.prepare(
    `INSERT INTO ec_processing_records
     (id, account_id, purpose, legal_basis, consent_ts)
     VALUES (?, ?, ?, 'consent', ?)`,
  ).bind(id, payload.accountId, payload.purpose, Math.floor(Date.now() / 1000)).run();

  await db.prepare(
    `INSERT INTO ec_consent_evidence (record_id, text_hash, ip_country, is_sensitive)
     VALUES (?, ?, ?, ?)`,
  ).bind(id, textHash, payload.ipCountry, payload.isSensitive ? 1 : 0).run();
}

async function sha256(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

---

## 3 — Data Subject Rights Router (Art. 53-72)

```typescript
// src/ec/dsr-router.ts
import { Hono } from 'hono';
import type { Env } from '../types';

const ecDsr = new Hono<{ Bindings: Env }>();

// Art. 55 — Right of Access
ecDsr.get('/ec/dsr/access', async (c) => {
  const accountId = c.req.header('X-Account-Id') ?? '';
  const requestId = await createDSRRequest(c.env.example project_DB, accountId, 'ec_access');

  const [profile, posts, records] = await Promise.all([
    c.env.example project_DB.prepare(`SELECT pseudonym, email_hash, created_at FROM accounts WHERE id = ?`)
      .bind(accountId).first(),
    c.env.example project_DB.prepare(`SELECT post_id, body_hash, created_at FROM posts WHERE account_id = ?`)
      .bind(accountId).all(),
    c.env.example project_DB.prepare(
      `SELECT purpose, legal_basis, consent_ts FROM ec_processing_records WHERE account_id = ?`,
    ).bind(accountId).all(),
  ]);

  await c.env.example project_DB.prepare(
    `UPDATE ec_dsr_requests SET status='completed', completed_at=? WHERE id=?`,
  ).bind(Math.floor(Date.now() / 1000), requestId).run();

  return c.json({ profile, posts: posts.results, processing: records.results });
});

// Art. 66 — Right to Deletion (Supresión)
ecDsr.delete('/ec/dsr/delete', async (c) => {
  const accountId = c.req.header('X-Account-Id') ?? '';
  const requestId = await createDSRRequest(c.env.example project_DB, accountId, 'ec_deletion');

  const hold = await c.env.example project_DB.prepare(
    `SELECT id FROM legal_holds WHERE account_id = ? LIMIT 1`,
  ).bind(accountId).first();

  if (hold) {
    await c.env.example project_DB.prepare(
      `UPDATE ec_dsr_requests SET status='refused', completed_at=? WHERE id=?`,
    ).bind(Math.floor(Date.now() / 1000), requestId).run();
    return c.json({ deleted: false, reason: 'legal_hold_active' }, 409);
  }

  await c.env.example project_DB.batch([
    c.env.example project_DB.prepare(`DELETE FROM posts WHERE account_id=?`).bind(accountId),
    c.env.example project_DB.prepare(`DELETE FROM ec_processing_records WHERE account_id=?`).bind(accountId),
    c.env.example project_DB.prepare(`DELETE FROM accounts WHERE id=?`).bind(accountId),
    c.env.example project_DB.prepare(
      `UPDATE ec_dsr_requests SET status='completed', completed_at=? WHERE id=?`,
    ).bind(Math.floor(Date.now() / 1000), requestId),
  ]);
  return c.json({ deleted: true });
});

// Art. 69 — Right to Portability
ecDsr.get('/ec/dsr/portability', async (c) => {
  const accountId = c.req.header('X-Account-Id') ?? '';
  const requestId = await createDSRRequest(c.env.example project_DB, accountId, 'ec_portability');

  const [profile, posts] = await Promise.all([
    c.env.example project_DB.prepare(`SELECT pseudonym, email_hash, created_at FROM accounts WHERE id=?`)
      .bind(accountId).first(),
    c.env.example project_DB.prepare(`SELECT * FROM posts WHERE account_id=?`).bind(accountId).all(),
  ]);

  await c.env.example project_DB.prepare(
    `UPDATE ec_dsr_requests SET status='completed', completed_at=? WHERE id=?`,
  ).bind(Math.floor(Date.now() / 1000), requestId).run();

  return c.json({
    format: 'JSON',
    law: 'Ecuador LOPDP Art. 69',
    profile,
    posts: posts.results,
  });
});

export default ecDsr;
```

---

## 4 — Breach Notification (Art. 44 — 15 Business Days)

```typescript
// src/ec/breach-notify.ts

export interface LOPDPBreachEvent {
  incident_id: string;
  detected_at: number;          // Unix epoch
  data_categories: string[];
  estimated_affected_ec: number; // Ecuador users
  description: string;
  risk_level: 'low' | 'medium' | 'high';
}

const FIFTEEN_BDAYS_S = 15 * 24 * 3600; // business days approximation

export async function handleBreach(
  env: { example project_DB: D1Database; BREACH_QUEUE: Queue<LOPDPBreachEvent> },
  event: LOPDPBreachEvent,
): Promise<void> {
  const notifyDeadline = event.detected_at + FIFTEEN_BDAYS_S;

  await env.example project_DB.prepare(
    `INSERT INTO ec_breach_log
     (incident_id, detected_at, notify_deadline, risk_level, status)
     VALUES (?, ?, ?, ?, 'queued')`,
  ).bind(
    event.incident_id,
    event.detected_at,
    notifyDeadline,
    event.risk_level,
  ).run();

  // Only medium/high risk requires individual notification
  if (event.risk_level !== 'low') {
    await env.BREACH_QUEUE.send(event);
  }
}

export function buildSPDPNotificationPayload(event: LOPDPBreachEvent): Record<string, unknown> {
  return {
    controller: 'example project Platform',
    law_article: 'Ecuador LOPDP Art. 44',
    incident_id: event.incident_id,
    detected_at: new Date(event.detected_at * 1000).toISOString(),
    categories: event.data_categories,
    affected_ec_users: event.estimated_affected_ec,
    description: event.description,
    risk_level: event.risk_level,
    dpo_contact: 'dpo@example project.example.com',
    spdp_portal: 'https://www.spdp.gob.ec/',
  };
}
```

---

## 5 — DPIA Trigger Assessment (Art. 41)

```typescript
// src/ec/dpia.ts
// LOPDP Art. 41: DPIA required if processing is "likely to result in high risk"
// Triggers: large-scale profiling, systematic monitoring, sensitive data at scale,
// new technologies with significant privacy impact.

export interface ProcessingActivity {
  name: string;
  involvesProfiling: boolean;
  involvesAutomatedDecisions: boolean;
  scaleEstimateUsers: number;
  sensitiveDataCategories: string[];
  usesNewTechnology: boolean;
  isPublicMonitoring: boolean;
}

export function dpiaRequired(activity: ProcessingActivity): boolean {
  const LARGE_SCALE = 10_000;
  if (activity.isPublicMonitoring) return true;
  if (activity.sensitiveDataCategories.length > 0 && activity.scaleEstimateUsers >= LARGE_SCALE) return true;
  if (activity.involvesProfiling && activity.scaleEstimateUsers >= LARGE_SCALE) return true;
  if (activity.involvesAutomatedDecisions && activity.scaleEstimateUsers >= LARGE_SCALE) return true;
  if (activity.usesNewTechnology) return true;
  return false;
}

export async function logDPIADecision(
  db: D1Database,
  activity: ProcessingActivity,
  required: boolean,
  rationale: string,
): Promise<void> {
  await db.prepare(
    `INSERT INTO ec_dpia_log (activity_name, dpia_required, rationale, assessed_at)
     VALUES (?, ?, ?, ?)`,
  ).bind(activity.name, required ? 1 : 0, rationale, Math.floor(Date.now() / 1000)).run();
}
```

---

## 6 — Cross-Border Transfer Guard (Art. 49)

```typescript
// src/ec/transfer-guard.ts
// Art. 49: transfers permitted to countries with adequate protection per SPDP decision,
// or via BCRs, SCCs approved by SPDP, or explicit consent.

// Ecuador has not yet published a formal adequacy list (SPDP was still being established
// as of 2025). Conservative approach: treat EU-adequate countries as an interim baseline.
const PROVISIONAL_ADEQUATE = new Set(['EU', 'EEA', 'UK', 'CH', 'IL', 'CA', 'NZ', 'JP', 'KR', 'AR']);

export function isTransferLawful(
  destinationIso: string,
  hasSCC: boolean,
  hasBCR: boolean,
  hasExplicitConsent: boolean,
): boolean {
  if (PROVISIONAL_ADEQUATE.has(destinationIso)) return true;
  if (hasSCC || hasBCR || hasExplicitConsent) return true;
  return false;
}

export async function logTransfer(
  db: D1Database,
  accountId: string,
  destination: string,
  basis: string,
): Promise<void> {
  await db.prepare(
    `INSERT INTO ec_transfer_log (account_id, destination, basis, ts) VALUES (?, ?, ?, ?)`,
  ).bind(accountId, destination, basis, Math.floor(Date.now() / 1000)).run();
}
```

---

## Anti-patterns

- **Assuming GDPR SCCs automatically satisfy LOPDP Art. 49**: Ecuador's SPDP has not formally adopted EU SCCs. Until the SPDP publishes its own SCC templates or adequacy list, maintain explicit consent as a fallback for transfers to non-EU countries.
- **Skipping DPIA for the example project moderation ML pipeline**: Automated content moderation that produces legal-effect decisions on user-generated content triggers LOPDP Art. 41 at scale.
- **15 business days for breach notification**: Business days in Ecuador exclude public holidays (of which there are many). Build in calendar margin.
- **No DPO appointment**: If example project processes sensitive data of Ecuadorian users at any scale, Art. 43 mandates a DPO; registration with SPDP is required.

---

## Gotchas

- **SPDP is new and evolving**: The Superintendencia de Protección de Datos Personales was established by LOPDP but guidance documents are still being published. Monitor <https://www.spdp.gob.ec/> for new resolutions.
- **Automated decisions**: Art. 71 gives data subjects the right not to be subject to solely automated decisions with legal or similarly significant effects — covers ML-only post removals.
- **Legitimate interest is a valid basis** under LOPDP (unlike some stricter national laws) but must be documented with a balancing test, available to SPDP on request.
- **Pseudonymous data is still personal data** unless it cannot be re-identified by the controller or a third party — the standard example project caveat applies.

---

## Verification

```bash
# DSR pipeline health
wrangler d1 execute example project_DB \
  --command "SELECT right_type, status, COUNT(*) FROM ec_dsr_requests GROUP BY right_type, status;"

# Overdue requests
wrangler d1 execute example project_DB \
  --command "SELECT id, right_type, deadline_at FROM ec_dsr_requests WHERE status='pending' AND deadline_at < unixepoch();"

# Breach notification log
wrangler d1 execute example project_DB \
  --command "SELECT incident_id, risk_level, status, notify_deadline FROM ec_breach_log ORDER BY detected_at DESC LIMIT 10;"

# DPIA log
wrangler d1 execute example project_DB \
  --command "SELECT activity_name, dpia_required FROM ec_dpia_log ORDER BY assessed_at DESC;"
```

---

## Related

- `chile-data-protection-bill-workers-d1.md` — Adjacent LATAM GDPR-modelled law
- `brazil-lgpd-data-subject-rights-workers-d1.md` — DSR pipeline patterns reusable for LOPDP
- `argentina-pdp-law-workers-d1-compliance.md` — Argentina LPDP (regional context)
- `gdpr-right-to-erasure-d1-r2-pipeline.md` — Erasure pipeline compatible with LOPDP Art. 66
- `ai-dpia-data-protection-impact-assessment.md` — DPIA methodology reusable for Art. 41

---

## Sources

- Ecuador LOPDP (Ley Orgánica de Protección de Datos Personales, 2021): <https://www.registroficial.gob.ec/>
- Superintendencia de Protección de Datos Personales (SPDP): <https://www.spdp.gob.ec/>
- Reglamento General a la LOPDP (Decreto Ejecutivo 8, 2022)
- IAPP — Ecuador Data Protection Overview (2024)
- OneTrust — Ecuador LOPDP Deep Dive (2023)
