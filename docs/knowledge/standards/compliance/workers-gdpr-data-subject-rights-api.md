# GDPR Data Subject Rights API with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your platform processes personal data of EU residents and must handle GDPR Chapter III data subject rights: right of access (Art. 15), right to erasure (Art. 17), and right to data portability (Art. 20). You need an API that verifies identity, tracks 30-day response deadlines, produces machine-readable data exports, and creates an immutable request log — all inside Cloudflare Workers + D1.

## Context

GDPR requires controllers to respond to data subject requests within one month (30 calendar days), extendable by two further months for complex requests. The API must:

1. Accept and queue requests from authenticated users.
2. Verify identity before processing (to prevent impersonation attacks).
3. For access/portability: export all personal data across all D1 tables.
4. For erasure: delete or anonymise personal data in every table, with documented exceptions (legal basis for retention).
5. Log every step for accountability to the supervisory authority.

This pattern implements all three rights in a single Workers app, with D1 as the data store.

## Solution

### 1. D1 Schema — request tracking

```sql
-- migrations/0002_dsr_requests.sql
CREATE TABLE IF NOT EXISTS dsr_requests (
  id              TEXT PRIMARY KEY,
  request_type    TEXT NOT NULL,   -- 'access' | 'erasure' | 'portability'
  subject_email   TEXT NOT NULL,
  subject_id      TEXT,            -- resolved internal user ID after verification
  status          TEXT NOT NULL DEFAULT 'pending_verification',
  -- status flow: pending_verification -> verified -> processing -> completed | rejected
  submitted_at    TEXT NOT NULL,
  deadline_at     TEXT NOT NULL,   -- submitted_at + 30 days
  extended_at     TEXT,            -- if extended: deadline_at + 60 days
  extension_reason TEXT,
  completed_at    TEXT,
  rejection_reason TEXT,
  verification_token TEXT,         -- emailed to subject for identity check
  verification_expires TEXT,
  export_url      TEXT,            -- signed R2 URL when export is ready
  notes           TEXT
);

CREATE INDEX idx_dsr_email    ON dsr_requests(subject_email, submitted_at);
CREATE INDEX idx_dsr_status   ON dsr_requests(status, deadline_at);
CREATE INDEX idx_dsr_deadline ON dsr_requests(deadline_at) WHERE status NOT IN ('completed','rejected');

CREATE TABLE IF NOT EXISTS dsr_audit_log (
  id           TEXT PRIMARY KEY,
  request_id   TEXT NOT NULL REFERENCES dsr_requests(id),
  event_time   TEXT NOT NULL,
  actor        TEXT NOT NULL,  -- 'subject' | 'system' | 'dpo'
  action       TEXT NOT NULL,
  detail       TEXT
);
```

### 2. TypeScript types

```typescript
// src/types/dsr.ts
export type DsrType   = 'access' | 'erasure' | 'portability';
export type DsrStatus =
  | 'pending_verification'
  | 'verified'
  | 'processing'
  | 'completed'
  | 'rejected';

export interface DsrRequest {
  id: string;
  request_type: DsrType;
  subject_email: string;
  subject_id?: string;
  status: DsrStatus;
  submitted_at: string;
  deadline_at: string;
  extended_at?: string;
  extension_reason?: string;
  completed_at?: string;
  rejection_reason?: string;
  verification_token?: string;
  verification_expires?: string;
  export_url?: string;
  notes?: string;
}
```

### 3. Request submission endpoint

```typescript
// src/routes/dsr.ts
import { Hono }    from 'hono';
import { z }       from 'zod';
import { uuidv7 }  from '../lib/uuid';
import { sendVerificationEmail } from '../lib/mailer';
import { dsrAudit } from '../lib/dsr-audit';

type Env = { DB: D1Database; DSR_EMAIL_SECRET: string };
const app = new Hono<{ Bindings: Env }>();

const SubmitSchema = z.object({
  request_type: z.enum(['access', 'erasure', 'portability']),
  email: z.string().email(),
});

// POST /dsr  — unauthenticated, anyone can submit for their own email
app.post('/dsr', async (c) => {
  const body = SubmitSchema.safeParse(await c.req.json());
  if (!body.success) return c.json({ error: body.error.flatten() }, 400);

  const { request_type, email } = body.data;
  const id            = uuidv7();
  const submitted_at  = new Date().toISOString();
  const deadline_at   = addDays(submitted_at, 30);
  const token         = crypto.randomUUID();
  const token_expires = addDays(submitted_at, 3);

  await c.env.DB
    .prepare(`
      INSERT INTO dsr_requests
        (id, request_type, subject_email, status, submitted_at, deadline_at,
         verification_token, verification_expires)
      VALUES (?, ?, ?, 'pending_verification', ?, ?, ?, ?)
    `)
    .bind(id, request_type, email, submitted_at, deadline_at, token, token_expires)
    .run();

  await dsrAudit(c.env.DB, id, 'subject', 'SUBMITTED', `type=${request_type}`);
  await sendVerificationEmail(email, token, request_type, c.env.DSR_EMAIL_SECRET);

  return c.json({ id, message: 'Verification email sent. Please verify within 3 days.' }, 202);
});

export default app;
```

### 4. Identity verification endpoint

```typescript
// GET /dsr/verify?token=<uuid>
app.get('/dsr/verify', async (c) => {
  const token = c.req.query('token');
  if (!token) return c.json({ error: 'token required' }, 400);

  const req = await c.env.DB
    .prepare(`
      SELECT * FROM dsr_requests
      WHERE verification_token = ?
        AND status = 'pending_verification'
        AND verification_expires > ?
    `)
    .bind(token, new Date().toISOString())
    .first<DsrRequest>();

  if (!req) return c.json({ error: 'Invalid or expired token' }, 404);

  // Resolve internal user ID
  const user = await c.env.DB
    .prepare('SELECT id FROM users WHERE email = ?')
    .bind(req.subject_email)
    .first<{ id: string }>();

  if (!user) {
    await c.env.DB
      .prepare(`UPDATE dsr_requests SET status='rejected', rejection_reason=? WHERE id=?`)
      .bind('No account found for this email address', req.id)
      .run();
    return c.json({ error: 'No account found' }, 404);
  }

  await c.env.DB
    .prepare(`
      UPDATE dsr_requests
      SET status='verified', subject_id=?, verification_token=NULL
      WHERE id=?
    `)
    .bind(user.id, req.id)
    .run();

  await dsrAudit(c.env.DB, req.id, 'system', 'VERIFIED', `user_id=${user.id}`);

  return c.json({ message: 'Identity verified. Request is now queued for processing.' });
});
```

### 5. Right-to-access & portability export

```typescript
// src/lib/dsr-export.ts
import type { D1Database } from '@cloudflare/workers-types';

export async function buildSubjectExport(db: D1Database, userId: string): Promise<Record<string, unknown[]>> {
  // Collect data from every table containing personal data
  const tables: Array<{ name: string; query: string }> = [
    { name: 'profile',      query: 'SELECT * FROM users WHERE id = ?' },
    { name: 'orders',       query: 'SELECT * FROM orders WHERE user_id = ?' },
    { name: 'addresses',    query: 'SELECT * FROM addresses WHERE user_id = ?' },
    { name: 'sessions',     query: 'SELECT id, created_at, ip, user_agent FROM sessions WHERE user_id = ?' },
    { name: 'preferences',  query: 'SELECT * FROM preferences WHERE user_id = ?' },
    { name: 'activity_log', query: 'SELECT * FROM activity_log WHERE user_id = ? ORDER BY created_at' },
  ];

  const export_data: Record<string, unknown[]> = {};

  for (const t of tables) {
    const { results } = await db.prepare(t.query).bind(userId).all();
    export_data[t.name] = results;
  }

  return export_data;
}

export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  const lines   = rows.map(r =>
    headers.map(h => JSON.stringify(r[h] ?? '')).join(',')
  );
  return [headers.join(','), ...lines].join('\n');
}
```

```typescript
// GET /dsr/:id/export — returns JSON or CSV of subject's data
app.get('/dsr/:id/export', requireDsrOwner, async (c) => {
  const dsr = await getDsr(c.env.DB, c.req.param('id'));

  if (dsr.status !== 'verified' && dsr.status !== 'processing') {
    return c.json({ error: 'Request not yet verified' }, 409);
  }

  const format = c.req.query('format') ?? 'json'; // 'json' | 'csv'
  const data   = await buildSubjectExport(c.env.DB, dsr.subject_id!);

  await c.env.DB
    .prepare(`UPDATE dsr_requests SET status='completed', completed_at=? WHERE id=?`)
    .bind(new Date().toISOString(), dsr.id)
    .run();

  await dsrAudit(c.env.DB, dsr.id, 'system', 'EXPORTED', `format=${format}`);

  if (format === 'csv') {
    // Multi-table CSV as zip is out of scope here; return JSON envelope with CSV values
    const csvPayload: Record<string, string> = {};
    for (const [table, rows] of Object.entries(data)) {
      csvPayload[table] = toCsv(rows as any[]);
    }
    return c.json({ format: 'csv', tables: csvPayload });
  }

  return c.json({ format: 'json', data });
});
```

### 6. Right-to-erasure endpoint

```typescript
// DELETE /dsr/:id/erase — DPO or system only
app.post('/dsr/:id/erase', requireRole('dpo'), async (c) => {
  const dsr = await getDsr(c.env.DB, c.req.param('id'));
  if (dsr.status !== 'verified') return c.json({ error: 'Not verified' }, 409);

  const userId = dsr.subject_id!;

  // Execute erasure in a batch — D1 batch ensures atomicity
  const batch = c.env.DB.batch([
    // Anonymise rather than hard-delete where FK constraints or legal hold applies
    c.env.DB.prepare(`UPDATE users SET email='erased-${userId}@gdpr.local', name='[Erased]', phone=NULL WHERE id=?`).bind(userId),
    c.env.DB.prepare('DELETE FROM sessions    WHERE user_id = ?').bind(userId),
    c.env.DB.prepare('DELETE FROM preferences WHERE user_id = ?').bind(userId),
    c.env.DB.prepare('UPDATE addresses SET street=NULL, postcode=NULL WHERE user_id=?').bind(userId),
    // Orders are retained for tax/legal purposes but de-linked from PII
    c.env.DB.prepare('UPDATE orders SET user_id=NULL WHERE user_id=?').bind(userId),
  ]);

  await batch;

  await c.env.DB
    .prepare(`UPDATE dsr_requests SET status='completed', completed_at=? WHERE id=?`)
    .bind(new Date().toISOString(), dsr.id)
    .run();

  await dsrAudit(c.env.DB, dsr.id, 'dpo', 'ERASED',
    'Profile anonymised; orders de-linked (legal retention basis Art.6(1)(c))');

  return c.json({ message: 'Erasure complete', retained: ['orders (tax law)'] });
});
```

### 7. Deadline alert cron

```typescript
// src/cron/dsr-deadline-check.ts
export async function checkDsrDeadlines(db: D1Database, notify: (email: string, id: string, daysLeft: number) => Promise<void>) {
  const soon = addDays(new Date().toISOString(), 5); // alert when 5 days remain

  const { results } = await db
    .prepare(`
      SELECT id, subject_email, deadline_at
      FROM dsr_requests
      WHERE status IN ('pending_verification','verified','processing')
        AND deadline_at <= ?
        AND deadline_at > ?
    `)
    .bind(soon, new Date().toISOString())
    .all<{ id: string; subject_email: string; deadline_at: string }>();

  for (const r of results) {
    const daysLeft = Math.ceil(
      (new Date(r.deadline_at).getTime() - Date.now()) / 86_400_000
    );
    await notify(r.subject_email, r.id, daysLeft);
  }
}
```

## Implementation Details

- **30-day clock** starts at `submitted_at`, not at verification. A subject who delays verification does not give you extra processing time — the regulatory deadline is from the moment you received the request.
- **Portability format** (Art. 20): JSON is widely accepted; CSV per table is acceptable. Machine-readable means the subject can import it into another service — avoid custom binary formats.
- **Erasure vs. anonymisation**: Deleting rows that are referenced by financial records creates referential integrity issues and may violate tax law. Anonymising (nulling PII fields, replacing email with a sentinel value) satisfies GDPR while preserving aggregate integrity.
- **D1 batch**: use `db.batch([...])` for erasure to ensure atomicity — all tables are cleared together or none are.
- **Legal retention exceptions**: document them in the `dsr_audit_log` at time of erasure so you can demonstrate to a supervisory authority why certain data was retained.

## Anti-patterns

- **Trusting the email in the submission body** without verification: attackers can submit erasure requests for other users' accounts. Always gate processing behind the email verification token.
- **Hard-deleting orders/invoices**: violates tax retention laws in most jurisdictions. De-link from PII instead.
- **Silently missing tables**: if you add a new table with personal data and forget to update the export/erasure logic, your Art. 15 response is incomplete. Maintain a data map and test it as part of CI.
- **Clock drift in deadline calculation**: use ISO-8601 UTC strings and `Date` arithmetic server-side. Never rely on SQLite `datetime('now', '+30 days')` — Workers and D1 may disagree on wall-clock time.

## Gotchas

- D1's `db.batch()` executes in order but does NOT guarantee cross-statement atomicity in the same way as a `BEGIN TRANSACTION` block. Wrap erasure in a single multi-statement transaction if your D1 version supports it.
- Verification email delivery is not guaranteed. Build a resend endpoint (`POST /dsr/:id/resend-verification`) gated by a cooldown.
- If the subject's email is not in your system, you still must respond within 30 days — the response can be "we hold no data for this email address".

## Verification

```bash
# Submit a request
curl -X POST https://api.example.com/dsr \
  -H 'Content-Type: application/json' \
  -d '{"request_type":"access","email":"user@example.com"}'

# Verify (token from email)
curl "https://api.example.com/dsr/verify?token=<uuid>"

# Export data
curl "https://api.example.com/dsr/<id>/export?format=json" \
  -H "Authorization: Bearer $TOKEN"

# Check deadlines via D1 console
wrangler d1 execute APP_DB \
  --command "SELECT id, status, deadline_at FROM dsr_requests WHERE status != 'completed' ORDER BY deadline_at"
```

## Related

- `documentation/docs/policies/compliance/workers-hipaa-phi-access-logging-d1.md`
- `documentation/docs/policies/compliance/workers-access-recertification-campaign-d1.md`
- `documentation/docs/policies/security/workers-rate-limiting-pattern.md`

## Sources

- GDPR Art. 15 — Right of access by the data subject
- GDPR Art. 17 — Right to erasure ('right to be forgotten')
- GDPR Art. 20 — Right to data portability
- GDPR Art. 12 — Transparent information and modalities
- EDPB Guidelines 01/2022 on data subject rights
- Cloudflare D1 Docs: https://developers.cloudflare.com/d1/
