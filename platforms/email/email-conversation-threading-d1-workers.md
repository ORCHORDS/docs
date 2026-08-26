# Email Conversation Threading with D1 on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Inbound email Workers receive individual messages but have no built-in concept of a
conversation thread. When building a helpdesk, inbox, or to-ticket system on top of
Cloudflare Email Routing, messages from the same conversation must be grouped so agents
can see the full context. Standard MIME threading headers (`Message-ID`, `In-Reply-To`,
`References`) carry the necessary lineage, but this lineage must be persisted and queried
in D1 to link new arrivals to existing threads.

## Context

RFC 5322 defines three headers that form a message's position in a thread:
`Message-ID` (the message's own canonical identifier), `In-Reply-To` (the direct parent
message's `Message-ID`), and `References` (the ordered list of all ancestor
`Message-ID`s). An email Worker parses these headers on every inbound message, upserts
the thread root into a `threads` table, and inserts the message record with a foreign-key
reference to the thread. Queries against `messages` return all messages sharing a
`thread_id`, sorted by arrival time.

## Parsing Threading Headers and Resolving Thread ID

```typescript
import PostalMime from "postal-mime";

export interface Env {
  DB: D1Database;
}

interface ParsedHeaders {
  messageId: string;
  inReplyTo: string | null;
  references: string[];
  subject: string;
  from: string;
  to: string;
  date: string;
}

function extractMessageId(raw: string | undefined): string {
  // Strip angle brackets: <abc@example.com> -> abc@example.com
  return (raw ?? crypto.randomUUID()).replace(/[<>]/g, "").trim();
}

function parseReferences(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(/\s+/)
    .map((r) => r.replace(/[<>]/g, "").trim())
    .filter(Boolean);
}

async function parseThreadingHeaders(
  rawMessage: ArrayBuffer
): Promise<ParsedHeaders> {
  const parsed = await new PostalMime().parse(rawMessage);

  const messageId = extractMessageId(parsed.messageId);
  const inReplyTo = parsed.inReplyTo
    ? extractMessageId(parsed.inReplyTo)
    : null;
  const references = parseReferences(
    parsed.headers?.find((h) => h.key.toLowerCase() === "references")?.value
  );

  return {
    messageId,
    inReplyTo,
    references,
    subject: parsed.subject ?? "(no subject)",
    from: parsed.from?.address ?? "",
    to: (parsed.to ?? []).map((t) => t.address).join(", "),
    date: parsed.date ?? new Date().toISOString(),
  };
}
```

## Upsert Thread and Insert Message in D1

The thread root is determined by walking the `References` list from oldest to newest.
If any ancestor `Message-ID` already has a `thread_id` in D1, the new message inherits
it. Otherwise a new thread is created with the current message as root.

```typescript
async function resolveThreadId(
  db: D1Database,
  headers: ParsedHeaders
): Promise<string> {
  // Check references from oldest ancestor to newest.
  const ancestors = [...headers.references];
  if (headers.inReplyTo && !ancestors.includes(headers.inReplyTo)) {
    ancestors.push(headers.inReplyTo);
  }

  for (const ancestorMsgId of ancestors) {
    const row = await db
      .prepare(`SELECT thread_id FROM messages WHERE message_id = ?`)
      .bind(ancestorMsgId)
      .first<{ thread_id: string }>();
    if (row?.thread_id) {
      return row.thread_id;
    }
  }

  // No ancestor found — this message starts a new thread.
  return crypto.randomUUID();
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const rawBuffer = await new Response(message.raw).arrayBuffer();
    const headers = await parseThreadingHeaders(rawBuffer);
    const threadId = await resolveThreadId(env.DB, headers);

    await env.DB.batch([
      // Upsert thread record (idempotent on thread_id).
      env.DB.prepare(
        `INSERT INTO threads (thread_id, subject, first_from, created_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT (thread_id) DO UPDATE
           SET last_message_at = excluded.created_at,
               message_count    = message_count + 1`
      ).bind(threadId, headers.subject, headers.from, headers.date),

      // Insert individual message.
      env.DB.prepare(
        `INSERT OR IGNORE INTO messages
           (message_id, thread_id, in_reply_to, subject, from_address,
            to_address, received_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        headers.messageId,
        threadId,
        headers.inReplyTo,
        headers.subject,
        headers.from,
        headers.to,
        headers.date
      ),
    ]);

    // Forward or process as needed.
    await message.forward("support@internal.example.com");
  },
};
```

## D1 Schema and Thread Query

```sql
-- migrations/0001_threading.sql
CREATE TABLE IF NOT EXISTS threads (
  thread_id       TEXT    PRIMARY KEY,
  subject         TEXT    NOT NULL,
  first_from      TEXT    NOT NULL,
  created_at      TEXT    NOT NULL,
  last_message_at TEXT,
  message_count   INTEGER NOT NULL DEFAULT 1,
  status          TEXT    NOT NULL DEFAULT 'open'
    CHECK(status IN ('open','closed','spam'))
);

CREATE TABLE IF NOT EXISTS messages (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id      TEXT    NOT NULL UNIQUE,
  thread_id       TEXT    NOT NULL REFERENCES threads(thread_id),
  in_reply_to     TEXT,
  subject         TEXT,
  from_address    TEXT    NOT NULL,
  to_address      TEXT,
  received_at     TEXT    NOT NULL
);

CREATE INDEX idx_messages_thread   ON messages(thread_id, received_at);
CREATE INDEX idx_messages_reply_to ON messages(in_reply_to);
CREATE INDEX idx_threads_status    ON threads(status, last_message_at DESC);
```

```typescript
// Retrieve a full conversation thread ordered by arrival time.
export async function getThread(
  db: D1Database,
  threadId: string
): Promise<{ thread: unknown; messages: unknown[] }> {
  const [threadRow, messagesResult] = await Promise.all([
    db
      .prepare(`SELECT * FROM threads WHERE thread_id = ?`)
      .bind(threadId)
      .first(),
    db
      .prepare(
        `SELECT message_id, from_address, to_address, subject, received_at, in_reply_to
         FROM messages
         WHERE thread_id = ?
         ORDER BY received_at ASC`
      )
      .bind(threadId)
      .all(),
  ]);

  return { thread: threadRow, messages: messagesResult.results };
}
```

## Anti-patterns

- Using only `In-Reply-To` without `References` to resolve thread membership — a mail
  client that omits `In-Reply-To` but includes `References` will create a false new thread.
- Storing the raw `Message-ID` including angle brackets as the primary key — this causes
  duplicate rows when the same message arrives from different forwarders with slightly
  different whitespace.
- Creating a thread per `Subject` string (ignoring headers) — subject lines change via
  "Re:" / "Fwd:" mutations and are not reliable thread anchors.

## Gotchas

- Cloudflare Email Routing can deliver the same message twice in rare retry scenarios;
  `INSERT OR IGNORE` on `messages.message_id` prevents duplicate rows.
- Very long mailing-list threads can have hundreds of entries in the `References` header;
  limit the ancestor walk to the most recent 20 entries to keep D1 query counts bounded.
- Messages sent directly (not as replies) will have neither `In-Reply-To` nor
  `References`, and must always start a new thread rather than being attached to a
  thread by subject heuristic.

## Verification

```bash
# Send a reply chain using swaks and verify thread grouping in D1.
MSG_ID1=$(uuidgen)@test.example
swaks --to inbound@acme.example --from alice@example.com \
  --header "Message-ID: <$MSG_ID1>" \
  --header "Subject: Support request" \
  --server mx.cloudflare.com

swaks --to inbound@acme.example --from bob@example.com \
  --header "In-Reply-To: <$MSG_ID1>" \
  --header "References: <$MSG_ID1>" \
  --header "Subject: Re: Support request" \
  --server mx.cloudflare.com

wrangler d1 execute EMAIL_DB \
  --command "SELECT t.thread_id, t.message_count, m.from_address FROM threads t JOIN messages m ON m.thread_id=t.thread_id ORDER BY m.received_at;" \
  --remote
```

## Related

- `email/email-threading-references-in-reply-to.md`
- `email/email-to-ticket-pattern.md`
- `email/inbound-email-processing.md`
- `email/inbound-webhook-workers-d1.md`

## Sources

- https://datatracker.ietf.org/doc/html/rfc5322#section-3.6.4
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/email-routing/email-workers/
- https://github.com/postalsys/postal-mime
