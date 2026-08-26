# Email Threading: Message-ID, In-Reply-To, and References in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Users receive reply emails that appear as separate conversations instead of being
grouped into a single thread. Email clients (Gmail, Outlook, Apple Mail) use
specific headers to stitch messages into threads. Without them every reply lands
as a new top-level message.

## Context

RFC 2822 defines three headers that govern threading:

- **Message-ID** – a globally unique identifier for each message.
- **In-Reply-To** – the `Message-ID` of the message being replied to.
- **References** – the full ancestry chain of `Message-ID` values.

Cloudflare Workers can send email via MailChannels. This article shows how to
generate correct headers, persist thread chains in D1, and reconstruct the
`References` chain for deep threads.

---

## Section 1 – Generating a Compliant Message-ID

A `Message-ID` must be unique per message and follow the format
`<local-part@domain>`. Using `crypto.randomUUID()` as the local part and your
sending domain as the right-hand side is safe and collision-resistant.

```typescript
// src/lib/message-id.ts

export function generateMessageId(sendingDomain: string): string {
  const localPart = crypto.randomUUID().replace(/-/g, '');
  return `<${localPart}@${sendingDomain}>`;
}

// Example output: <a3f7c2d1b0e948f6a5c2d3e4f5a6b7c8@mail.example.com>
```

---

## Section 2 – D1 Schema for Thread Chain Tracking

Store one row per sent message. When a reply is sent, look up the parent row to
build `In-Reply-To` and `References`.

```sql
-- migrations/0001_email_threads.sql

CREATE TABLE IF NOT EXISTS email_messages (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id    TEXT    NOT NULL UNIQUE,   -- RFC 2822 Message-ID including angle brackets
  in_reply_to   TEXT,                      -- parent Message-ID, NULL for root
  references    TEXT,                      -- space-separated ancestor chain
  subject       TEXT    NOT NULL,
  recipient     TEXT    NOT NULL,
  sent_at       INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_email_messages_message_id ON email_messages(message_id);
```

```typescript
// src/lib/thread-store.ts

export interface ThreadRow {
  message_id: string;
  in_reply_to: string | null;
  references: string | null;
}

export async function getThreadRow(
  db: D1Database,
  messageId: string
): Promise<ThreadRow | null> {
  const result = await db
    .prepare('SELECT message_id, in_reply_to, references FROM email_messages WHERE message_id = ?')
    .bind(messageId)
    .first<ThreadRow>();
  return result ?? null;
}

export async function insertThreadRow(
  db: D1Database,
  row: { messageId: string; inReplyTo: string | null; references: string | null; subject: string; recipient: string }
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO email_messages (message_id, in_reply_to, references, subject, recipient)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(row.messageId, row.inReplyTo, row.references, row.subject, row.recipient)
    .run();
}
```

---

## Section 3 – Building Threading Headers and Sending

```typescript
// src/lib/threaded-send.ts

import { generateMessageId } from './message-id';
import { getThreadRow, insertThreadRow } from './thread-store';

export interface SendOptions {
  db: D1Database;
  sendingDomain: string;
  fromAddress: string;
  fromName: string;
  toAddress: string;
  subject: string;
  textBody: string;
  htmlBody: string;
  /** Message-ID of the message being replied to, if any */
  parentMessageId?: string;
}

export async function sendThreadedEmail(opts: SendOptions): Promise<void> {
  const {
    db, sendingDomain, fromAddress, fromName,
    toAddress, subject, textBody, htmlBody, parentMessageId,
  } = opts;

  const newMessageId = generateMessageId(sendingDomain);

  let inReplyTo: string | null = null;
  let references: string | null = null;

  if (parentMessageId) {
    const parentRow = await getThreadRow(db, parentMessageId);
    inReplyTo = parentMessageId;

    // References = parent's References + parent's Message-ID
    const ancestorRefs = parentRow?.references ?? null;
    references = ancestorRefs
      ? `${ancestorRefs} ${parentMessageId}`
      : parentMessageId;
  }

  // Build additional headers
  const extraHeaders: Record<string, string> = {
    'Message-ID': newMessageId,
  };
  if (inReplyTo) extraHeaders['In-Reply-To'] = inReplyTo;
  if (references) extraHeaders['References'] = references;

  const payload = {
    personalizations: [{ to: [{ email: toAddress }] }],
    from: { email: fromAddress, name: fromName },
    subject,
    content: [
      { type: 'text/plain', value: textBody },
      { type: 'text/html', value: htmlBody },
    ],
    headers: extraHeaders,
  };

  const response = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`MailChannels send failed: ${response.status} ${text}`);
  }

  // Persist to D1 for future replies
  await insertThreadRow(db, {
    messageId: newMessageId,
    inReplyTo,
    references,
    subject,
    recipient: toAddress,
  });
}
```

---

## Section 4 – Worker Handler

```typescript
// src/index.ts

import { sendThreadedEmail } from './lib/threaded-send';

export interface Env {
  DB: D1Database;
  SENDING_DOMAIN: string;
  FROM_ADDRESS: string;
  FROM_NAME: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.json<{
      to: string;
      subject: string;
      text: string;
      html: string;
      parentMessageId?: string;
    }>();

    await sendThreadedEmail({
      db: env.DB,
      sendingDomain: env.SENDING_DOMAIN,
      fromAddress: env.FROM_ADDRESS,
      fromName: env.FROM_NAME,
      toAddress: body.to,
      subject: body.subject,
      textBody: body.text,
      htmlBody: body.html,
      parentMessageId: body.parentMessageId,
    });

    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Anti-patterns

- **Reusing the same `Message-ID`** across messages – breaks threading immediately.
- **Omitting `References`** and only setting `In-Reply-To` – Gmail groups correctly
  but Outlook may not for threads deeper than two.
- **Using timestamps alone** as the local part of `Message-ID` – collisions are
  possible under high concurrency.
- **Not persisting sent `Message-ID` values** – makes it impossible to reconstruct
  `References` for future replies.

## Gotchas

- MailChannels strips unknown headers silently; verify threading headers appear
  in the raw message source in your email client.
- The `References` header can grow large for very long threads. RFC 5322 allows
  folding long header lines with CRLF + whitespace.
- D1 `unixepoch()` returns seconds, not milliseconds.
- Workers do not have a native `nodemailer` equivalent; all MIME construction is
  manual or via MailChannels' JSON API.

## Verification

```bash
# Send a root message and capture its Message-ID
curl -X POST https://your-worker.example.com/ \
  -H 'Content-Type: application/json' \
  -d '{"to":"test@example.com","subject":"Thread test","text":"Root","html":"<p>Root</p>"}'

# Reply to it using the returned / stored Message-ID
curl -X POST https://your-worker.example.com/ \
  -H 'Content-Type: application/json' \
  -d '{"to":"test@example.com","subject":"Re: Thread test","text":"Reply","html":"<p>Reply</p>","parentMessageId":"<abc123@mail.example.com>"}'

# Verify the DB chain
wrangler d1 execute MY_DB --command \
  "SELECT message_id, in_reply_to, references FROM email_messages ORDER BY sent_at;"
```

## Related

- `workers-email-multipart-mime-builder.md`
- `workers-email-scheduled-digest-cron.md`
- `workers-email-rate-limit-per-recipient.md`

## Sources

- RFC 2822 §3.6.4 – Identification fields
- RFC 5322 §3.6.4 – Message-ID / References
- https://developers.cloudflare.com/d1/
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413
