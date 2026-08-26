# Email Attachment Scanning with R2 and Workers AI

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Inbound emails carrying attachments (PDFs, Office documents, archives) must be scanned
for malicious content before they are stored or forwarded downstream. Running AV or
content-classification entirely inside a single Workers invocation risks hitting CPU
limits; storing attachments in R2 first and then triggering an async scan with Workers AI
keeps the pipeline responsive and auditable.

## Context

Cloudflare Email Routing delivers inbound messages to a Worker via the `email` handler.
The Worker can read the raw MIME stream, extract attachment parts, write each part to R2,
and enqueue a scan job. A second consumer Worker calls the Workers AI
`@cf/meta/llama-3-8b-instruct` (text) or an image-classification model on extracted
content, then updates a D1 `attachment_scans` table with the verdict. Downstream release
or quarantine is gated on that verdict.

## Parsing MIME and Writing Attachments to R2

The `postal-mime` library (bundled at build time) handles multipart parsing without
external fetches. Each `attachment` object exposes `content` as an `ArrayBuffer`.

```typescript
import PostalMime from "postal-mime";

export interface Env {
  ATTACHMENT_BUCKET: R2Bucket;
  SCAN_QUEUE: Queue<ScanJob>;
  DB: D1Database;
}

interface ScanJob {
  messageId: string;
  r2Key: string;
  filename: string;
  mimeType: string;
  senderAddress: string;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const raw = new Response(message.raw);
    const parsed = await new PostalMime().parse(await raw.arrayBuffer());

    const messageId =
      parsed.messageId ?? crypto.randomUUID();

    for (const attachment of parsed.attachments ?? []) {
      const r2Key = `attachments/${messageId}/${attachment.filename}`;

      await env.ATTACHMENT_BUCKET.put(r2Key, attachment.content, {
        httpMetadata: { contentType: attachment.mimeType },
        customMetadata: {
          messageId,
          senderAddress: message.from,
          filename: attachment.filename ?? "unknown",
        },
      });

      await env.SCAN_QUEUE.send({
        messageId,
        r2Key,
        filename: attachment.filename ?? "unknown",
        mimeType: attachment.mimeType ?? "application/octet-stream",
        senderAddress: message.from,
      } satisfies ScanJob);
    }

    // Forward only after attachments are staged; quarantine happens in consumer.
    await message.forward("inbound-review@internal.example.com");
  },
};
```

## Async Scan Consumer with Workers AI

The consumer pulls from the queue, reads text-extractable content from R2, and sends it
to Workers AI for classification. Binary-only types (images, executables) fall back to a
MIME-type blocklist verdict.

```typescript
import { Ai } from "@cloudflare/ai";

const BLOCKED_MIME_PREFIXES = [
  "application/x-msdownload",
  "application/x-executable",
  "application/x-sh",
];

export default {
  async queue(
    batch: MessageBatch<ScanJob>,
    env: Env & { AI: Ai }
  ): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      let verdict: "clean" | "suspicious" | "blocked" = "clean";
      let reason = "";

      // Immediate block on dangerous MIME types.
      if (
        BLOCKED_MIME_PREFIXES.some((p) => job.mimeType.startsWith(p))
      ) {
        verdict = "blocked";
        reason = `blocked_mime:${job.mimeType}`;
      } else {
        const obj = await env.ATTACHMENT_BUCKET.get(job.r2Key);
        if (obj && job.mimeType.startsWith("text/")) {
          const text = await obj.text();
          const response = await env.AI.run(
            "@cf/meta/llama-3-8b-instruct",
            {
              messages: [
                {
                  role: "system",
                  content:
                    "Classify the following email attachment text as CLEAN, SUSPICIOUS, or MALICIOUS. Reply with only one word.",
                },
                { role: "user", content: text.slice(0, 4096) },
              ],
            }
          );
          const label = (response as { response: string }).response
            .trim()
            .toUpperCase();
          if (label === "MALICIOUS") {
            verdict = "blocked";
            reason = "ai_malicious";
          } else if (label === "SUSPICIOUS") {
            verdict = "suspicious";
            reason = "ai_suspicious";
          }
        }
      }

      await env.DB.prepare(
        `INSERT INTO attachment_scans
           (message_id, r2_key, filename, mime_type, verdict, reason, scanned_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      )
        .bind(
          job.messageId,
          job.r2Key,
          job.filename,
          job.mimeType,
          verdict,
          reason,
          new Date().toISOString()
        )
        .run();

      msg.ack();
    }
  },
};
```

## D1 Schema and Release Gate

```typescript
// migrations/0001_attachment_scans.sql
/*
CREATE TABLE attachment_scans (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id   TEXT    NOT NULL,
  r2_key       TEXT    NOT NULL UNIQUE,
  filename     TEXT    NOT NULL,
  mime_type    TEXT    NOT NULL,
  verdict      TEXT    NOT NULL CHECK(verdict IN ('clean','suspicious','blocked')),
  reason       TEXT,
  scanned_at   TEXT    NOT NULL
);
CREATE INDEX idx_scans_message ON attachment_scans(message_id);
CREATE INDEX idx_scans_verdict  ON attachment_scans(verdict);
*/

// Release-gate helper: all attachments for a message must be clean.
export async function allAttachmentsClean(
  db: D1Database,
  messageId: string
): Promise<boolean> {
  const { results } = await db
    .prepare(
      `SELECT COUNT(*) AS total,
              SUM(CASE WHEN verdict = 'clean' THEN 1 ELSE 0 END) AS clean_count
       FROM attachment_scans
       WHERE message_id = ?`
    )
    .bind(messageId)
    .all<{ total: number; clean_count: number }>();

  const row = results[0];
  return row.total > 0 && row.total === row.clean_count;
}
```

## Anti-patterns

- Scanning attachments synchronously inside the `email` handler — CPU time limit will
  terminate the Worker before large files are processed.
- Storing attachment bytes in D1 BLOBs — R2 is purpose-built for binary objects and
  avoids D1 row-size limits.
- Trusting the `Content-Type` header from the sender to determine safety — always
  validate with magic-byte sniffing or explicit blocklists.

## Gotchas

- Workers AI text models have a context window; truncate extracted text to 4 096 tokens
  before sending or the request will be rejected with a 400 error.
- R2 `put` within the `email` handler counts toward the Workers 50 ms CPU budget per
  subrequest; prefer small attachments in the inbound handler and defer large ones via a
  Durable Object or Queue.

## Verification

```bash
# Upload a test EICAR-like text file and trigger the scan queue manually.
wrangler r2 object put attachments/test-msg-001/test.txt \
  --file ./fixtures/suspicious.txt \
  --content-type text/plain \
  --remote

# Query D1 for the verdict.
wrangler d1 execute EMAIL_DB \
  --command "SELECT verdict, reason FROM attachment_scans WHERE message_id='test-msg-001';" \
  --remote
```

## Related

- `email/email-attachment-patterns.md`
- `email/inbound-email-processing.md`
- `email/email-archiving-compliance-retention-r2.md`

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/ai/models/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://github.com/postalsys/postal-mime
