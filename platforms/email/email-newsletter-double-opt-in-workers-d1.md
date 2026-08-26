# Email Newsletter Double Opt-In With Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project (example.com) wants to build a newsletter feature that is legally defensible under GDPR and CAN-SPAM, prevents spamtrap hits from bots and disposable addresses, and produces an auditable consent trail. Single opt-in is insufficient: any address submitted — typos, fake signups, bot-harvested — gets added immediately. Double opt-in requires the address owner to confirm by clicking a link in a verification email before any marketing email is sent.

## Context
A Cloudflare Worker handles the subscription form POST, stores a pending record in D1 with a short-lived confirmation token, and sends the confirmation email via MailChannels. A second Worker endpoint handles the confirmation link click, flips the record to confirmed, writes a consent audit entry, and sends a welcome email. All token operations use `crypto.randomUUID()` and are time-bounded. D1 provides the persistence layer for both the subscription state machine and the immutable audit log.

## D1 Schema — Subscriptions and Audit Log

The `newsletter_subscriptions` table models the lifecycle: `pending → confirmed → unsubscribed`. The `consent_audit_log` table is append-only and records every state transition with IP address and timestamp for legal compliance.

```sql
-- migrations/0002_newsletter_doi.sql
CREATE TABLE newsletter_subscriptions (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  email           TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending',   -- pending | confirmed | unsubscribed
  confirm_token   TEXT,
  token_expires   INTEGER,
  confirmed_at    INTEGER,
  unsubscribed_at INTEGER,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  ip_address      TEXT,
  UNIQUE(email)
);

CREATE TABLE consent_audit_log (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  sub_id      TEXT NOT NULL REFERENCES newsletter_subscriptions(id),
  event       TEXT NOT NULL,   -- subscribed | confirmed | unsubscribed | resent
  ip_address  TEXT,
  user_agent  TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_subs_email       ON newsletter_subscriptions(email);
CREATE INDEX idx_subs_token       ON newsletter_subscriptions(confirm_token);
CREATE INDEX idx_audit_sub_id     ON consent_audit_log(sub_id);
```

## Subscription Endpoint — Pending Record and Confirmation Email

The Worker validates the submitted email, rate-limits by IP using KV, creates a pending record in D1 with a token valid for 24 hours, and sends the confirmation email. If the address is already pending (double submit), a fresh token is issued and a new confirmation email is sent to prevent expired-token frustration.

```typescript
// subscribe-handler.ts
export async function handleSubscribe(request: Request, env: Env): Promise<Response> {
  const body = await request.formData();
  const email = (body.get("email") as string | null)?.toLowerCase().trim() ?? "";
  const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
  const ua = request.headers.get("User-Agent") ?? "";

  // Basic format validation
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return Response.json({ error: "Invalid email address" }, { status: 400 });
  }

  // IP rate limit: 3 signups per hour per IP
  const rateKey = `doi:rate:${ip}`;
  const count = parseInt((await env.DOI_KV.get(rateKey)) ?? "0", 10);
  if (count >= 3) {
    return Response.json({ error: "Too many requests" }, { status: 429 });
  }
  await env.DOI_KV.put(rateKey, String(count + 1), { expirationTtl: 3600 });

  // Check for already-confirmed subscription
  const existing = await env.DB
    .prepare("SELECT id, status FROM newsletter_subscriptions WHERE email = ?1")
    .bind(email)
    .first<{ id: string; status: string }>();

  if (existing?.status === "confirmed") {
    // Silently succeed — do not reveal whether the address is subscribed
    return Response.json({ ok: true });
  }

  const token = crypto.randomUUID().replace(/-/g, "");
  const expires = Math.floor(Date.now() / 1000) + 86400; // 24h

  let subId: string;
  if (existing) {
    // Resend — update token
    await env.DB.prepare(`
      UPDATE newsletter_subscriptions
      SET confirm_token = ?1, token_expires = ?2
      WHERE id = ?3
    `).bind(token, expires, existing.id).run();
    subId = existing.id;

    await env.DB.prepare(`
      INSERT INTO consent_audit_log (sub_id, event, ip_address, user_agent)
      VALUES (?1, 'resent', ?2, ?3)
    `).bind(subId, ip, ua).run();
  } else {
    const newId = crypto.randomUUID();
    await env.DB.prepare(`
      INSERT INTO newsletter_subscriptions
        (id, email, status, confirm_token, token_expires, ip_address)
      VALUES (?1, ?2, 'pending', ?3, ?4, ?5)
    `).bind(newId, email, token, expires, ip).run();
    subId = newId;

    await env.DB.prepare(`
      INSERT INTO consent_audit_log (sub_id, event, ip_address, user_agent)
      VALUES (?1, 'subscribed', ?2, ?3)
    `).bind(subId, ip, ua).run();
  }

  const confirmUrl = `https://example.com/newsletter/confirm?token=${token}`;
  await sendConfirmationEmail(env, email, confirmUrl);

  return Response.json({ ok: true });
}
```

## Confirmation Endpoint — Token Validation and State Flip

The user clicks the confirmation link in the email. The Worker validates the token, checks expiry, flips status to `confirmed`, clears the token, and writes to the audit log. A welcome email is sent after confirmation.

```typescript
// confirm-handler.ts
export async function handleConfirm(request: Request, env: Env): Promise<Response> {
  const url   = new URL(request.url);
  const token = url.searchParams.get("token") ?? "";
  const ip    = request.headers.get("CF-Connecting-IP") ?? "unknown";
  const ua    = request.headers.get("User-Agent") ?? "";

  if (!token || token.length !== 32) {
    return new Response("Invalid confirmation link.", { status: 400 });
  }

  const sub = await env.DB
    .prepare(`
      SELECT id, email, status, token_expires
      FROM newsletter_subscriptions
      WHERE confirm_token = ?1
    `)
    .bind(token)
    .first<{ id: string; email: string; status: string; token_expires: number }>();

  if (!sub) {
    return new Response("Confirmation link not found or already used.", { status: 404 });
  }
  if (sub.status === "confirmed") {
    return Response.redirect("https://example.com/newsletter/already-confirmed", 302);
  }
  if (sub.token_expires < Math.floor(Date.now() / 1000)) {
    return new Response("Confirmation link has expired. Please subscribe again.", { status: 410 });
  }

  // Confirm
  await env.DB.prepare(`
    UPDATE newsletter_subscriptions
    SET status = 'confirmed', confirmed_at = unixepoch(),
        confirm_token = NULL, token_expires = NULL
    WHERE id = ?1
  `).bind(sub.id).run();

  await env.DB.prepare(`
    INSERT INTO consent_audit_log (sub_id, event, ip_address, user_agent)
    VALUES (?1, 'confirmed', ?2, ?3)
  `).bind(sub.id, ip, ua).run();

  await sendWelcomeEmail(env, sub.email);

  return Response.redirect("https://example.com/newsletter/confirmed", 302);
}
```

## Send Guard — Only Confirmed Subscribers Receive Mail

Before any newsletter send, the Worker queries only `status = 'confirmed'` records. A cursor-based pagination approach batches large lists without loading the full subscriber table into memory.

```typescript
// send-newsletter.ts
export async function* confirmedSubscribers(
  db: D1Database,
  batchSize = 200
): AsyncGenerator<string[]> {
  let lastId = "";
  while (true) {
    const rows = await db
      .prepare(`
        SELECT id, email FROM newsletter_subscriptions
        WHERE status = 'confirmed' AND id > ?1
        ORDER BY id ASC
        LIMIT ?2
      `)
      .bind(lastId, batchSize)
      .all<{ id: string; email: string }>();

    if (!rows.results.length) break;
    yield rows.results.map((r) => r.email);
    lastId = rows.results[rows.results.length - 1].id;
  }
}
```

## Anti-patterns
- Sending marketing email to `pending` status addresses — double opt-in means zero email before confirmation; sending confirmation reminders to pending is fine, but newsletter content is not.
- Using a predictable token (incrementing ID, short numeric code) — tokens must be cryptographically random (UUID v4) and long enough to resist brute-force; store only in D1, not in URL fragments or cookies.
- Not expiring tokens — stale confirmation links from bot signups could be clicked by the bot owner later; 24–48 hours is the standard window.
- Revealing subscription state in the subscribe response — returning "already subscribed" leaks PII; always respond identically whether the address is new, pending, or confirmed.

## Gotchas
- Under GDPR, the consent record (confirmed_at, ip_address, user_agent) must be retained for the lifetime of the subscription plus a reasonable period; do not delete audit rows when a user unsubscribes.
- Gmail may pre-fetch confirmation links in the preview pane; the confirmation endpoint must use a one-time token that becomes invalid after first use, or the link will auto-confirm before the user clicks it — consider a two-step confirm (click → confirm button on landing page) rather than single-GET confirmation.
- D1 `UNIQUE(email)` constraint means concurrent double-submits race — use `INSERT OR IGNORE` then `UPDATE` (upsert pattern) or wrap in a D1 transaction.
- The `confirm_token` column should be indexed (`CREATE INDEX`) since it is queried on every confirmation click.

## Verification
1. Submit a valid email and confirm a `pending` row appears in D1 with a non-null `confirm_token`.
2. Click the confirmation link and verify the row transitions to `confirmed` with `confirmed_at` set, token cleared, and audit log entry written.
3. Click the same confirmation link again and verify a 404 or redirect to "already confirmed" (token is null so lookup fails).
4. Wait for token expiry (or set a short TTL in staging) and attempt confirmation; verify a 410 Gone response.
5. Run a test newsletter send and confirm only `confirmed` subscribers receive mail.

## Related
- [double-opt-in-flow.md](double-opt-in-flow.md)
- [email-consent-audit-trail-d1.md](email-consent-audit-trail-d1.md)
- [email-suppression-list-kv-workers.md](email-suppression-list-kv-workers.md)
- [one-click-unsubscribe-rfc8058-gdpr.md](one-click-unsubscribe-rfc8058-gdpr.md)
- [gdpr-email-consent.md](gdpr-email-consent.md)

## Sources
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/kv/
- https://www.rfc-editor.org/rfc/rfc6238 (TOTP, relevant for time-bound token patterns)
- https://gdpr.eu/article-7-how-can-we-get-consent/
