# Cloudflare Email Workers: Advanced Inbound Processing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your domain receives inbound email and you need to do more than simple forwarding: parse
MIME structure, extract attachments, apply custom spam scoring, route messages to different
destinations based on headers or body content, or trigger downstream workflows. Cloudflare
Email Routing's GUI rules cover simple cases; Email Workers give you full programmatic control
over every inbound message.

## Context

When Email Routing is enabled for a domain, each `email` handler in a Worker receives a
`ForwardableEmailMessage` object. The binding is declared as `type = "email"` in
`wrangler.toml`; the Worker's entry point exports an `email` function (not `fetch`).

The `message` object provides:
- `from`, `to` — envelope addresses (not necessarily the header `From`/`To`).
- `headers` — a `Headers`-like map of RFC 5322 headers.
- `raw` — a `ReadableStream<Uint8Array>` of the full RFC 5322 message.
- `rawSize` — total byte size.
- `forward(address, headers?)` — forward to any destination.
- `reply(mime)` — send an auto-reply using a `Response`-compatible body.
- `setReject(reason)` — reject the message with a 550 SMTP error.

Email Workers run under the standard CPU and memory limits (10 ms CPU on Bundled, 30 s on
Unbound). Parsing large attachments in-Worker is feasible on Unbound; offload to a Queue for
async processing if messages can exceed a few MB.

## wrangler.toml Configuration

```toml
name = "email-processor"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[email]]
type     = "email"
name     = "INBOUND"

[[queues.producers]]
binding  = "EMAIL_QUEUE"
queue    = "email-jobs"

[[r2_buckets]]
binding  = "ATTACHMENTS"
bucket_name = "email-attachments"

[[kv_namespaces]]
binding  = "SPAM_RULES"
id       = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## Routing and Rejection by Header

```typescript
// src/index.ts
export interface Env {
  EMAIL_QUEUE: Queue;
  ATTACHMENTS: R2Bucket;
  SPAM_RULES: KVNamespace;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const subject = message.headers.get("Subject") ?? "";
    const from    = message.from.toLowerCase();

    // 1. Block-list check — stored as JSON array in KV
    const blocked = await env.SPAM_RULES.get<string[]>("blocked_senders", "json") ?? [];
    if (blocked.includes(from)) {
      message.setReject("5.7.1 Sender blocked");
      return;
    }

    // 2. Simple spam heuristics on subject
    const spamScore = scoreSubject(subject);
    if (spamScore >= 10) {
      // Forward to quarantine instead of rejecting so we can review
      await message.forward("quarantine@example.com");
      return;
    }

    // 3. Route by subject prefix
    if (subject.startsWith("[SUPPORT]")) {
      await message.forward("support@example.com");
      return;
    }

    if (subject.startsWith("[BILLING]")) {
      await message.forward("billing@example.com");
      return;
    }

    // 4. Default: enqueue for async processing and forward a copy
    const rawBytes = await readStream(message.raw);
    await env.EMAIL_QUEUE.send({
      from:    message.from,
      to:      message.to,
      subject,
      rawSize: message.rawSize,
      rawB64:  toBase64(rawBytes),
    });

    await message.forward("inbox@example.com");
  },
};

function scoreSubject(subject: string): number {
  const patterns = [/urgent/i, /free money/i, /click here/i, /you won/i, /limited offer/i];
  return patterns.filter((p) => p.test(subject)).length * 3;
}

async function readStream(stream: ReadableStream<Uint8Array>): Promise<Uint8Array> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream) chunks.push(chunk);
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const buf = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { buf.set(chunk, offset); offset += chunk.length; }
  return buf;
}

function toBase64(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes));
}
```

## MIME Parsing and Attachment Extraction

Email Workers do not ship a built-in MIME parser. For multipart messages, use a lightweight
MIME parser bundled into your Worker. The example below uses `mailparser` (bundled at build
time) via the queue consumer — keeping the email Worker itself fast.

```typescript
// src/queue-consumer.ts  — separate worker processing the email-jobs queue
import { simpleParser, ParsedMail } from "mailparser"; // bundled via npm

export interface Env {
  ATTACHMENTS: R2Bucket;
}

interface EmailJob {
  from: string;
  to: string;
  subject: string;
  rawSize: number;
  rawB64: string;
}

export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      await processEmail(msg.body, env);
      msg.ack();
    }
  },
};

async function processEmail(job: EmailJob, env: Env): Promise<void> {
  const rawBytes = Uint8Array.from(atob(job.rawB64), (c) => c.charCodeAt(0));
  const parsed: ParsedMail = await simpleParser(Buffer.from(rawBytes));

  if (!parsed.attachments?.length) return;

  for (const attachment of parsed.attachments) {
    const key = `${Date.now()}-${attachment.filename ?? "untitled"}`;
    await env.ATTACHMENTS.put(key, attachment.content, {
      httpMetadata: { contentType: attachment.contentType },
      customMetadata: {
        from: job.from,
        subject: job.subject,
        filename: attachment.filename ?? "",
      },
    });
    console.log(`Saved attachment: ${key} (${attachment.size} bytes)`);
  }
}
```

## Auto-Reply with a Templated MIME Response

```typescript
// src/auto-reply.ts — called from the email handler when appropriate
export async function sendAutoReply(
  message: ForwardableEmailMessage,
  ticketId: string,
): Promise<void> {
  const subject = message.headers.get("Subject") ?? "(no subject)";
  const replyBody = [
    `From: support@example.com`,
    `To: ${message.from}`,
    `Subject: Re: ${subject}`,
    `Content-Type: text/plain; charset=utf-8`,
    ``,
    `Thanks for reaching out. Your request has been logged as ticket #${ticketId}.`,
    ``,
    `We typically respond within one business day.`,
    ``,
    `— Orchords Support`,
  ].join("\r\n");

  await message.reply(
    new Response(replyBody, {
      headers: { "Content-Type": "message/rfc822" },
    }),
  );
}
```

## DKIM / SPF Header Inspection

Email Routing adds authentication result headers before your Worker sees the message:

```typescript
// src/auth-check.ts
export function getAuthResults(headers: Headers): {
  dkim: string; spf: string; dmarc: string;
} {
  const results = headers.get("Authentication-Results") ?? "";

  const extract = (key: string) => {
    const m = results.match(new RegExp(`${key}=([^\\s;]+)`));
    return m?.[1] ?? "none";
  };

  return {
    dkim:  extract("dkim"),
    spf:   extract("spf"),
    dmarc: extract("dmarc"),
  };
}

// Usage in the email handler:
//   const auth = getAuthResults(message.headers);
//   if (auth.dmarc !== "pass") message.setReject("5.7.26 DMARC check failed");
```

## Anti-patterns

- Reading `message.raw` twice — the stream is single-use; buffer it to a `Uint8Array` once
  and reuse the buffer.
- Calling `message.forward()` after `setReject()` — once rejected, further operations throw;
  always `return` immediately after `setReject`.
- Parsing large MIME bodies synchronously in the `email` handler on Bundled Workers — the
  10 ms CPU limit will be exceeded; move heavy parsing to a Queue consumer on Unbound.
- Forwarding to an external address without validating the `forward()` destination against
  your allow-list — an attacker-controlled `To:` header could be used to relay spam through
  your Worker if you forward based on the header value without sanitisation.

## Gotchas

- `message.to` is the SMTP envelope recipient (the address the MX received the message for),
  which may differ from the `To:` header (displayed recipient); use `message.to` for routing.
- `message.rawSize` counts the full RFC 5322 message including headers; the body-only size is
  smaller — do not use `rawSize` as the attachment size guard.
- Email Workers must be bound to the Email Routing rule in the dashboard, not just deployed;
  deploying without adding the custom address rule means no messages reach the Worker.
- `message.reply()` requires the body to be a valid RFC 5322 message; sending plain text
  without headers results in a malformed reply that many clients reject.

## Verification

```bash
# Send a test message using swaks (SMTP Swiss Army Knife)
swaks --to your-catch-all@yourdomain.com \
      --from test@example.com \
      --header "Subject: [SUPPORT] Test ticket" \
      --body "Hello, this is a test."

# Check Cloudflare Email Routing logs in the dashboard:
# Workers & Pages → your worker → Logs → filter by "email"

# Confirm attachment landed in R2
wrangler r2 object list email-attachments --prefix "$(date +%s | cut -c1-8)"
```

## Related

- `workers-email-routing.md`
- `email-service-best-practices.md`
- `cloudflare-queues-dead-letter-dlq.md`
- `r2-best-practices.md`
- `queues-batch-processing.md`

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/email-routing/email-workers/runtime-api/
- https://developers.cloudflare.com/email-routing/email-workers/reply-to-emails/
