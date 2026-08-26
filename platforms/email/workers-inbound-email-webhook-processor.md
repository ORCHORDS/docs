# Processing Inbound Email as Webhooks in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You receive support, billing, and abuse emails at a shared inbox and need them automatically routed into a ticketing system without a dedicated mail server. Cloudflare Email Routing can forward inbound email to a Worker's `email` handler, where the message is parsed, categorised, queued, and auto-acknowledged within milliseconds.

---

## Context
Cloudflare Email Routing delivers inbound messages to a Worker's `email(message, env, ctx)` handler via the `EmailMessage` interface. The Worker inspects `message.from`, `message.to`, and `message.headers` to parse the subject. Based on subject keywords (`[BILLING]`, `[ABUSE]`, or the default `support`), the message is dispatched to a dedicated Cloudflare Queue. A Queue consumer creates a D1 ticket row and sends an auto-reply via MailChannels confirming receipt with a ticket ID. This keeps the email handler fast and non-blocking — the heavy lifting happens asynchronously in the consumer.

---

## Section 1 — D1 Schema, Queues & Wrangler Config

```sql
-- migrations/0001_tickets.sql
CREATE TABLE IF NOT EXISTS tickets (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  queue_name  TEXT NOT NULL,
  from_email  TEXT NOT NULL,
  subject     TEXT NOT NULL,
  body_text   TEXT,
  status      TEXT NOT NULL DEFAULT 'open',
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_tickets_queue  ON tickets(queue_name, status);
CREATE INDEX IF NOT EXISTS idx_tickets_from   ON tickets(from_email);
```

```toml
# wrangler.toml
name = "inbound-email-processor"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
FROM_EMAIL = "support@example.com"

[[d1_databases]]
binding       = "DB"
database_name = "tickets-db"
database_id   = "<your-d1-database-id>"

[[queues.producers]]
binding = "QUEUE_SUPPORT"
queue   = "inbound-support"

[[queues.producers]]
binding = "QUEUE_BILLING"
queue   = "inbound-billing"

[[queues.producers]]
binding = "QUEUE_ABUSE"
queue   = "inbound-abuse"

[[queues.consumers]]
queue           = "inbound-support"
max_batch_size  = 5
max_batch_timeout = 10

[[queues.consumers]]
queue           = "inbound-billing"
max_batch_size  = 5
max_batch_timeout = 10

[[queues.consumers]]
queue           = "inbound-abuse"
max_batch_size  = 5
max_batch_timeout = 10
```

---

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  QUEUE_SUPPORT: Queue<InboundEmailMessage>;
  QUEUE_BILLING: Queue<InboundEmailMessage>;
  QUEUE_ABUSE:   Queue<InboundEmailMessage>;
  FROM_EMAIL: string;
}

interface InboundEmailMessage {
  from:      string;
  to:        string;
  subject:   string;
  bodyText:  string;
  queueName: 'support' | 'billing' | 'abuse';
}

function classifyBySubject(subject: string): 'billing' | 'abuse' | 'support' {
  const lower = subject.toLowerCase();
  if (lower.includes('[billing]') || lower.includes('invoice') || lower.includes('payment')) {
    return 'billing';
  }
  if (lower.includes('[abuse]') || lower.includes('spam') || lower.includes('phishing')) {
    return 'abuse';
  }
  return 'support';
}

async function readBodyText(message: ForwardableEmailMessage): Promise<string> {
  // EmailMessage.raw is a ReadableStream of the full RFC 5322 message.
  // For production MIME parsing, use the postal-mime package.
  const raw = await new Response(message.raw).text();
  const blankLine = raw.indexOf('\r\n\r\n');
  if (blankLine === -1) return raw.slice(0, 2000);
  return raw.slice(blankLine + 4, blankLine + 4 + 4000);
}

async function sendAutoReply(
  fromEmail: string,
  toEmail: string,
  ticketId: string,
  queueName: string
): Promise<void> {
  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: toEmail }] }],
      from: { email: fromEmail },
      subject: `[Ticket #${ticketId.slice(0, 8).toUpperCase()}] We received your message`,
      content: [
        {
          type: 'text/html',
          value: `
            <p>Hi,</p>
            <p>Thanks for contacting Orchords. Your message has been received and assigned to our
            <strong>${queueName}</strong> team.</p>
            <p>Ticket ID: <code>${ticketId}</code></p>
            <p>We aim to respond within 1 business day.</p>
          `,
        },
      ],
    }),
  });
}

async function processQueuedEmail(
  env: Env,
  message: Message<InboundEmailMessage>
): Promise<void> {
  const { from, subject, bodyText, queueName } = message.body;
  const ticketId = crypto.randomUUID();

  await env.DB
    .prepare(
      `INSERT INTO tickets (id, queue_name, from_email, subject, body_text)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(ticketId, queueName, from, subject, bodyText)
    .run();

  await sendAutoReply(env.FROM_EMAIL, from, ticketId, queueName);
  message.ack();
}

export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    const from    = message.from;
    const to      = message.to;
    const subject = message.headers.get('subject') ?? '(no subject)';
    const bodyText = await readBodyText(message);
    const queueName = classifyBySubject(subject);

    const payload: InboundEmailMessage = { from, to, subject, bodyText, queueName };

    const queueMap = {
      support: env.QUEUE_SUPPORT,
      billing: env.QUEUE_BILLING,
      abuse:   env.QUEUE_ABUSE,
    } as const;

    ctx.waitUntil(queueMap[queueName].send(payload));
  },

  async queue(batch: MessageBatch<InboundEmailMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      await processQueuedEmail(env, message);
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Email Routing Setup & Testing

```bash
# 1. Enable Email Routing in the Cloudflare dashboard for your domain.
# 2. Add a catch-all rule:
#    Dashboard -> Email -> Email Routing -> Routing Rules
#    Action: "Send to a Worker", Worker: inbound-email-processor

# 3. Apply D1 migration
npx wrangler d1 execute tickets-db --file=migrations/0001_tickets.sql

# 4. Deploy
npx wrangler deploy

# 5. Send a test email
# Subject: [BILLING] Invoice question
# To: billing@yourdomain.com

# 6. Confirm ticket
npx wrangler d1 execute tickets-db \
  --command "SELECT id, queue_name, from_email, subject, status FROM tickets ORDER BY created_at DESC LIMIT 5"

# 7. Tail logs
npx wrangler tail inbound-email-processor
```

```typescript
// test/classify.test.ts
import { describe, it, expect } from 'vitest';

function classifyBySubject(subject: string): string {
  const lower = subject.toLowerCase();
  if (lower.includes('[billing]') || lower.includes('invoice') || lower.includes('payment')) return 'billing';
  if (lower.includes('[abuse]') || lower.includes('spam') || lower.includes('phishing'))    return 'abuse';
  return 'support';
}

describe('classifyBySubject', () => {
  it('routes billing keywords to billing queue', () => {
    expect(classifyBySubject('[BILLING] Invoice #123')).toBe('billing');
    expect(classifyBySubject('Payment failed')).toBe('billing');
  });
  it('routes abuse keywords to abuse queue', () => {
    expect(classifyBySubject('[ABUSE] Phishing report')).toBe('abuse');
    expect(classifyBySubject('This is spam')).toBe('abuse');
  });
  it('defaults to support', () => {
    expect(classifyBySubject('Hello!')).toBe('support');
  });
});
```

---

## Anti-patterns
- **Doing heavy work inside the `email` handler** — The `email` handler has a tight CPU time budget; defer parsing, DB writes, and outbound HTTP to a Queue consumer via `ctx.waitUntil`.
- **Reading `message.raw` twice** — `raw` is a `ReadableStream` and can only be consumed once; if you need to both parse and forward, `tee()` the stream first.
- **Forwarding all email to one queue** — Using a single queue for all inbound categories mixes SLAs; separate queues let you scale billing/abuse consumers independently.
- **Not acknowledging queue messages** — If you omit `message.ack()` after a successful DB insert, the consumer retries the same message and creates duplicate tickets.

---

## Gotchas
- The `email` handler only fires when Cloudflare Email Routing is configured on your domain; it does not receive emails sent directly to a Worker URL.
- `message.headers` returns the email headers as a `Headers` object; the subject is in the `subject` (lowercase) header key.
- `message.raw` is the full RFC 5322 message including MIME boundaries; for HTML emails or attachments, use the `postal-mime` npm package to parse properly.
- Email Routing catch-all rules only activate when no more-specific matching rule fires first; order your Routing Rules carefully to avoid swallowing emails meant for real inboxes.
- MailChannels auto-reply requires SPF/DKIM alignment on your `FROM_EMAIL` domain to avoid the auto-reply being marked as spam.

---

## Verification

```bash
# Open ticket count by queue
npx wrangler d1 execute tickets-db \
  --command "SELECT queue_name, COUNT(*) n FROM tickets WHERE status='open' GROUP BY queue_name"

# Recent tickets
npx wrangler d1 execute tickets-db \
  --command "SELECT id, queue_name, from_email, subject, created_at FROM tickets ORDER BY created_at DESC LIMIT 10"

# Tail live logs
npx wrangler tail inbound-email-processor --format pretty
```

---

## Related
- `workers-transactional-email-d1-audit.md`
- `workers-email-list-management-d1.md`

---

## Sources
- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- EmailMessage API — https://developers.cloudflare.com/email-routing/email-workers/runtime-api/
- postal-mime MIME parser — https://github.com/postalsys/postal-mime
- MailChannels API — https://api.mailchannels.net/tx/v1/documentation
