# Email Reply-to-Thread Matching via Message-ID in D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Inbound emails sent through Cloudflare Email Routing need to be correlated back to
the originating outbound message so support tickets, conversation threads, and
notification replies land in the correct thread. Without this, every inbound
message is treated as a new conversation.

## Context

SMTP threading relies on two headers: `Message-ID` (set on every outbound message)
and `In-Reply-To` / `References` (set by mail clients when replying). A D1 table
acts as the lookup index: outbound sends write their `Message-ID`; inbound Email
Workers read `In-Reply-To` and `References` to find the matching thread. This
avoids an external database hop and keeps everything on Cloudflare's network.

## D1 Schema

```sql
-- Migration 001
CREATE TABLE IF NOT EXISTS message_index (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id   TEXT    NOT NULL UNIQUE,   -- the RFC 5322 Message-ID value
  thread_id    TEXT    NOT NULL,           -- your application thread/ticket ID
  subject      TEXT,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_message_id ON message_index(message_id);
CREATE INDEX IF NOT EXISTS idx_thread_id  ON message_index(thread_id);
```

## Outbound: Recording Message-IDs

When sending via MailChannels, SendGrid, or any SMTP relay from a Worker, store
the generated `Message-ID` alongside your thread ID before (or immediately after)
dispatch:

```typescript
// send-worker/index.ts
import { Env } from './types';

export interface ThreadedMessage {
  threadId: string;
  to: string;
  subject: string;
  html: string;
  text: string;
}

function generateMessageId(domain: string): string {
  const random = crypto.randomUUID().replace(/-/g, '');
  return `<${random}@${domain}>`;
}

export async function sendThreadedEmail(
  env: Env,
  msg: ThreadedMessage,
): Promise<string> {
  const messageId = generateMessageId('mail.example.com');

  // Record in D1 BEFORE sending so a fast reply never races ahead
  await env.DB.prepare(
    `INSERT OR IGNORE INTO message_index (message_id, thread_id, subject)
     VALUES (?, ?, ?)`,
  ).bind(messageId, msg.threadId, msg.subject).run();

  // MailChannels send
  const payload = {
    personalizations: [{ to: [{ email: msg.to }] }],
    from: { email: 'support@example.com', name: 'Support' },
    subject: msg.subject,
    content: [
      { type: 'text/plain', value: msg.text },
      { type: 'text/html',  value: msg.html },
    ],
    headers: {
      'Message-ID': messageId,
      'X-Thread-ID': msg.threadId,
    },
  };

  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    // Roll back the D1 insert on send failure to avoid phantom entries
    await env.DB.prepare(
      'DELETE FROM message_index WHERE message_id = ?',
    ).bind(messageId).run();
    throw new Error(`Send failed: ${res.status}`);
  }

  return messageId;
}
```

## Inbound: Resolving Reply to Thread

The Email Worker receives inbound mail via the `email` handler. Parse
`In-Reply-To` and `References` headers, then look up each candidate in D1:

```typescript
// email-worker/index.ts
import { EmailMessage } from 'cloudflare:email';
import { Env } from './types';

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    const inReplyTo = message.headers.get('in-reply-to') ?? '';
    const references = message.headers.get('references') ?? '';

    // Build candidate list: In-Reply-To first (most specific), then References
    const candidates = [
      ...parseMessageIds(inReplyTo),
      ...parseMessageIds(references),
    ];

    let threadId: string | null = null;

    for (const candidate of candidates) {
      const row = await env.DB.prepare(
        'SELECT thread_id FROM message_index WHERE message_id = ? LIMIT 1',
      ).bind(candidate).first<{ thread_id: string }>();

      if (row) {
        threadId = row.thread_id;
        break;
      }
    }

    if (!threadId) {
      // New conversation — create a thread
      threadId = crypto.randomUUID();
    }

    // Index this inbound message so further replies chain correctly
    const inboundMsgId = message.headers.get('message-id');
    if (inboundMsgId) {
      await env.DB.prepare(
        `INSERT OR IGNORE INTO message_index (message_id, thread_id, subject)
         VALUES (?, ?, ?)`,
      ).bind(inboundMsgId, threadId, message.headers.get('subject') ?? '').run();
    }

    // Route to your application
    await routeToThread(env, threadId, message);
  },
};

function parseMessageIds(header: string): string[] {
  // RFC 5322 Message-IDs are wrapped in angle brackets
  return [...header.matchAll(/<([^>]+)>/g)].map(m => `<${m[1]}>`);
}

async function routeToThread(
  env: Env,
  threadId: string,
  message: EmailMessage,
): Promise<void> {
  await env.QUEUE.send({
    threadId,
    from: message.from,
    subject: message.headers.get('subject'),
    receivedAt: Date.now(),
  });
}
```

## Anti-patterns

- **Matching only on subject line** (`Re: …`) — subject-based matching is fragile;
  users change subjects, mail clients strip prefixes, and collision rate is high.
- **Storing raw `References` chains without parsing** — the References header can
  list dozens of Message-IDs; querying by the full string always misses.
- **Not storing Message-IDs before sending** — a fast reply can arrive before the
  post-send DB write, creating orphan threads.
- **Ignoring thread expiry** — D1 rows accumulate; add a TTL column and a
  scheduled Worker to prune entries older than your SLA window (e.g. 90 days).

## Gotchas

- `message.headers.get()` in Cloudflare Email Workers is case-insensitive per the
  API but the actual header name from `parseMessageIds()` must match the stored
  format (angle brackets included).
- MailChannels may rewrite `Message-ID` if the value looks malformed — test with
  their sandbox before relying on custom IDs.
- `INSERT OR IGNORE` silently swallows duplicate `message_id` conflicts; switch to
  `ON CONFLICT DO UPDATE` if you need to update `thread_id` on collision.
- References can contain Message-IDs from external senders whose IDs are never in
  your D1; always fall through the full list before treating mail as a new thread.

## Verification

```bash
# 1. Send a test email from your outbound Worker, capture the Message-ID from D1
wrangler d1 execute DB --command \
  "SELECT message_id, thread_id FROM message_index ORDER BY id DESC LIMIT 5"

# 2. Simulate an inbound reply with curl (Email Workers local dev)
wrangler dev --local
# Send a raw MIME message with In-Reply-To set to the captured Message-ID

# 3. Confirm the inbound row shares the same thread_id
wrangler d1 execute DB --command \
  "SELECT message_id, thread_id FROM message_index ORDER BY id DESC LIMIT 5"
```

## Related

- `email-conversation-threading-d1-workers.md`
- `email-threading-references-in-reply-to.md`
- `workers-email-reply-parsing-thread-detection.md`
- `email-transactional-idempotency-workers-d1.md`
- `cloudflare-email-routing-workers.md`

## Sources

- RFC 5322 §3.6.4 — Identification Fields (Message-ID, In-Reply-To, References)
- Cloudflare Email Workers API: https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- MailChannels Send API: https://api.mailchannels.net/tx/v1/documentation
