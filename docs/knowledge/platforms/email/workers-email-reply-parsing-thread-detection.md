# Workers Email Reply Parsing and Thread Detection

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your support or CRM system receives inbound replies via Cloudflare Email Routing and needs to:

- Identify that an email is a reply (not a new conversation)
- Extract the original thread ID from headers or the body
- Strip quoted text so only the new content is stored
- Route the reply to the correct open ticket or conversation record in D1

Without proper reply parsing, every inbound email looks like a new conversation, duplicating tickets and breaking context.

---

## Context

Email clients signal replies through two RFC-5322 headers:

- `In-Reply-To` — contains the `Message-ID` of the message being replied to
- `References` — contains the full chain of `Message-IDs` in the thread

Cloudflare Email Routing delivers raw MIME messages to a Worker via the `email` handler. The `EmailMessage` object exposes headers through a `Headers`-compatible interface. After extracting thread identity from headers, the Worker must also strip quoted content from the body (lines starting with `>`, `On … wrote:` blocks, and `--` signature delimiters) so only the net-new reply text is persisted.

---

## Parsing In-Reply-To and References Headers

```typescript
import { EmailMessage } from "cloudflare:email";
import { createMimeMessage } from "mimetext";

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const inReplyTo = message.headers.get("In-Reply-To")?.trim() ?? null;
    const references = message.headers.get("References")?.trim() ?? null;

    // Normalise angle brackets: <abc@domain> → abc@domain
    const normalise = (id: string | null) =>
      id ? id.replace(/[<>]/g, "").split(/\s+/)[0] : null;

    const parentMessageId = normalise(inReplyTo);

    // References is space-separated oldest→newest; last entry is immediate parent
    const referenceIds = references
      ? references.split(/\s+/).map((r) => r.replace(/[<>]/g, ""))
      : [];

    const threadRootId = referenceIds[0] ?? parentMessageId;

    if (!parentMessageId) {
      // No In-Reply-To → treat as new conversation
      await createNewConversation(message, env);
      return;
    }

    await appendReplyToThread(message, parentMessageId, threadRootId, env);
  },
};
```

---

## Looking Up the Thread in D1

```typescript
async function appendReplyToThread(
  message: EmailMessage,
  parentMessageId: string,
  threadRootId: string | null,
  env: Env
) {
  // Find the conversation by any known message ID in the thread
  const row = await env.DB.prepare(
    `SELECT conversation_id FROM email_messages
     WHERE message_id = ? OR message_id = ?
     LIMIT 1`
  )
    .bind(parentMessageId, threadRootId ?? parentMessageId)
    .first<{ conversation_id: string }>();

  if (!row) {
    // Parent not found — treat as orphan and open new conversation
    await createNewConversation(message, env);
    return;
  }

  const body = await extractReplyBody(message);

  await env.DB.prepare(
    `INSERT INTO email_messages
       (message_id, conversation_id, sender, subject, body_text, received_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`
  )
    .bind(
      message.headers.get("Message-ID") ?? crypto.randomUUID(),
      row.conversation_id,
      message.from,
      message.headers.get("Subject") ?? "",
      body
    )
    .run();
}
```

---

## Stripping Quoted Text from Plain-Text Body

```typescript
async function extractReplyBody(message: EmailMessage): Promise<string> {
  const raw = await new Response(message.raw).text();

  // Very basic MIME plain-text extraction (single-part messages)
  const bodyStart = raw.indexOf("\r\n\r\n");
  const fullBody = bodyStart !== -1 ? raw.slice(bodyStart + 4) : raw;

  return stripQuotedText(fullBody);
}

function stripQuotedText(body: string): string {
  const lines = body.split(/\r?\n/);
  const result: string[] = [];
  let inQuoteBlock = false;

  for (const line of lines) {
    // Standard quoted line prefix
    if (line.startsWith(">")) {
      inQuoteBlock = true;
      continue;
    }

    // "On <date>, <name> wrote:" attribution line — start of quote block
    if (/^On .+wrote:$/i.test(line.trim())) {
      inQuoteBlock = true;
      continue;
    }

    // Signature delimiter
    if (line.trim() === "--") {
      break;
    }

    inQuoteBlock = false;
    result.push(line);
  }

  return result.join("\n").trim();
}
```

---

## Handling HTML-Only Replies

Many mobile clients send only `text/html` parts. Use a regex-based HTML stripper when no plain-text alternative exists.

```typescript
function htmlToPlainText(html: string): string {
  return html
    .replace(/<blockquote[^>]*>[\s\S]*?<\/blockquote>/gi, "") // remove quotes
    .replace(/<div class="gmail_quote"[\s\S]*?<\/div>/gi, "")  // Gmail quote
    .replace(/<[^>]+>/g, " ")                                  // strip tags
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s{2,}/g, " ")
    .trim();
}
```

---

## Storing Message IDs for Future Thread Detection

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS email_messages (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id      TEXT NOT NULL UNIQUE,       -- RFC-5322 Message-ID
  conversation_id TEXT NOT NULL,
  sender          TEXT NOT NULL,
  subject         TEXT,
  body_text       TEXT,
  received_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_email_messages_message_id
  ON email_messages (message_id);

CREATE INDEX IF NOT EXISTS idx_email_messages_conversation
  ON email_messages (conversation_id, received_at DESC);
```

---

## Anti-patterns

- **Matching by Subject line alone** — `Re:` subjects are unreliable; clients strip, mangle, or localise the prefix. Always prefer `In-Reply-To`.
- **Storing the full raw MIME body** — raw bodies include quoted history and attachments; store only the extracted reply text to avoid unbounded D1 row growth.
- **Ignoring the References chain** — using only `In-Reply-To` misses orphaned replies where the immediate parent is not in your DB but an ancestor is.
- **Blocking the Worker on heavy MIME parsing** — use `ctx.waitUntil()` for DB writes so the Email Routing ACK is not delayed.

---

## Gotchas

- `message.raw` is a `ReadableStream` and can only be consumed once. Tee it if you need the body for both parsing and forwarding.
- The `Message-ID` header value always includes angle brackets (`<...>`); strip them before using as a DB key.
- Some mailing-list servers strip `In-Reply-To` to collapse threads — check `References` as fallback.
- HTML quote stripping is client-specific; test against Gmail, Outlook, and Apple Mail reply formats separately.
- CF Email Routing Workers have a 10 MB message size limit; large attachments may cause `message.raw` reads to fail at the stream level.

---

## Verification

```bash
# Send a simulated reply locally with swaks
swaks --to you@routing-domain.com \
  --header "In-Reply-To: <original-message-id@domain>" \
  --header "References: <original-message-id@domain>" \
  --body "This is the new reply text.\n\nOn Mon 1 Jan, Alice wrote:\n> Original quoted line"

# Query D1 to confirm thread linkage
wrangler d1 execute DB --command \
  "SELECT conversation_id, COUNT(*) as msgs FROM email_messages GROUP BY conversation_id"
```

---

## Related

- `email-conversation-threading-d1-workers.md`
- `email-threading-references-in-reply-to.md`
- `inbound-email-processing.md`
- `cloudflare-email-routing-workers.md`
- `email-to-ticket-pattern.md`

---

## Sources

- RFC 5322 §3.6.4 Identification Fields — https://datatracker.ietf.org/doc/html/rfc5322#section-3.6.4
- Cloudflare Email Routing Workers API — https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
