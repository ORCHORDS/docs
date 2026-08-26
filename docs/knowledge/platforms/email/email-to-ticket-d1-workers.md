# Email-to-Ticket Conversion with D1 Storage Using Email Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team receives support requests at `support@yourdomain.com`. You need to:

- Automatically create a D1 ticket record for every new inbound email
- Detect reply emails (via `In-Reply-To` / `References` headers) and append them to the existing ticket thread
- Extract only the new reply text, excluding quoted history
- Store file attachments in R2 and link them to the ticket
- Send an auto-reply with the assigned ticket ID
- Prevent reply-loops when the auto-reply itself triggers the Worker

---

## Context

The Email Worker is bound to `support@yourdomain.com` via an Email Routing specific address rule. The Worker parses the `In-Reply-To` header to find a previously issued ticket ID embedded in the `Message-ID` header of the auto-reply:

```
Message-ID: <ticket-42.reply@support.yourdomain.com>
```

The `ticket-42` portion encodes the ticket ID. When a recipient replies, their client includes `In-Reply-To: <ticket-42.reply@support.yourdomain.com>`, allowing the Worker to resolve the thread without a database lookup by subject line.

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS tickets (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  subject     TEXT    NOT NULL,
  from_addr   TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'open',
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_messages (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id    INTEGER NOT NULL REFERENCES tickets(id),
  message_id   TEXT    NOT NULL UNIQUE,
  from_addr    TEXT    NOT NULL,
  body_text    TEXT,
  raw_size     INTEGER,
  received_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_attachments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id  TEXT    NOT NULL REFERENCES ticket_messages(message_id),
  filename    TEXT    NOT NULL,
  mime_type   TEXT    NOT NULL,
  r2_key      TEXT    NOT NULL,
  size_bytes  INTEGER NOT NULL,
  stored_at   TEXT    NOT NULL
);
```

---

## Worker Entry Point

```typescript
import PostalMime from "postal-mime";
import type { EmailMessage } from "cloudflare:email";

interface Env {
  DB: D1Database;
  ATTACHMENTS: R2Bucket;
  DKIM_PRIVATE_KEY: string;
  FROM_ADDRESS: string;
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const autoSubmitted = message.headers.get("Auto-Submitted") ?? "";
    const xAutoReply = message.headers.get("X-Auto-Reply-Key") ?? "";
    if (autoSubmitted !== "no" && autoSubmitted !== "" || xAutoReply === "support-bot") {
      return;
    }

    const rawBuffer = await new Response(message.raw).arrayBuffer();
    const parsed = await new PostalMime().parse(rawBuffer);
    const messageId = message.headers.get("Message-ID") ?? `<${crypto.randomUUID()}@unknown>`;
    const inReplyTo = message.headers.get("In-Reply-To") ?? "";
    const references = message.headers.get("References") ?? "";

    const existingTicketId = resolveTicketIdFromHeader(inReplyTo) ??
                             resolveTicketIdFromHeader(references);

    if (existingTicketId) {
      await appendToTicket(existingTicketId, messageId, message, parsed, env);
    } else {
      const newTicketId = await createTicket(messageId, message, parsed, env);
      ctx.waitUntil(sendAutoReply(newTicketId, message, env));
    }
  },
};

function resolveTicketIdFromHeader(headerValue: string): number | null {
  const match = headerValue.match(/<ticket-(\d+)\.reply@/);
  return match ? parseInt(match[1], 10) : null;
}
```

---

## Create New Ticket

```typescript
async function createTicket(
  messageId: string,
  message: EmailMessage,
  parsed: Awaited<ReturnType<PostalMime["parse"]>>,
  env: Env
): Promise<number> {
  const now = new Date().toISOString();
  const subject = message.headers.get("Subject") ?? "(no subject)";
  const bodyText = extractNewReplyText(parsed.text ?? "");

  const ticketRow = await env.DB.prepare(
    `INSERT INTO tickets (subject, from_addr, status, created_at, updated_at)
     VALUES (?, ?, 'open', ?, ?) RETURNING id`
  )
    .bind(subject, message.from, now, now)
    .first<{ id: number }>();

  if (!ticketRow) throw new Error("Failed to create ticket");
  const ticketId = ticketRow.id;

  await env.DB.prepare(
    `INSERT INTO ticket_messages (ticket_id, message_id, from_addr, body_text, raw_size, received_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(ticketId, messageId, message.from, bodyText, parsed.attachments?.length ?? 0, now)
    .run();

  await storeAttachments(messageId, parsed, env);
  return ticketId;
}
```

---

## Append Reply to Existing Ticket

```typescript
async function appendToTicket(
  ticketId: number,
  messageId: string,
  message: EmailMessage,
  parsed: Awaited<ReturnType<PostalMime["parse"]>>,
  env: Env
): Promise<void> {
  const now = new Date().toISOString();
  const bodyText = extractNewReplyText(parsed.text ?? "");

  const existing = await env.DB.prepare(
    `SELECT id FROM ticket_messages WHERE message_id = ?`
  ).bind(messageId).first();
  if (existing) return;

  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO ticket_messages (ticket_id, message_id, from_addr, body_text, raw_size, received_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(ticketId, messageId, message.from, bodyText, 0, now),
    env.DB.prepare(
      `UPDATE tickets SET updated_at = ?, status = 'open' WHERE id = ?`
    ).bind(now, ticketId),
  ]);

  await storeAttachments(messageId, parsed, env);
}

function extractNewReplyText(fullText: string): string {
  return fullText
    .split("\n")
    .filter((line) => !line.startsWith(">"))
    .join("\n")
    .split(/^--\s*$/m)[0]
    .trim();
}
```

---

## Auto-Reply via MailChannels

```typescript
async function sendAutoReply(
  ticketId: number,
  original: EmailMessage,
  env: Env
): Promise<void> {
  const autoMessageId = `<ticket-${ticketId}.reply@support.yourdomain.com>`;
  const subject = `Re: ${original.headers.get("Subject") ?? "(no subject)"}`;

  await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      personalizations: [{
        to: [{ email: original.from }],
        dkim_domain: "yourdomain.com",
        dkim_selector: "mailchannels",
        dkim_private_key: env.DKIM_PRIVATE_KEY,
      }],
      from: { email: env.FROM_ADDRESS, name: "Support" },
      subject,
      content: [{
        type: "text/plain",
        value: `Your support request has been received and assigned ticket #${ticketId}.\n\nReply to this email to add more information.\n\nTicket #${ticketId}`,
      }],
      headers: {
        "Message-ID": autoMessageId,
        "In-Reply-To": original.headers.get("Message-ID") ?? "",
        "Auto-Submitted": "auto-replied",
        "X-Auto-Reply-Key": "support-bot",
      },
    }),
  });
}
```

---

## Anti-patterns

- **Matching tickets by subject line** — subjects change between replies and are not globally unique. Use `In-Reply-To` / `References` with a structured `Message-ID` scheme instead.
- **Storing raw MIME in D1** — raw messages can be several megabytes. Store body text in D1 and binary attachments in R2.
- **Sending an auto-reply to every email, including `noreply@` senders** — check that the sender domain accepts replies and that `Auto-Submitted` is not set before sending.
- **Not stripping quoted history from `body_text`** — each reply will accumulate the entire prior conversation.

---

## Gotchas

- Some email clients (particularly Outlook) do not include `In-Reply-To` when replying. Fall back to matching the first `<ticket-N.reply@...>` reference in the `References` header chain.
- Workers D1 `UNIQUE` constraint on `message_id` prevents duplicate messages if Email Routing delivers the same message twice. Treat the constraint violation as a no-op.
- The `Auto-Submitted: auto-replied` header is checked to prevent loops; also check that the `from` address is not your own support address.

---

## Verification

```bash
# Apply schema
wrangler d1 execute support-tickets --file=schema.sql

# Deploy Worker
wrangler deploy --name email-to-ticket src/index.ts

# Send a new support email
swaks --from customer@gmail.com --to support@yourdomain.com \
  --header "Subject: My order never arrived" \
  --body "Hi, I placed order #12345 three weeks ago."

# Verify ticket was created
wrangler d1 execute support-tickets \
  --command "SELECT t.id, t.subject, t.from_addr, t.status FROM tickets t ORDER BY id DESC LIMIT 5"
```

---

## Related

- `email-reply-to-thread-matching-d1.md`
- `email-conversation-threading-d1-workers.md`
- `email-forwarding-loop-detection-d1-workers.md`
- `email-auto-responder-out-of-office-d1-workers.md`

---

## Sources

- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- PostalMime npm — https://www.npmjs.com/package/postal-mime
- MailChannels Transactional API — https://api.mailchannels.net/tx/v1/documentation
