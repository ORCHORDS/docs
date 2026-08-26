# Email Thread Summarization with Workers AI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A support or sales inbox accumulates long email threads; agents waste time scrolling through history before replying.
Workers AI (llama-3.1-8b-instruct or similar) can summarize a full thread on demand or on inbound, storing the result in D1.

## Context
Cloudflare Workers AI runs inference at the edge with zero cold-start and no egress to a third-party LLM provider.
Email threads are reconstructed from D1 (storing each message body + metadata) using the `References` / `In-Reply-To` chain.
The summary is written back to D1 and surfaced via a REST endpoint consumed by a help-desk front-end.

---

## Architecture / Data Model

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS email_messages (
  id          TEXT PRIMARY KEY,          -- Message-ID (stripped of angle brackets)
  thread_id   TEXT NOT NULL,             -- canonical thread root Message-ID
  from_addr   TEXT NOT NULL,
  subject     TEXT NOT NULL,
  body_text   TEXT NOT NULL,
  received_at INTEGER NOT NULL           -- Unix epoch seconds
);

CREATE INDEX IF NOT EXISTS idx_thread ON email_messages(thread_id, received_at);

CREATE TABLE IF NOT EXISTS thread_summaries (
  thread_id    TEXT PRIMARY KEY,
  summary      TEXT NOT NULL,
  model        TEXT NOT NULL,
  generated_at INTEGER NOT NULL
);
```

## Inbound Email Handler — Storing Messages

```typescript
// src/email-handler.ts
import { EmailMessage } from 'cloudflare:email';
import PostalMime from 'postal-mime';  // bundled via npm

export interface Env {
  DB: D1Database;
  AI: Ai;
  SUMMARIZE_QUEUE: Queue<{ threadId: string }>;
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const parser = new PostalMime();
    const raw = new Response(message.raw);
    const parsed = await parser.parse(await raw.arrayBuffer());

    // Derive thread_id: use first References header entry or fall-back to this Message-ID
    const references = (parsed.headers.get('references') ?? '')
      .split(/\s+/)
      .filter(Boolean)
      .map((r) => r.replace(/[<>]/g, ''));

    const messageId = (parsed.headers.get('message-id') ?? crypto.randomUUID())
      .replace(/[<>]/g, '');

    const threadId = references[0] ?? messageId;

    const bodyText =
      parsed.text ??
      parsed.html?.replace(/<[^>]+>/g, ' ').replace(/\s{2,}/g, ' ') ??
      '';

    await env.DB.prepare(
      `INSERT OR IGNORE INTO email_messages
         (id, thread_id, from_addr, subject, body_text, received_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
      .bind(
        messageId,
        threadId,
        parsed.from?.address ?? message.from,
        parsed.subject ?? '(no subject)',
        bodyText.slice(0, 8_000),   // cap per-message stored text
        Math.floor(Date.now() / 1000)
      )
      .run();

    // Enqueue background summarization — avoids blocking the email handler
    await env.SUMMARIZE_QUEUE.send({ threadId });
    await message.forward('support@example.com');
  },
};
```

## Queue Consumer — Generating the Summary

```typescript
// src/summarize-consumer.ts
export interface Env {
  DB: D1Database;
  AI: Ai;
}

interface SummarizeMessage {
  threadId: string;
}

export default {
  async queue(batch: MessageBatch<SummarizeMessage>, env: Env): Promise<void> {
    // Deduplicate thread IDs within the batch
    const threadIds = [...new Set(batch.messages.map((m) => m.body.threadId))];

    for (const threadId of threadIds) {
      const { results } = await env.DB.prepare(
        `SELECT from_addr, subject, body_text, received_at
           FROM email_messages
          WHERE thread_id = ?
          ORDER BY received_at ASC
          LIMIT 20`
      )
        .bind(threadId)
        .all<{
          from_addr: string;
          subject: string;
          body_text: string;
          received_at: number;
        }>();

      if (results.length === 0) continue;

      // Build a condensed thread transcript
      const transcript = results
        .map(
          (r, i) =>
            `[Message ${i + 1}] From: ${r.from_addr}\n${r.body_text.slice(0, 600)}`
        )
        .join('\n\n---\n\n');

      const prompt = `Summarize the following email thread in 3-5 bullet points.
Focus on: the main issue, decisions made, and any open action items.
Respond with only the bullet list, no preamble.

THREAD:
${transcript}`;

      const aiResult = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 400,
      });

      const summary =
        typeof aiResult === 'object' && 'response' in aiResult
          ? (aiResult as { response: string }).response
          : JSON.stringify(aiResult);

      await env.DB.prepare(
        `INSERT OR REPLACE INTO thread_summaries
           (thread_id, summary, model, generated_at)
         VALUES (?, ?, ?, ?)`
      )
        .bind(threadId, summary, 'llama-3.1-8b-instruct', Math.floor(Date.now() / 1000))
        .run();
    }

    batch.ackAll();
  },
};
```

## REST Endpoint — Serving the Summary

```typescript
// src/api-worker.ts  (fetch handler, same Worker or separate via Service Bindings)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const threadId = url.searchParams.get('threadId');
    if (!threadId) return new Response('missing threadId', { status: 400 });

    const row = await env.DB.prepare(
      `SELECT summary, model, generated_at FROM thread_summaries WHERE thread_id = ?`
    )
      .bind(threadId)
      .first<{ summary: string; model: string; generated_at: number }>();

    if (!row) return new Response('no summary yet', { status: 404 });

    return Response.json(row);
  },
};
```

## Anti-patterns
- Summarizing inside the `email()` handler — the 30-second CPU wall clock makes it unsafe for long threads; always queue.
- Sending raw HTML to the model — strip tags first; HTML markup inflates token count and degrades summary quality.
- Storing full bodies without truncation — one large attachment can blow past D1's 1 MB row limit; cap per-message text at 6–8 KB.
- Re-summarizing on every new message — debounce via a 5-minute delay or only regenerate when the thread grows by ≥ 3 messages.
- Using `llama-3.3-70b-instruct` for high-volume summarization — the 8B model is 4× faster and costs 5× less; quality difference is minimal for summaries.

## Gotchas
- Workers AI `@cf/meta/llama-3.1-8b-instruct` returns `{ response: string }` for chat completions; assert the shape before using `.response`.
- `postal-mime` must be bundled via npm — it is not available as a built-in. Add `"postal-mime": "^2.2.0"` to `package.json`.
- The `AI` binding must be declared in `wrangler.toml` under `[ai]` — it does not accept a name override.
- `MessageBatch.ackAll()` must be called even on error paths or messages replay indefinitely.
- Thread reconstruction assumes `References` header is set correctly; some legacy MUAs omit it — fall back to subject-line matching as a secondary heuristic.

## Verification

```sql
-- Check messages are being stored
SELECT thread_id, COUNT(*) AS msg_count
  FROM email_messages
 GROUP BY thread_id
 ORDER BY msg_count DESC
 LIMIT 10;

-- Check summaries were generated
SELECT ts.thread_id, ts.model, ts.generated_at, LENGTH(ts.summary) AS summary_len
  FROM thread_summaries ts
 ORDER BY ts.generated_at DESC
 LIMIT 5;

-- Spot-check a summary
SELECT summary FROM thread_summaries WHERE thread_id = '<root-message-id>';
```

## Related
- `workers-email-reply-parsing-thread-detection.md` — building the thread chain from headers
- `email-conversation-threading-d1-workers.md` — D1 schema for threaded storage
- `email-inbound-forwarding-webhook-processing-workers.md` — inbound processing pipeline
- `email-digest-batching-queues-d1-workers.md` — queue-based batching patterns

## Sources
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/queues/
- https://github.com/postalsys/postal-mime
- https://developers.cloudflare.com/d1/
