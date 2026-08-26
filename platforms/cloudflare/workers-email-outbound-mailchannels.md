# Outbound Email from Workers via Send Email Binding

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker needs to send transactional email — password resets, order confirmations, alert notifications — without routing through an external SMTP relay or calling a third-party API from the edge. You want to use Cloudflare's native Send Email capability tied to Email Routing so mail originates from your verified domain.

## Context

Cloudflare Workers can send email through two mechanisms:

1. **Send Email binding** (`send_email`) — the preferred approach. Wrangler declares a binding that grants the Worker permission to send from one or more verified sender addresses. Mail is handed to Cloudflare's Email Routing infrastructure, which delivers via its own MTA. No external credentials required.
2. **MailChannels HTTP API** — deprecated for new projects as of 2025. MailChannels removed the free Workers integration; use the Send Email binding instead.

The Send Email binding requires: (a) Email Routing enabled on the zone, (b) at least one verified sender address, and (c) the destination address either verified in Email Routing or unrestricted sending enabled.

---

## 1. Wrangler Configuration

```toml
# wrangler.toml
name = "mailer-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[send_email]]
name = "SEND_EMAIL"
# Optional: lock to a specific from address
from_email = "noreply@example.com"
# Optional: restrict allowed destination addresses
destination_address = "alerts@example.com"
```

For unrestricted sending (any verified recipient), omit `destination_address` and set **Send to any address** in the Email Routing dashboard.

---

## 2. TypeScript Types for the Binding

```typescript
// src/types.ts
export interface Env {
  SEND_EMAIL: SendEmail;
}

// Workers runtime provides SendEmail; declare it for TypeScript
interface SendEmail {
  send(message: EmailMessage): Promise<void>;
}

interface EmailMessage {
  from: string;
  to: string | string[];
  subject: string;
  text?: string;
  html?: string;
  // RFC 2822 raw message alternative:
  rawMessage?: ReadableStream | string;
  headers?: Record<string, string>;
}
```

---

## 3. Sending a Plain Text / HTML Email

```typescript
// src/index.ts
import { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { to, subject, text, html } = await request.json<{
      to: string;
      subject: string;
      text: string;
      html?: string;
    }>();

    if (!to || !subject || !text) {
      return Response.json({ error: "Missing required fields" }, { status: 400 });
    }

    await env.SEND_EMAIL.send({
      from: "noreply@example.com",
      to,
      subject,
      text,
      html,
    });

    return Response.json({ ok: true });
  },
} satisfies ExportedHandler<Env>;
```

---

## 4. Sending Raw RFC 2822 Messages (Attachments, Custom Headers)

The `send()` binding accepts a raw RFC 2822 message string for full MIME control, including attachments encoded as base64 MIME parts:

```typescript
import { Env } from "./types";

function buildMimeMessage(opts: {
  from: string;
  to: string;
  subject: string;
  textBody: string;
  attachmentName: string;
  attachmentBase64: string;
  attachmentMime: string;
}): string {
  const boundary = `boundary_${crypto.randomUUID().replace(/-/g, "")}`;
  return [
    `From: ${opts.from}`,
    `To: ${opts.to}`,
    `Subject: ${opts.subject}`,
    `MIME-Version: 1.0`,
    `Content-Type: multipart/mixed; boundary="${boundary}"`,
    ``,
    `--${boundary}`,
    `Content-Type: text/plain; charset=utf-8`,
    ``,
    opts.textBody,
    ``,
    `--${boundary}`,
    `Content-Type: ${opts.attachmentMime}`,
    `Content-Transfer-Encoding: base64`,
    `Content-Disposition: attachment; filename="${opts.attachmentName}"`,
    ``,
    opts.attachmentBase64,
    ``,
    `--${boundary}--`,
  ].join("\r\n");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const raw = buildMimeMessage({
      from: "reports@example.com",
      to: "cto@example.com",
      subject: "Weekly Report",
      textBody: "Please find the report attached.",
      attachmentName: "report.csv",
      attachmentBase64: btoa("date,revenue\n2026-08-23,12500"),
      attachmentMime: "text/csv",
    });

    await env.SEND_EMAIL.send({
      from: "reports@example.com",
      to: "cto@example.com",
      subject: "Weekly Report",
      rawMessage: raw,
    });

    return Response.json({ ok: true });
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. Triggered Sending from a Queue Consumer

A common pattern: a Queue consumer sends transactional mail in response to events, decoupling mail delivery from the request path:

```typescript
// wrangler.toml additions:
// [[queues.consumers]]
// queue = "transactional-mail"
// max_batch_size = 10

import { Env } from "./types";

interface MailJob {
  to: string;
  subject: string;
  text: string;
  html?: string;
}

export default {
  async queue(batch: MessageBatch<MailJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { to, subject, text, html } = msg.body;
      try {
        await env.SEND_EMAIL.send({
          from: "noreply@example.com",
          to,
          subject,
          text,
          html,
        });
        msg.ack();
      } catch (err) {
        // Retry on next batch; DLQ after maxRetries
        console.error("Mail send failed", { to, err });
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Sending mail inside `waitUntil()` without error handling** — if delivery fails silently, the caller gets a 200 and the mail is lost. Await `send()` in the main path or use a Queue.
- **Using MailChannels HTTP API** — removed from free tier; requests now 403. Migrate to Send Email binding.
- **Constructing RFC 2822 manually with `\n` instead of `\r\n`** — MIME requires CRLF line endings. `\n`-only messages fail DKIM signing and may be rejected.
- **Building HTML with string interpolation from user input** — XSS in email HTML is a phishing vector. Sanitize or use a template engine.

---

## Gotchas

- `from_email` in `wrangler.toml` must match a verified sender in Email Routing. Mismatched addresses fail at runtime with `Error: Permission denied`.
- The binding silently ignores `Reply-To` in the top-level `send()` options object — set it inside `rawMessage` headers instead.
- Rate limits: Cloudflare Email Routing is rate-limited per zone (varies by plan). For bulk sends, use a dedicated ESP and reach it via `fetch()` from the Worker.
- Email Routing must be enabled and have at least one catch-all or specific route configured even if you only send outbound — the zone association is required for the binding to resolve.
- `destination_address` in `wrangler.toml` restricts **all** sends from that binding. If you need to send to arbitrary addresses, omit it and enable unrestricted sending in the dashboard.

---

## Verification

```bash
# Deploy
wrangler deploy

# Test basic send
curl -X POST https://mailer-worker.<subdomain>.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"to":"you@yourdomain.com","subject":"Test","text":"Hello from Workers"}'

# Check delivery in Email Routing activity logs:
# Cloudflare Dashboard → Email → Email Routing → Activity

# Verify DKIM pass by inspecting received mail headers:
# Authentication-Results: dkim=pass
```

---

## Related

- `cloudflare-email-worker-inbound-advanced.md`
- `workers-email-routing.md`
- `queues-dlq-patterns.md`
- `cloudflare-queues-delayed-delivery-scheduling.md`

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/send-email-workers/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/send-email/
- https://developers.cloudflare.com/email-routing/
