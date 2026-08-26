# Immutable Email Security Audit Trail with D1

- Date: 2026-08-22
- Author: example.com
- Status: production

## Append-Only Email Audit Log for Compliance

Regulatory frameworks — GDPR, HIPAA, SOC 2, and legal hold requests — require
demonstrable evidence of what email was sent, to whom, when, and whether it
was authenticated. Standard ESP dashboards retain data for 30–90 days and
offer no cryptographic immutability guarantee. A self-owned append-only audit
log closes this gap by capturing envelope metadata, authentication results,
and disposition outcomes in D1 at send time, with no UPDATE or DELETE paths
permitted.

D1's SQLite foundation makes it straightforward to enforce append-only
semantics at the schema level via triggers that reject any attempt to modify
or delete audit rows. A Workers middleware layer intercepts every outbound
send, records the event before handing off to the ESP, and exposes a
compliance query API that legal and security teams can hit with date-range or
recipient filters.

The architecture keeps audit data under the application's control, queryable
with standard SQL, and independently verifiable via row hashes chained to the
previous entry.

## Context

Stack: Cloudflare Workers, D1, Resend or SendGrid, TypeScript, Wrangler 3+.

A thin middleware Worker wraps all outbound send calls. Before calling the
ESP API, it inserts an audit row with a hash of the message envelope. After
the ESP responds, it updates the row status — the only permitted mutation.
SQLite triggers block DELETE and further UPDATE on finalised rows. A read-only
compliance API endpoint allows querying the log with field filters.

## D1 Schema with Immutability Triggers

```sql
-- migrations/0001_audit_log.sql

CREATE TABLE email_audit_log (
  id              TEXT PRIMARY KEY,          -- UUID generated in Worker
  prev_hash       TEXT NOT NULL DEFAULT '',  -- SHA-256 of previous row for chaining
  row_hash        TEXT NOT NULL,             -- SHA-256(id||prev_hash||envelope fields)
  sent_at         INTEGER NOT NULL,          -- Unix epoch ms
  from_address    TEXT NOT NULL,
  to_address      TEXT NOT NULL,
  subject_hash    TEXT NOT NULL,             -- SHA-256 of subject (PII-safe)
  template_id     TEXT,
  campaign_id     TEXT,
  dkim_domain     TEXT,
  dkim_selector   TEXT,
  spf_result      TEXT,
  dmarc_result    TEXT,
  esp_message_id  TEXT,
  status          TEXT NOT NULL DEFAULT 'queued',   -- queued|sent|bounced|failed
  status_updated_at INTEGER
);

-- Prevent deletion of audit rows
CREATE TRIGGER no_delete_audit
BEFORE DELETE ON email_audit_log
BEGIN
  SELECT RAISE(ABORT, 'Audit log rows are immutable — DELETE not permitted');
END;

-- Allow only status/esp_message_id updates; block modification of envelope fields
CREATE TRIGGER no_update_envelope
BEFORE UPDATE OF from_address, to_address, subject_hash, sent_at, row_hash, prev_hash
ON email_audit_log
BEGIN
  SELECT RAISE(ABORT, 'Envelope fields are immutable after insert');
END;

CREATE INDEX idx_audit_to        ON email_audit_log(to_address, sent_at DESC);
CREATE INDEX idx_audit_campaign  ON email_audit_log(campaign_id, sent_at DESC);
CREATE INDEX idx_audit_status    ON email_audit_log(status, sent_at DESC);
```

## Middleware Worker — Capture Envelope at Send Time

```ts
// workers/email-audit-middleware.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  RESEND_API_KEY: string;
}

interface SendPayload {
  from: string;
  to: string;
  subject: string;
  html: string;
  templateId?: string;
  campaignId?: string;
  dkimDomain?: string;
  dkimSelector?: string;
}

async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function insertAuditRow(
  db: D1Database,
  id: string,
  payload: SendPayload
): Promise<void> {
  // Fetch previous row hash for chain integrity
  const prev = await db
    .prepare(`SELECT row_hash FROM email_audit_log ORDER BY sent_at DESC LIMIT 1`)
    .first<{ row_hash: string }>();
  const prevHash = prev?.row_hash ?? '';

  const subjectHash = await sha256Hex(payload.subject);
  const sentAt = Date.now();
  const rowHash = await sha256Hex(
    [id, prevHash, payload.from, payload.to, subjectHash, sentAt].join('|')
  );

  await db
    .prepare(
      `INSERT INTO email_audit_log
         (id, prev_hash, row_hash, sent_at, from_address, to_address,
          subject_hash, template_id, campaign_id, dkim_domain, dkim_selector, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued')`
    )
    .bind(
      id, prevHash, rowHash, sentAt,
      payload.from, payload.to, subjectHash,
      payload.templateId ?? null,
      payload.campaignId ?? null,
      payload.dkimDomain ?? null,
      payload.dkimSelector ?? null
    )
    .run();
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST' || new URL(req.url).pathname !== '/send') {
      return new Response('Not found', { status: 404 });
    }

    const payload = await req.json<SendPayload>();
    const id = crypto.randomUUID();

    await insertAuditRow(env.DB, id, payload);

    // Forward to ESP
    const espRes = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ from: payload.from, to: payload.to, subject: payload.subject, html: payload.html }),
    });

    const { id: espId, error } = await espRes.json<{ id?: string; error?: string }>();

    // Update mutable status fields only
    await env.DB.prepare(
      `UPDATE email_audit_log
       SET status = ?, esp_message_id = ?, status_updated_at = ?
       WHERE id = ?`
    )
      .bind(error ? 'failed' : 'sent', espId ?? null, Date.now(), id)
      .run();

    return Response.json({ auditId: id, espId, error });
  },
};
```

## Compliance Query API

```ts
// workers/compliance-api.ts — read-only query endpoint for legal holds
export async function handleComplianceQuery(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const recipient = url.searchParams.get('to');
  const from = url.searchParams.get('from_ts');  // epoch ms
  const to = url.searchParams.get('to_ts');      // epoch ms
  const limit = Math.min(Number(url.searchParams.get('limit') ?? 100), 1000);

  const rows = await env.DB.prepare(
    `SELECT id, sent_at, from_address, to_address, subject_hash,
            template_id, campaign_id, dkim_domain, spf_result, dmarc_result,
            esp_message_id, status, row_hash, prev_hash
     FROM email_audit_log
     WHERE (? IS NULL OR to_address = ?)
       AND (? IS NULL OR sent_at >= CAST(? AS INTEGER))
       AND (? IS NULL OR sent_at <= CAST(? AS INTEGER))
     ORDER BY sent_at DESC
     LIMIT ?`
  )
    .bind(recipient, recipient, from, from, to, to, limit)
    .all();

  return Response.json({ rows: rows.results, count: rows.results.length });
}
```

## Anti-patterns

- Relying solely on ESP activity dashboards for audit data — they expire, can be deleted, and are outside your compliance boundary
- Logging the full subject line instead of a SHA-256 hash — subject lines often contain PII that creates unnecessary retention risk
- Using KV for the audit log — KV has no SQL query capability and no trigger support for immutability enforcement
- Auditing only successful sends — failed and queued states are equally important for compliance evidence

## Gotchas

- D1 triggers fire within the SQLite transaction; a trigger `RAISE(ABORT)` rolls back the entire statement cleanly
- The hash chain requires serial inserts; concurrent Workers instances could race on `prev_hash` — use Durable Objects or a Queue if strict chain ordering is mandatory
- D1 has a 500 MB per-database limit in beta; for very high send volumes, partition logs by month into separate D1 databases
- `status_updated_at` is nullable for rows that never received an ESP callback; account for this in compliance queries

## Verification

```ts
// Verify chain integrity for a range of rows
const rows = await env.DB.prepare(
  `SELECT id, prev_hash, row_hash FROM email_audit_log ORDER BY sent_at ASC LIMIT 100`
).all<{ id: string; prev_hash: string; row_hash: string }>();

for (let i = 1; i < rows.results.length; i++) {
  const expected = rows.results[i].prev_hash;
  const actual = rows.results[i - 1].row_hash;
  console.assert(expected === actual, `Chain break at row ${i}: prev_hash mismatch`);
}
console.log('Chain integrity OK for', rows.results.length, 'rows');
```

## Related

- email-consent-audit-trail-d1.md
- dmarc-aggregate-report-parsing.md
- spf-dkim-dmarc-alignment-debugging-workers.md
- bulk-email-compliance-can-spam-gdpr.md
- bounce-suppression-d1.md

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_createtrigger.html
- https://developers.cloudflare.com/workers/
- https://www.rfc-editor.org/rfc/rfc7208 (SPF)
- https://www.rfc-editor.org/rfc/rfc6376 (DKIM)
