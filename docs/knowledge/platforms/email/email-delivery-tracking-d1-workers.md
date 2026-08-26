# Transactional Email Delivery Tracking via D1 and Email Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You send transactional emails — receipts, password resets, shipping notifications — through MailChannels or an SMTP relay, but have no internal record of which messages were sent, which addresses hard-bounced, or aggregate delivery success rates broken down by template.

---

## Context

A complete D1-backed delivery tracking system has two halves:

1. **Outbound logging** — when the Worker sends an email via MailChannels, it writes a record to D1 with status `sent` and stores the RFC 5322 `Message-ID` header it injected
2. **Inbound DSN processing** — a dedicated Email Routing Worker receives Delivery Status Notifications (DSNs) sent to `bounces@yourdomain.com`, parses the `message/delivery-status` MIME part, correlates the original `Message-ID`, and updates the D1 record's status

DSNs are standardised in RFC 3461/3462. The `Action` field in the DSN describes the outcome (`failed`, `delayed`, `delivered`, `relayed`, `expanded`).

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS email_deliveries (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id    TEXT    NOT NULL UNIQUE,
  recipient     TEXT    NOT NULL,
  template_slug TEXT    NOT NULL,
  subject       TEXT,
  status        TEXT    NOT NULL DEFAULT 'sent',
  bounce_code   TEXT,
  bounce_reason TEXT,
  sent_at       TEXT    NOT NULL,
  updated_at    TEXT    NOT NULL
);

CREATE INDEX idx_del_message_id ON email_deliveries(message_id);
CREATE INDEX idx_del_recipient  ON email_deliveries(recipient);
CREATE INDEX idx_del_status     ON email_deliveries(status);
CREATE INDEX idx_del_template   ON email_deliveries(template_slug, status);
```

---

## Outbound Send with D1 Logging

```typescript
export async function sendTracked(env: Env, params: SendParams): Promise<string> {
  const messageId = `<${crypto.randomUUID()}@yourdomain.com>`;
  const now = new Date().toISOString();

  // Insert BEFORE sending so the record always exists when a DSN arrives
  await env.DB.prepare(
    `INSERT INTO email_deliveries
     (message_id, recipient, template_slug, subject, status, sent_at, updated_at)
     VALUES (?, ?, ?, ?, 'sent', ?, ?)`
  ).bind(messageId, params.to, params.templateSlug, params.subject, now, now).run();

  const response = await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [{
        to: [{ email: params.to }],
        dkim_domain: "yourdomain.com",
        dkim_selector: "mailchannels",
        dkim_private_key: env.DKIM_PRIVATE_KEY,
      }],
      from: { email: params.fromEmail },
      subject: params.subject,
      content: [{ type: "text/html", value: params.html }],
      headers: {
        "Message-ID": messageId,
        "Return-Path": "bounces@yourdomain.com",
      },
    }),
  });

  if (!response.ok) {
    await env.DB.prepare(
      `UPDATE email_deliveries SET status = 'send_failed', updated_at = ? WHERE message_id = ?`
    ).bind(new Date().toISOString(), messageId).run();
    throw new Error(`MailChannels ${response.status}`);
  }

  return messageId;
}
```

---

## DSN Email Worker: Parse and Correlate

```typescript
import PostalMime from "postal-mime";
import type { EmailMessage } from "cloudflare:email";

export default {
  async email(message: EmailMessage, env: { DB: D1Database }, ctx: ExecutionContext) {
    const contentType = message.headers.get("Content-Type") ?? "";
    if (!contentType.toLowerCase().includes("multipart/report")) return;

    const rawBuffer = await new Response(message.raw).arrayBuffer();
    const parsed = await new PostalMime().parse(rawBuffer);

    const dsnPart = parsed.attachments?.find(
      (a) => a.mimeType?.toLowerCase() === "message/delivery-status"
    );
    if (!dsnPart) return;

    const dsnText = new TextDecoder().decode(dsnPart.content);
    const originalMessageId = extractField(dsnText, "Original-Message-ID");
    const action = extractField(dsnText, "Action")?.toLowerCase();
    const statusCode = extractField(dsnText, "Status");
    const diagnostic = extractField(dsnText, "Diagnostic-Code");

    if (!originalMessageId || !action || !statusCode) return;

    ctx.waitUntil(
      updateDeliveryStatus(env, originalMessageId, action, statusCode, diagnostic ?? null)
    );
  },
};

function extractField(dsnText: string, field: string): string | null {
  const match = dsnText.match(new RegExp(`^${field}:\\s*(.+)$`, "im"));
  return match ? match[1].trim() : null;
}

async function updateDeliveryStatus(
  env: { DB: D1Database },
  messageId: string,
  action: string,
  statusCode: string,
  diagnostic: string | null
): Promise<void> {
  let status: string;
  if (action === "delivered") status = "delivered";
  else if (action === "failed") status = statusCode.startsWith("5") ? "bounced_hard" : "bounced_soft";
  else if (action === "delayed") status = "deferred";
  else status = `dsn_${action}`;

  try {
    await env.DB.prepare(
      `UPDATE email_deliveries SET status = ?, bounce_code = ?, bounce_reason = ?, updated_at = ? WHERE message_id = ?`
    ).bind(status, statusCode, diagnostic, new Date().toISOString(), messageId).run();
  } catch (err) {
    console.error("D1 update failed for", messageId, err);
  }
}
```

---

## Delivery Stats and Suppression

```typescript
export async function getDeliveryStats(
  env: Env,
  templateSlug: string,
  sinceHours: number
): Promise<{ status: string; count: number; pct: number }[]> {
  const since = new Date(Date.now() - sinceHours * 3_600_000).toISOString();

  const result = await env.DB.prepare(
    `SELECT
       status,
       COUNT(*) AS count,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
     FROM email_deliveries
     WHERE template_slug = ? AND sent_at >= ?
     GROUP BY status
     ORDER BY count DESC`
  ).bind(templateSlug, since).all<{ status: string; count: number; pct: number }>();

  return result.results;
}

export async function isSuppressed(env: Env, recipient: string): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM email_deliveries WHERE recipient = ? AND status = 'bounced_hard' LIMIT 1`
  ).bind(recipient).first();
  return row !== null;
}
```

---

## Anti-patterns

- **Storing the full HTML body in D1** — D1 is not a blob store. Archive message bodies in R2 if needed.
- **Polling the ESP API for bounce events** — polling is slow and rate-limited. DSN-based processing works at the SMTP protocol layer.
- **Using a random UUID as `message_id` at query time** — the `Message-ID` must be set before the send and stored in D1.
- **Treating `status = delivered` as inbox delivery** — DSN `delivered` means the remote MTA accepted the message, not that it reached the inbox.

---

## Gotchas

- Not all receiving MTAs generate DSNs. Gmail issues DSNs only for hard bounces.
- The `Return-Path` set in the outbound send must match the address bound to the DSN Worker in Email Routing.
- A `UNIQUE` constraint violation on `message_id` (e.g. duplicate DSN) throws a `D1_ERROR`. Wrap `INSERT` statements in try/catch.

---

## Verification

```bash
wrangler d1 execute email-delivery --file=schema.sql
wrangler deploy --name dsn-processor src/bounce-worker.ts

wrangler d1 execute email-delivery \
  --command "SELECT message_id, status, bounce_code, bounce_reason FROM email_deliveries ORDER BY updated_at DESC LIMIT 10"
```

---

## Related

- `email-transactional-idempotency-workers-d1.md`
- `bounce-handling-hard-soft.md`
- `email-suppression-list-kv-workers.md`

---

## Sources

- RFC 3461 — SMTP Service Extension for Delivery Status Notifications — https://datatracker.ietf.org/doc/html/rfc3461
- RFC 3463 — Enhanced Mail System Status Codes — https://datatracker.ietf.org/doc/html/rfc3463
- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
