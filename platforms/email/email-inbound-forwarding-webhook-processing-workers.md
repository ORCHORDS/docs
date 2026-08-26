# Inbound Email Forwarding and Webhook Processing With Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project (example.com) assigns each user a personal reply address (e.g. `reply+<token>@mail.example.com`) so they can reply to notification emails and have those replies posted as comments or DMs inside the platform. Inbound mail must be parsed, the token resolved to a user and thread, the reply text extracted, and a webhook fired to the platform API — all within a single Cloudflare Email Worker.

## Context
Cloudflare Email Routing can route inbound mail to a Worker via the `email` export. The Worker receives a `ForwardableEmailMessage` object containing the raw RFC 5322 message. The `postal-mime` library (bundled at build time) parses MIME structure. D1 maps reply tokens to (userId, threadId) pairs. The platform API receives a signed webhook payload; a KV namespace deduplicates retried deliveries.

## Routing Configuration

In `wrangler.toml`, declare the email binding and an email rule that sends all mail at `mail.example.com` to the Worker. Cloudflare Email Routing must be enabled on the zone and DNS MX records must point to Cloudflare's inbound MX servers.

```toml
# wrangler.toml
name = "inbound-email-processor"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[email]]
name = "INBOUND"

[[d1_databases]]
binding = "DB"
database_name = "example project-main"
database_id = "YOUR_D1_ID"

[[kv_namespaces]]
binding = "DEDUP_KV"
id = "YOUR_KV_ID"
```

## Token Extraction and Resolution

The `To` address encodes the reply token as a sub-address (`reply+<token>@mail.example.com`). The Worker extracts the token from the `to` header, looks it up in D1, and rejects mail with an unknown token by forwarding to a dead-letter address rather than throwing (throwing would cause Cloudflare to bounce the sender).

```typescript
// token-resolver.ts
interface ReplyToken {
  user_id: string;
  thread_id: string;
  thread_type: "comment" | "dm";
  expires_at: number;
}

export async function resolveToken(
  db: D1Database,
  rawTo: string
): Promise<ReplyToken | null> {
  const match = rawTo.match(/reply\+([a-z0-9_-]+)@/i);
  if (!match) return null;

  const token = match[1];
  const row = await db
    .prepare(`
      SELECT user_id, thread_id, thread_type, expires_at
      FROM reply_tokens
      WHERE token = ?1 AND expires_at > unixepoch()
    `)
    .bind(token)
    .first<ReplyToken>();

  return row ?? null;
}
```

## MIME Parsing and Reply Extraction

Email replies typically contain a quoted block below the new content. The Worker uses `postal-mime` to parse the message and then strips the quoted portion so only the new text reaches the platform. Plain-text part is preferred; HTML is stripped as fallback.

```typescript
// parse-reply.ts
import PostalMime from "postal-mime";

export async function extractReplyText(
  rawMessage: ReadableStream<Uint8Array>
): Promise<{ text: string; subject: string; fromAddress: string }> {
  const chunks: Uint8Array[] = [];
  const reader = rawMessage.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) chunks.push(value);
  }

  const bytes = new Uint8Array(chunks.reduce((acc, c) => acc + c.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }

  const email = await PostalMime.parse(bytes.buffer);

  const raw = email.text ?? stripHtml(email.html ?? "");

  // Strip quoted reply block — lines starting with ">" or the On … wrote: marker
  const lines = raw.split("\n");
  const cutIndex = lines.findIndex(
    (l) => l.startsWith(">") || /^On .+ wrote:$/.test(l.trim())
  );
  const text = (cutIndex === -1 ? lines : lines.slice(0, cutIndex))
    .join("\n")
    .trim();

  return {
    text,
    subject: email.subject ?? "",
    fromAddress: email.from?.address ?? "",
  };
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}
```

## Main Email Worker — Orchestration

The `email` export receives the `ForwardableEmailMessage`. It deduplicates via the message `Message-ID` header stored in KV, resolves the token, parses the reply, and POSTs a signed webhook to the platform API.

```typescript
// src/index.ts
import { resolveToken } from "./token-resolver";
import { extractReplyText } from "./parse-reply";

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const messageId = message.headers.get("Message-ID") ?? crypto.randomUUID();
    const dedupKey = `msgid:${messageId}`;

    // Idempotency guard
    if (await env.DEDUP_KV.get(dedupKey)) {
      return; // Already processed
    }

    const token = await resolveToken(env.DB, message.to);
    if (!token) {
      // Forward to dead-letter mailbox instead of bouncing
      await message.forward("deadletter@example.com");
      return;
    }

    const { text, fromAddress } = await extractReplyText(message.raw);
    if (!text || text.length > 10_000) {
      await message.forward("deadletter@example.com");
      return;
    }

    const payload = {
      userId: token.user_id,
      threadId: token.thread_id,
      threadType: token.thread_type,
      text,
      fromAddress,
      receivedAt: new Date().toISOString(),
    };

    const sig = await signPayload(env.WEBHOOK_SECRET, payload);

    const resp = await fetch("https://api.example.com/internal/email-reply", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Webhook-Signature": sig,
      },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      throw new Error(`Webhook delivery failed: ${resp.status}`); // Triggers Cloudflare retry
    }

    await env.DEDUP_KV.put(dedupKey, "1", { expirationTtl: 7 * 86400 });
  },
};

async function signPayload(secret: string, payload: unknown): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(JSON.stringify(payload))
  );
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}
```

## Anti-patterns
- Throwing on an unknown token — this causes Cloudflare to generate a bounce back to the sender, leaking that the address schema exists. Forward to a dead-letter address instead.
- Storing the full raw message in D1 — D1 rows have a practical size limit; store large bodies in R2 and save only metadata in D1.
- Trusting the `From` header for authentication — it is trivially spoofed. Use DMARC/DKIM validation via the `message.headers` and Cloudflare's pre-validated authentication results, or require reply token uniqueness per sender.
- Parsing MIME in a regex — MIME boundary handling is complex; always use `postal-mime` or an equivalent well-tested library.

## Gotchas
- `message.raw` is a `ReadableStream` and can only be consumed once. Read it fully before calling `message.forward()` if you need both the content and the forward.
- Cloudflare Email Workers have a 10 MB message size limit; attachments in replies can exceed this; add a `Content-Length` check and forward oversized mail to dead-letter.
- Reply token TTL should match notification email retention (e.g. 30 days); expired tokens should forward to dead-letter, not error, to avoid sender-facing bounces.
- `postal-mime` must be bundled — it is not a built-in Workers API. Add it to `package.json` and confirm tree-shaking does not strip it.

## Verification
1. Send a test email to `reply+<valid-token>@mail.example.com` and confirm the platform API receives the webhook within 5 seconds.
2. Send to `reply+<expired-token>@` and confirm the email reaches the dead-letter mailbox, not a bounce.
3. Send the same email twice (duplicate `Message-ID`); confirm the webhook is only posted once (KV dedup working).
4. Send a reply with a quoted block and confirm only the new content appears in the webhook `text` field.

## Related
- [inbound-email-processing.md](inbound-email-processing.md)
- [inbound-webhook-workers-d1.md](inbound-webhook-workers-d1.md)
- [email-forwarding-setup.md](email-forwarding-setup.md)
- [email-webhook-idempotency-deduplication.md](email-webhook-idempotency-deduplication.md)
- [email-webhook-signature-validation-workers.md](email-webhook-signature-validation-workers.md)

## Sources
- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/email-routing/email-workers/runtime-api/
- https://github.com/postalsys/postal-mime
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
