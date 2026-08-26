# Brazil LGPD — Data Subject Rights Engineering on Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project processes personal data of Brazilian users. Under the Lei Geral de Proteção de Dados Pessoais (LGPD, Law 13.709/2018), data subjects hold nine distinct rights enumerated in Art. 18 plus the right to review automated decisions under Art. 20. The ANPD (Autoridade Nacional de Proteção de Dados) requires controllers to respond to access requests within **15 days** (confirmed by ANPD Resolution CD/ANPD nº 4/2023). A general LGPD overview is in `lgpd-brazil-compliance.md`; this article focuses exclusively on the engineering implementation of all nine rights in Cloudflare Workers backed by D1.

---

## Context

**LGPD Art. 18 rights** (all nine):

| # | Right | Key obligation |
|---|-------|----------------|
| I | Confirmation of processing | Immediate or within 15 days |
| II | Access | Within 15 days; machine-readable format required |
| III | Correction | Of incomplete, inaccurate or outdated data |
| IV | Anonymisation, blocking, or deletion of excessive/unnecessary data | |
| V | Portability | To another service provider on request |
| VI | Deletion of data processed with consent | Except where retention is legally required |
| VII | Information about sharing | Which third parties data is shared with |
| VIII | Information about refusing consent | And the consequences of refusal |
| IX | Revocation of consent | Facilitated free of charge |

**Art. 20**: Right to review any decision made solely by automated processing (profiling), including a right to a human review.

**Enforcement**: ANPD can impose fines up to 2% of Brazilian revenue, capped at BRL 50 M per infraction. Administrative sanctions started July 2023.

---

## 1 — DSR Request Schema and Queue

```typescript
// schema/lgpd-dsr.sql
CREATE TABLE IF NOT EXISTS lgpd_dsr_requests (
  id            TEXT PRIMARY KEY,
  account_id    TEXT NOT NULL,
  right_type    TEXT NOT NULL CHECK (right_type IN (
    'art18i_confirmation','art18ii_access','art18iii_correction',
    'art18iv_anonymise_block_delete','art18v_portability',
    'art18vi_delete_consent_data','art18vii_sharing_info',
    'art18viii_refusal_info','art18ix_revoke_consent','art20_automated_review'
  )),
  requested_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  deadline_at   INTEGER NOT NULL,   -- requested_at + 15 days (in seconds)
  status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','in_progress','completed','refused')),
  completed_at  INTEGER,
  refusal_basis TEXT
);
CREATE INDEX IF NOT EXISTS idx_lgpd_dsr_account ON lgpd_dsr_requests(account_id);
CREATE INDEX IF NOT EXISTS idx_lgpd_dsr_deadline ON lgpd_dsr_requests(deadline_at) WHERE status = 'pending';
```

```typescript
// src/br/dsr-intake.ts
import { Hono } from 'hono';
import type { Env } from '../types';

const FIFTEEN_DAYS_S = 15 * 24 * 60 * 60;

export const dsrRouter = new Hono<{ Bindings: Env }>();

dsrRouter.post('/br/dsr', async (c) => {
  const body = await c.req.json<{ right_type: string }>();
  const accountId = c.req.header('X-Account-Id') ?? '';
  const now = Math.floor(Date.now() / 1000);

  const id = crypto.randomUUID();
  await c.env.example project_DB.prepare(
    `INSERT INTO lgpd_dsr_requests (id, account_id, right_type, requested_at, deadline_at)
     VALUES (?, ?, ?, ?, ?)`,
  ).bind(id, accountId, body.right_type, now, now + FIFTEEN_DAYS_S).run();

  return c.json({ request_id: id, deadline: new Date((now + FIFTEEN_DAYS_S) * 1000).toISOString() });
});
```

---

## 2 — Art. 18-I & 18-II: Confirmation and Access

```typescript
// src/br/art18-access.ts
import type { D1Database } from '@cloudflare/workers-types';

export async function fulfillAccess(
  db: D1Database,
  requestId: string,
  accountId: string,
): Promise<Record<string, unknown>> {
  const [profile, posts, processing] = await Promise.all([
    db.prepare(`SELECT pseudonym, email_hash, created_at FROM accounts WHERE id = ?`)
      .bind(accountId).first(),
    db.prepare(`SELECT post_id, body_hash, created_at FROM posts WHERE account_id = ?`)
      .bind(accountId).all(),
    db.prepare(
      `SELECT purpose, legal_basis, created_at FROM lgpd_processing_records WHERE account_id = ?`,
    ).bind(accountId).all(),
  ]);

  await db.prepare(
    `UPDATE lgpd_dsr_requests SET status = 'completed', completed_at = ? WHERE id = ?`,
  ).bind(Math.floor(Date.now() / 1000), requestId).run();

  return {
    confirmation: Boolean(profile),   // Art. 18-I
    profile,                           // Art. 18-II
    posts: posts.results,
    processing_activities: processing.results,
    generated_at: new Date().toISOString(),
  };
}
```

---

## 3 — Art. 18-III: Correction of Inaccurate Data

```typescript
// src/br/art18iii-correction.ts

export interface CorrectionPayload {
  requestId: string;
  accountId: string;
  field: string;
  newValue: string;
}

const CORRECTABLE_FIELDS = new Set(['pseudonym', 'email_hash', 'locale']);

export async function fulfillCorrection(
  db: D1Database,
  payload: CorrectionPayload,
): Promise<{ ok: boolean; reason?: string }> {
  if (!CORRECTABLE_FIELDS.has(payload.field)) {
    await markRefused(db, payload.requestId, 'field_not_correctable');
    return { ok: false, reason: 'Field is not correctable via this channel.' };
  }

  // Parameterised field name is not possible in D1; validate against allowlist above.
  const stmt = {
    pseudonym:   `UPDATE accounts SET pseudonym   = ? WHERE id = ?`,
    email_hash:  `UPDATE accounts SET email_hash  = ? WHERE id = ?`,
    locale:      `UPDATE accounts SET locale      = ? WHERE id = ?`,
  }[payload.field];

  await db.batch([
    db.prepare(stmt!).bind(payload.newValue, payload.accountId),
    db.prepare(
      `UPDATE lgpd_dsr_requests SET status='completed', completed_at=? WHERE id=?`,
    ).bind(Math.floor(Date.now() / 1000), payload.requestId),
  ]);
  return { ok: true };
}

async function markRefused(db: D1Database, requestId: string, basis: string): Promise<void> {
  await db.prepare(
    `UPDATE lgpd_dsr_requests SET status='refused', refusal_basis=?, completed_at=? WHERE id=?`,
  ).bind(basis, Math.floor(Date.now() / 1000), requestId).run();
}
```

---

## 4 — Art. 18-IV & 18-VI: Deletion (Excessive Data / Consent-Based Data)

```typescript
// src/br/art18-delete.ts
// IV: delete data that is unnecessary or excessive for the stated purpose.
// VI: delete data whose legal basis was consent, when consent is withdrawn.

export async function fulfillDeletion(
  db: D1Database,
  requestId: string,
  accountId: string,
  variant: 'iv_excessive' | 'vi_consent',
): Promise<void> {
  // Check for retention obligations that override deletion
  const hold = await db.prepare(
    `SELECT id FROM legal_holds WHERE account_id = ? AND law = 'BR-LGPD' LIMIT 1`,
  ).bind(accountId).first();

  if (hold) {
    await db.prepare(
      `UPDATE lgpd_dsr_requests SET status='refused', refusal_basis='legal_hold', completed_at=?
       WHERE id=?`,
    ).bind(Math.floor(Date.now() / 1000), requestId).run();
    return;
  }

  const toDelete =
    variant === 'vi_consent'
      ? // Delete only data processed under consent basis
        [
          db.prepare(
            `DELETE FROM lgpd_processing_records WHERE account_id=? AND legal_basis='consent'`,
          ).bind(accountId),
        ]
      : // Delete all data judged unnecessary/excessive — full account purge
        [
          db.prepare(`DELETE FROM posts WHERE account_id=?`).bind(accountId),
          db.prepare(`DELETE FROM reactions WHERE account_id=?`).bind(accountId),
          db.prepare(`DELETE FROM lgpd_processing_records WHERE account_id=?`).bind(accountId),
          db.prepare(`DELETE FROM accounts WHERE id=?`).bind(accountId),
        ];

  await db.batch([
    ...toDelete,
    db.prepare(
      `UPDATE lgpd_dsr_requests SET status='completed', completed_at=? WHERE id=?`,
    ).bind(Math.floor(Date.now() / 1000), requestId),
    db.prepare(
      `INSERT INTO deletion_audit (account_id, law, variant, ts) VALUES (?,?,?,?)`,
    ).bind(accountId, 'BR-LGPD', variant, Math.floor(Date.now() / 1000)),
  ]);
}
```

---

## 5 — Art. 18-V: Portability Export

```typescript
// src/br/art18v-portability.ts

export async function fulfillPortability(
  db: D1Database,
  r2: R2Bucket,
  requestId: string,
  accountId: string,
): Promise<{ download_key: string }> {
  const [profile, posts, processing] = await Promise.all([
    db.prepare(`SELECT pseudonym, email_hash, created_at FROM accounts WHERE id=?`)
      .bind(accountId).first(),
    db.prepare(`SELECT * FROM posts WHERE account_id=?`).bind(accountId).all(),
    db.prepare(`SELECT * FROM lgpd_processing_records WHERE account_id=?`)
      .bind(accountId).all(),
  ]);

  const payload = JSON.stringify(
    { law: 'BR-LGPD Art.18-V', profile, posts: posts.results, processing: processing.results },
    null,
    2,
  );

  const key = `lgpd-portability/${accountId}/${requestId}.json`;
  await r2.put(key, payload, {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: { expires_at: String(Math.floor(Date.now() / 1000) + 7 * 86400) },
  });

  await db.prepare(
    `UPDATE lgpd_dsr_requests SET status='completed', completed_at=? WHERE id=?`,
  ).bind(Math.floor(Date.now() / 1000), requestId).run();

  return { download_key: key };
}
```

---

## 6 — Art. 20: Automated Decision Review

```typescript
// src/br/art20-automated-review.ts
// Any solely-automated decision affecting user interests must be reviewable by a human.

export async function requestHumanReview(
  db: D1Database,
  accountId: string,
  decisionId: string,
): Promise<void> {
  await db.prepare(
    `INSERT INTO art20_review_queue (account_id, decision_id, requested_at, status)
     VALUES (?, ?, ?, 'pending')`,
  ).bind(accountId, decisionId, Math.floor(Date.now() / 1000)).run();
  // A compliance officer picks this up in the admin dashboard.
}

export async function logAutomatedDecision(
  db: D1Database,
  accountId: string,
  decisionType: string, // e.g. 'content_moderation_auto_removal'
  inputFeatures: Record<string, unknown>,
): Promise<string> {
  const id = crypto.randomUUID();
  await db.prepare(
    `INSERT INTO automated_decisions (id, account_id, decision_type, input_hash, decided_at)
     VALUES (?, ?, ?, ?, ?)`,
  ).bind(
    id, accountId, decisionType,
    // Hash features so PII is not stored verbatim in the log
    await hashObject(inputFeatures),
    Math.floor(Date.now() / 1000),
  ).run();
  return id;
}

async function hashObject(obj: Record<string, unknown>): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(obj)));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

---

## 7 — Deadline Monitor (Cron Trigger)

```typescript
// src/br/deadline-monitor.ts — runs every 6 hours via Cron Trigger
export async function checkDeadlines(db: D1Database): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  const overdue = await db.prepare(
    `SELECT id, account_id, right_type, deadline_at FROM lgpd_dsr_requests
     WHERE status = 'pending' AND deadline_at < ?`,
  ).bind(now).all();

  for (const row of overdue.results as Array<{
    id: string; account_id: string; right_type: string; deadline_at: number;
  }>) {
    const hoursOverdue = ((now - row.deadline_at) / 3600).toFixed(1);
    console.error(
      `LGPD DSR OVERDUE | id=${row.id} type=${row.right_type} ` +
      `account=${row.account_id} overdue=${hoursOverdue}h`,
    );
    // In production: page on-call and auto-escalate to DPO
  }
}
```

---

## Anti-patterns

- **Treating all nine rights as a single "delete everything" request**: Art. 18-IV (excessive data) and Art. 18-VI (consent-based data) have different scopes; conflating them over-deletes data that may be retained on other lawful bases.
- **Ignoring Art. 20 for moderation decisions**: If example project auto-removes posts via ML classifiers, those are automated decisions subject to Art. 20 human review on request.
- **Not logging refusals**: ANPD can require a controller to demonstrate it handled refusals lawfully (e.g., data necessary for legal proceedings). Keep refusal reasons in `lgpd_dsr_requests.refusal_basis`.
- **Returning raw PII in portability exports stored in R2 indefinitely**: Portability files must have a short TTL (7 days) and be access-controlled.

---

## Gotchas

- **15-day deadline is calendar days**, not business days. Set the `deadline_at` column accordingly.
- **Art. 18-IX (consent revocation) must be as easy as giving consent** — if consent was one click, revocation must also be one click.
- **Anonymous data is out of scope**, but example project pseudonyms linked to email hashes are not anonymous under LGPD if re-identification is possible.
- **ANPD's 2% cap is on Brazilian revenue**, not global — but the cap is BRL 50 M per infraction regardless of revenue.

---

## Verification

```bash
# Overdue DSR requests
wrangler d1 execute example project_DB \
  --command "SELECT id, right_type, deadline_at, status FROM lgpd_dsr_requests WHERE status='pending' AND deadline_at < unixepoch();"

# DSR completion rate
wrangler d1 execute example project_DB \
  --command "SELECT status, COUNT(*) FROM lgpd_dsr_requests GROUP BY status;"

# Art. 20 review queue depth
wrangler d1 execute example project_DB \
  --command "SELECT status, COUNT(*) FROM art20_review_queue GROUP BY status;"
```

---

## Related

- `lgpd-brazil-compliance.md` — General LGPD controller obligations and lawful basis
- `gdpr-data-subject-rights-api.md` — GDPR DSR patterns reusable for LGPD
- `gdpr-right-to-erasure-d1-r2-pipeline.md` — Erasure pipeline applicable to Art. 18-IV/VI
- `data-retention-automated-deletion-workers.md` — Retention schedules affecting Art. 18-VI scope

---

## Sources

- LGPD (Law 13.709/2018): <https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm>
- ANPD Resolution CD/ANPD nº 4/2023 — DSR response timelines
- ANPD — Orientações sobre direitos dos titulares: <https://www.gov.br/anpd/>
- IAPP — LGPD Practical Guide (2024)
