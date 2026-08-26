# Inbound Email Parsing and Routing with Cloudflare Email Routing + Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You want to receive emails at `support@example.com`, `orders@example.com`, or catch-all addresses, parse the MIME content, extract attachments, route messages to different handlers based on from/to/subject rules, and optionally auto-reply — all without running an email server. You also need to extract attachments and store them durably in R2, and route high-spam-score messages to a quarantine flow.

## Context

Cloudflare Email Routing can forward inbound emails to a Worker using the `email` event handler. The Worker receives a `ForwardableEmailMessage` object that exposes headers, the raw MIME stream, and methods to forward or reject the message. MIME parsing must be done manually or with a bundled library because Workers run in the V8 isolate (no Node.js `mailparser` without polyfills). The `postal-mime` library (pure ESM, no Node built-ins) is the recommended choice.

Cloudflare Email Routing configuration routes inbound addresses to Worker handlers via the dashboard or the Cloudflare API. The Worker is invoked synchronously; if it throws or times out, the sender receives a bounce.

## Solution

### Wrangler Configuration

```toml
# wrangler.toml
name = "email-router"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "ATTACHMENTS"
bucket_name = "email-attachments-prod"

[[kv_namespaces]]
binding = "ROUTING_RULES"
id = "<routing-rules-kv-id>"

[[d1_databases]]
binding = "DB"
database_name = "inbound-email-log"
database_id = "<your-d1-database-id>"

[vars]
AUTO_REPLY_FROM = "support@example.com"
SPAM_SCORE_THRESHOLD = "5.0"
```

### Install postal-mime

```bash
npm install postal-mime
```

### MIME Parsing and Attachment Extraction

```typescript
// src/mime-parser.ts
import PostalMime from 'postal-mime';

export interface ParsedEmail {
  messageId: string;
  from: { address: string; name?: string };
  to: Array<{ address: string; name?: string }>;
  cc: Array<{ address: string; name?: string }>;
  subject: string;
  date: string;
  textBody?: string;
  htmlBody?: string;
  attachments: ParsedAttachment[];
  headers: Map<string, string>;
  spamScore: number;
}

export interface ParsedAttachment {
  filename: string;
  mimeType: string;
  size: number;
  content: ArrayBuffer;
}

export async function parseMimeEmail(
  rawStream: ReadableStream<Uint8Array>
): Promise<ParsedEmail> {
  // Collect the full stream into an ArrayBuffer.
  const reader = rawStream.getReader();
  const chunks: Uint8Array[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
  const buffer = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.length;
  }

  const parser = new PostalMime();
  const parsed = await parser.parse(buffer.buffer);

  // Extract X-Spam-Score header (set by Cloudflare Email Routing).
  const spamScoreHeader = parsed.headers.find(
    (h) => h.key.toLowerCase() === 'x-spam-score'
  );
  const spamScore = spamScoreHeader ? parseFloat(spamScoreHeader.value) : 0;

  return {
    messageId:
      parsed.messageId ??
      `${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`,
    from: parsed.from ?? { address: 'unknown@unknown.com' },
    to: parsed.to ?? [],
    cc: parsed.cc ?? [],
    subject: parsed.subject ?? '(no subject)',
    date: parsed.date ?? new Date().toISOString(),
    textBody: parsed.text,
    htmlBody: parsed.html,
    attachments: (parsed.attachments ?? []).map((att) => ({
      filename: att.filename ?? 'attachment',
      mimeType: att.mimeType,
      size: att.content.byteLength,
      content: att.content,
    })),
    headers: new Map(parsed.headers.map((h) => [h.key.toLowerCase(), h.value])),
    spamScore,
  };
}
```

### Attachment Storage in R2

```typescript
// src/attachments.ts
import { ParsedAttachment } from './mime-parser';

export interface Env {
  ATTACHMENTS: R2Bucket;
}

/**
 * Store all attachments for a given email in R2.
 * Key pattern: attachments/{messageId}/{filename}
 * Returns list of R2 keys for the stored files.
 */
export async function storeAttachments(
  env: Env,
  messageId: string,
  attachments: ParsedAttachment[]
): Promise<string[]> {
  const keys = await Promise.all(
    attachments.map(async (att) => {
      // Sanitise filename to prevent path traversal.
      const safeFilename = att.filename
        .replace(/[^a-zA-Z0-9._-]/g, '_')
        .slice(0, 200);
      const key = `attachments/${messageId}/${safeFilename}`;

      await env.ATTACHMENTS.put(key, att.content, {
        httpMetadata: { contentType: att.mimeType },
        customMetadata: {
          'original-filename': att.filename,
          'message-id': messageId,
          'upload-time': new Date().toISOString(),
        },
      });
      return key;
    })
  );
  return keys;
}
```

### Routing Rules Engine

```typescript
// src/router.ts
import { ParsedEmail } from './mime-parser';

// Rules are stored in KV as JSON under key 'routing:rules'
export interface RoutingRule {
  id: string;
  priority: number;   // Lower = higher priority
  conditions: {
    fromDomain?: string;   // e.g. "example.com"
    toAddress?: string;    // e.g. "orders@example.com"
    subjectContains?: string;
    spamScoreAbove?: number;
  };
  action: 'forward' | 'autoReply' | 'quarantine' | 'discard' | 'webhook';
  actionTarget?: string;  // forward address, webhook URL, etc.
  replyTemplate?: string; // auto-reply message body
}

export function matchRules(
  email: ParsedEmail,
  rules: RoutingRule[]
): RoutingRule | null {
  const sorted = [...rules].sort((a, b) => a.priority - b.priority);

  for (const rule of sorted) {
    const c = rule.conditions;
    if (c.spamScoreAbove !== undefined && email.spamScore < c.spamScoreAbove) continue;
    if (c.fromDomain) {
      const fromDomain = email.from.address.split('@')[1]?.toLowerCase();
      if (fromDomain !== c.fromDomain.toLowerCase()) continue;
    }
    if (c.toAddress) {
      const toAddresses = email.to.map((t) => t.address.toLowerCase());
      if (!toAddresses.includes(c.toAddress.toLowerCase())) continue;
    }
    if (c.subjectContains) {
      if (
        !email.subject
          .toLowerCase()
          .includes(c.subjectContains.toLowerCase())
      )
        continue;
    }
    return rule;
  }
  return null;
}
```

### Email Worker Entry Point

```typescript
// src/index.ts
import { parseMimeEmail } from './mime-parser';
import { storeAttachments } from './attachments';
import { matchRules, RoutingRule } from './router';

export interface Env {
  ATTACHMENTS: R2Bucket;
  ROUTING_RULES: KVNamespace;
  DB: D1Database;
  AUTO_REPLY_FROM: string;
  SPAM_SCORE_THRESHOLD: string;
}

export default {
  // Standard HTTP handler (for health checks, rule management API, etc.)
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/rules' && request.method === 'GET') {
      const rules = await env.ROUTING_RULES.get('routing:rules', { type: 'json' });
      return new Response(JSON.stringify(rules ?? []), {
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.pathname === '/rules' && request.method === 'PUT') {
      const body = await request.json<RoutingRule[]>();
      await env.ROUTING_RULES.put('routing:rules', JSON.stringify(body));
      return new Response(JSON.stringify({ ok: true }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response('Not Found', { status: 404 });
  },

  // Email handler — invoked by Cloudflare Email Routing.
  async email(
    message: ForwardableEmailMessage,
    env: Env
  ): Promise<void> {
    // Parse full MIME.
    const parsed = await parseMimeEmail(message.raw);

    // Store attachments in R2.
    const attachmentKeys = parsed.attachments.length > 0
      ? await storeAttachments(env, parsed.messageId, parsed.attachments)
      : [];

    // Log to D1.
    await env.DB.prepare(
      `INSERT OR IGNORE INTO inbound_emails
       (id, from_address, to_address, subject, spam_score, attachment_count, received_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        parsed.messageId,
        parsed.from.address,
        parsed.to[0]?.address ?? '',
        parsed.subject,
        parsed.spamScore,
        attachmentKeys.length,
        new Date().toISOString()
      )
      .run();

    // Load routing rules.
    const rules =
      (await env.ROUTING_RULES.get('routing:rules', { type: 'json' })) ?? [];
    const matchedRule = matchRules(parsed, rules as RoutingRule[]);

    if (!matchedRule || matchedRule.action === 'discard') {
      // No rule matched or explicit discard — reject the message.
      message.setReject('Message discarded by routing policy');
      return;
    }

    switch (matchedRule.action) {
      case 'forward':
        if (matchedRule.actionTarget) {
          await message.forward(matchedRule.actionTarget);
        }
        break;

      case 'quarantine':
        // Forward to a quarantine address for human review.
        await message.forward('quarantine@example.com');
        break;

      case 'autoReply': {
        // Send an auto-reply via MailChannels.
        const replyBody = matchedRule.replyTemplate
          ?? 'Thank you for contacting Orchords. We will respond within 24 hours.';
        await fetch('https://api.mailchannels.net/tx/v1/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            personalizations: [{ to: [{ email: parsed.from.address }] }],
            from: { email: env.AUTO_REPLY_FROM, name: 'Orchords Support' },
            subject: `Re: ${parsed.subject}`,
            content: [{ type: 'text/plain', value: replyBody }],
            headers: { 'In-Reply-To': parsed.messageId },
          }),
        });
        // Also forward the original to the support inbox.
        await message.forward('support-inbox@example.com');
        break;
      }

      case 'webhook':
        if (matchedRule.actionTarget) {
          await fetch(matchedRule.actionTarget, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              messageId: parsed.messageId,
              from: parsed.from,
              subject: parsed.subject,
              textBody: parsed.textBody?.slice(0, 2000),
              attachmentKeys,
            }),
          });
        }
        break;
    }
  },
};
```

## Implementation Details

- Cloudflare Email Routing passes the raw RFC 5322 MIME message as a `ReadableStream<Uint8Array>` on `message.raw`. You must consume it fully before the email handler returns, or Cloudflare will treat it as rejected.
- `postal-mime` handles MIME multipart, quoted-printable, base64 decoding, and character set conversion. It is pure ESM and works in Workers without configuration.
- The `X-Spam-Score` header is set by Cloudflare's spam filtering pipeline before the Worker is invoked. Values above 5.0 are typically spam; values above 10.0 are almost certainly spam.
- Attachments up to 25 MB are supported by Cloudflare Email Routing. R2 supports individual object sizes up to 5 TB. Store the message ID in R2 custom metadata for cross-referencing with D1.
- `message.forward(address)` is asynchronous and can fail if the target address is not a verified Cloudflare destination. Wrap in try/catch and log failures.
- `message.setReject(reason)` causes the sending MTA to receive a 550 SMTP rejection. Use this only for clear spam or policy violations, not for routing failures (use quarantine instead).

## Anti-patterns

- **Parsing MIME with string split / regex** — MIME is a complex, recursive format. Manual parsing breaks on multipart boundaries, encoded words in headers, and non-ASCII filenames. Always use a proper MIME library.
- **Storing attachments directly in D1 as blobs** — D1 has a 10 MB row size limit and is not designed for binary storage. Use R2 for attachments, D1 for metadata and keys.
- **Forwarding all email including spam to internal addresses** — floods internal inboxes. Apply spam score threshold before forwarding.
- **Blocking on the full attachment pipeline before acking the message** — if R2 writes are slow, the email handler times out and the sender gets a bounce. Consider storing raw email in R2 first, then processing asynchronously via a Queue.
- **Using `message.raw` twice** — it is a one-time ReadableStream. Read it once, store the buffer, and pass the buffer to the parser.

## Gotchas

- The `email` handler must be exported as a named export on the `default` export object (`export default { email() {} }`). A standalone `export async function email()` does not work.
- `ForwardableEmailMessage` is a Cloudflare-specific type in `@cloudflare/workers-types`. Install `@cloudflare/workers-types` and add it to `tsconfig.json` `types` array.
- Routing rules stored in KV are eventually consistent. A rule change may take up to 60 s to propagate globally. For critical routing changes, deploy a Worker change instead of a KV update.
- Workers in Email Routing cannot send HTTP responses — the `fetch` return value is unused. Only `message.forward()` and `message.setReject()` affect email delivery.
- Cloudflare Email Routing does not currently support IMAP or POP3 — it is receive-and-route only. For full mailbox storage, forward to a traditional email provider.

## Verification

```bash
# Deploy the Worker
wrangler deploy

# Configure Email Routing in Cloudflare dashboard:
# Email > Email Routing > Routing Rules > Add address rule:
#   Catch-all -> Action: Send to Worker -> email-router

# Send a test email to support@example.com from an external account.

# Check D1 for the received record
wrangler d1 execute inbound-email-log \
  --command "SELECT id, from_address, subject, spam_score, attachment_count FROM inbound_emails ORDER BY received_at DESC LIMIT 5"

# Check R2 for attachments
wrangler r2 object list email-attachments-prod --prefix='attachments/'

# Upload routing rules
curl -X PUT http://localhost:8787/rules \
  -H 'Content-Type: application/json' \
  -d '[{"id":"r1","priority":10,"conditions":{"spamScoreAbove":5},"action":"quarantine"}]'
```

## Related

- `documentation/docs/policies/email/workers-email-template-engine-r2.md`
- `documentation/docs/policies/email/workers-transactional-email-queue.md`
- Cloudflare Email Routing docs: https://developers.cloudflare.com/email-routing/
- postal-mime library: https://github.com/postalsys/postal-mime
- RFC 5322 (Internet Message Format): https://datatracker.ietf.org/doc/html/rfc5322

## Sources

- Cloudflare Email Routing documentation (2025)
- postal-mime README and API reference (2024)
- RFC 5321 (SMTP) and RFC 5322 (Internet Message Format)
- Cloudflare blog — Email Routing Workers integration (2023)
