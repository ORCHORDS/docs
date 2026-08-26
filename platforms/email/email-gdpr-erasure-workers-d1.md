# Email GDPR Right-to-Erasure Processing — Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user submits a GDPR Article 17 "right to erasure" (right to be forgotten) request.
Your email infrastructure stores their address across multiple D1 tables: sent-email
logs, open/click events, preference records, consent audit trails, suppression lists,
and personalisation KV entries. You need to cascade-delete or pseudonymise all of it
within the GDPR-mandated 30-day window, emit a verifiable completion record, and do
this without accidentally re-adding the address if a new send attempt arrives before
the erasure is fully propagated.

---

## Context

GDPR Article 17 applies when:
- The personal data is no longer necessary for the purpose it was collected.
- The data subject withdraws consent (and there is no other lawful basis).
- The data subject objects under Article 21 and there are no overriding grounds.

Email addresses are personal data under GDPR. Associated metadata (open timestamps,
IP addresses from click events, device headers) can also be personal data.

**Retention exceptions** — erasure is *not* required when data is kept for:
- Compliance with a legal obligation (e.g., transaction records under tax law).
- Establishment or defence of legal claims.

In practice: suppress the email address immediately (stop sending), delete behavioural
data (opens/clicks), pseudonymise or delete logs, and retain only legally obligated
records with the email replaced by a pseudonym.

---

## D1 Schema — Typical Email Data Surfaces

```sql
-- Tables that typically hold the email address and must be addressed
-- (schema abbreviated to key columns)

CREATE TABLE subscribers (
  id         TEXT PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  status     TEXT,
  created_at INTEGER
);

CREATE TABLE sent_emails (
  id           TEXT PRIMARY KEY,
  recipient    TEXT NOT NULL,   -- personal data
  subject      TEXT,
  sent_at      INTEGER
);

CREATE TABLE email_events (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL,   -- personal data
  event_type  TEXT,            -- open / click / bounce
  ip          TEXT,            -- personal data
  user_agent  TEXT,            -- potentially personal data
  occurred_at INTEGER
);

CREATE TABLE email_preferences (
  email       TEXT PRIMARY KEY,
  categories  TEXT,
  updated_at  INTEGER
);

CREATE TABLE consent_log (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL,
  action      TEXT,            -- subscribed / unsubscribed / erased
  ip          TEXT,
  ts          INTEGER
);

CREATE TABLE suppression (
  email      TEXT PRIMARY KEY,
  reason     TEXT,
  created_at INTEGER
);

-- Erasure audit table (retained permanently — email replaced by token)
CREATE TABLE erasure_requests (
  id            TEXT PRIMARY KEY,
  token         TEXT NOT NULL,  -- pseudonym, NOT the email
  requested_at  INTEGER NOT NULL,
  completed_at  INTEGER,
  tables_purged TEXT            -- JSON array of table names
);
```

---

## Erasure Worker

```typescript
// erasure-worker.ts

interface Env {
  DB: D1Database;
  KV: KVNamespace;       // personalisation / preference KV
  R2: R2Bucket;          // archived email bodies
  ERASURE_SECRET: string; // HMAC key for pseudonymisation
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }
    const { email } = await request.json<{ email: string }>();
    if (!email || !email.includes("@")) {
      return new Response("invalid email", { status: 400 });
    }
    const result = await processErasure(email.toLowerCase().trim(), env);
    return Response.json(result);
  },
};

async function processErasure(
  email: string,
  env: Env
): Promise<{ token: string; tablesAffected: string[] }> {
  // 1. Generate a stable pseudonym (deterministic HMAC — same token if re-requested)
  const token = await pseudonymise(email, env.ERASURE_SECRET);
  const requestedAt = Math.floor(Date.now() / 1000);
  const tablesPurged: string[] = [];

  // 2. Immediately add to suppression list BEFORE deleting — prevents re-send race
  await env.DB.prepare(
    `INSERT OR REPLACE INTO suppression (email, reason, created_at)
     VALUES (?, 'erasure-gdpr', ?)`
  ).bind(token, requestedAt).run(); // store token, not email
  tablesPurged.push("suppression");

  // 3. Pseudonymise subscriber record (keep row for referential integrity,
  //    replace PII with token)
  const sub = await env.DB.prepare(
    `UPDATE subscribers SET email = ?, status = 'erased' WHERE email = ?`
  ).bind(token, email).run();
  if (sub.meta.changes > 0) tablesPurged.push("subscribers");

  // 4. Pseudonymise sent_emails (keep for business records / legal retention)
  const sent = await env.DB.prepare(
    `UPDATE sent_emails SET recipient = ? WHERE recipient = ?`
  ).bind(token, email).run();
  if (sent.meta.changes > 0) tablesPurged.push("sent_emails");

  // 5. Delete behavioural events (no legitimate retention basis)
  const events = await env.DB.prepare(
    `DELETE FROM email_events WHERE email = ?`
  ).bind(email).run();
  if (events.meta.changes > 0) tablesPurged.push("email_events");

  // 6. Delete preference data
  const prefs = await env.DB.prepare(
    `DELETE FROM email_preferences WHERE email = ?`
  ).bind(email).run();
  if (prefs.meta.changes > 0) tablesPurged.push("email_preferences");

  // 7. Pseudonymise consent log (retain for legal audit, remove email)
  const consent = await env.DB.prepare(
    `UPDATE consent_log SET email = ?, ip = 'erased' WHERE email = ?`
  ).bind(token, email).run();
  if (consent.meta.changes > 0) tablesPurged.push("consent_log");

  // 8. Delete from KV (personalisation data)
  await env.KV.delete(`prefs:${email}`);
  await env.KV.delete(`merge:${email}`);
  tablesPurged.push("kv");

  // 9. Delete archived email bodies from R2 (list by prefix)
  const listed = await env.R2.list({ prefix: `archives/${email}/` });
  for (const obj of listed.objects) {
    await env.R2.delete(obj.key);
  }
  if (listed.objects.length > 0) tablesPurged.push("r2-archives");

  // 10. Write erasure audit record
  await env.DB.prepare(
    `INSERT INTO erasure_requests (id, token, requested_at, completed_at, tables_purged)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    token,
    requestedAt,
    Math.floor(Date.now() / 1000),
    JSON.stringify(tablesPurged)
  ).run();

  return { token, tablesAffected: tablesPurged };
}

async function pseudonymise(email: string, secret: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(email));
  const hex = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
  return `erased-${hex}@pseudonym.invalid`;
}
```

---

## Handling New Sends After Erasure

```typescript
// pre-send guard in your sending Worker
async function isSuppressed(email: string, env: Env): Promise<boolean> {
  // Check by the real email — suppression row stores the pseudonym,
  // so we must check via a separate active-suppression index, OR
  // keep a lightweight KV flag keyed by email hash.
  const key = await hashEmail(email, env.ERASURE_SECRET);
  const flag = await env.KV.get(`erased:${key}`);
  return flag !== null;
}
```

Set `erased:<hash>` in KV at erasure time with no expiry. This avoids storing the
raw email anywhere while still allowing O(1) pre-send checks.

---

## Verification Endpoint

```typescript
// GET /erasure/status?token=<redacted-secret>
export async function erasureStatus(token: string, env: Env): Promise<Response> {
  const row = await env.DB.prepare(
    `SELECT token, requested_at, completed_at, tables_purged
     FROM erasure_requests WHERE token = ?`
  ).bind(token).first();
  if (!row) return new Response("not found", { status: 404 });
  return Response.json(row);
}
```

Return this token to the data subject as their erasure reference number.

---

## Anti-patterns

- **Deleting from consent_log entirely** — regulators may ask you to prove you stopped
  sending after consent withdrawal. Pseudonymise; do not delete.
- **Deleting suppression entries** — if you delete the suppression record, a new sign-up
  with the same email bypasses the erasure. Keep suppression under the pseudonym or a
  hash.
- **Processing asynchronously without a pre-send gate** — queued sends may fire between
  the erasure request and the queue processing. The KV flag approach above prevents this.
- **Storing the plaintext email in the audit log** — the erasure_requests table exists
  to prove you erased PII; putting the email back in it defeats the purpose.

---

## Gotchas

- D1 does not support multi-table transactions across different `prepare()` calls.
  Use sequential statements; accept that a crash mid-erasure leaves partial state.
  The idempotent HMAC pseudonym means re-running the erasure is safe.
- R2 `list()` returns at most 1000 objects per call. Paginate with `cursor` for
  users with many archived emails.
- The pseudonym domain `.invalid` is an IANA-reserved label — no MX record will
  ever resolve for it, preventing accidental re-activation.
- Confirm your DPA (Data Processing Agreement) with downstream ESPs — suppression
  lists must also be synced to Mailgun/SES/SendGrid. See
  `email-cross-esp-suppression-sync-d1.md`.

---

## Related

- `email-cross-esp-suppression-sync-d1.md` — syncing suppression across ESPs
- `email-consent-audit-trail-d1.md` — consent logging schema
- `gdpr-email-consent.md` — consent collection
- `email-suppression-list-kv-workers.md` — KV suppression lookup
- `bulk-email-compliance-can-spam-gdpr.md` — compliance overview

---

## Sources

- GDPR Article 17 — Right to erasure
- GDPR Recital 65 — erasure of personal data
- ICO guidance: Right to erasure (erasure.ico.org.uk)
- EDPB Guidelines 05/2020 on consent
- Cloudflare D1 documentation — batched writes
- Cloudflare R2 documentation — list with cursor
