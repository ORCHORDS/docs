# Cloudflare Workers Queues for Async Translation Batch Processing

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A product catalogue receives 500 new items per hour. Each item must be translated into 12 locales before it is visible in those markets. Your current approach calls a translation API synchronously during the item-create request, which:
- adds 3–8 seconds of translation latency to the create response,
- fails the entire create if the translation provider is temporarily unavailable,
- cannot retry failed translations without complex orchestration code in the origin server.

You need an asynchronous translation pipeline where:
- the create request enqueues a translation job and returns immediately,
- a separate consumer Worker calls the translation API, writes results to D1, and marks the item as translated,
- failures are retried automatically with exponential back-off,
- the queue scales to absorb bursts without dropping messages.

Cloudflare Workers Queues provides exactly this: durable, ordered, at-least-once delivery between Workers, with built-in retry and dead-letter queue support.

---

## Context

Queues decouple producers (Workers that emit jobs) from consumers (Workers that process them). Messages persist in Cloudflare's infrastructure until successfully processed or exhausted through retries.

```
Create API Worker  →  Queue  →  Translation Consumer Worker
                                         │
                                   Translation API (DeepL / OpenAI / etc.)
                                         │
                                        D1  ←  writes locale content rows
                                         │
                                  Webhook / KV  ←  notifies origin of completion
```

Key properties:
- **At-least-once delivery** — a message may be delivered more than once; make your consumer idempotent.
- **Batch processing** — the consumer receives up to 100 messages per invocation; process them together for efficiency (one batch API call instead of 100 individual calls).
- **Dead-letter queue (DLQ)** — messages that exhaust retries are forwarded to a separate queue for inspection.

---

## 1. Wrangler Configuration

```toml
# wrangler.toml
name = "i18n-gateway"
compatibility_date = "2025-09-01"

# Producer binding (used by the API Worker)
[[queues.producers]]
queue   = "translation-jobs"
binding = "TRANSLATION_QUEUE"

# Consumer binding (used by the Translation Consumer Worker)
[[queues.consumers]]
queue            = "translation-jobs"
max_batch_size   = 50       # messages per consumer invocation
max_batch_timeout = 30      # seconds to wait before flushing a partial batch
max_retries      = 5
dead_letter_queue = "translation-dlq"

[[queues.producers]]
queue   = "translation-dlq"
binding = "TRANSLATION_DLQ"

[[queues.consumers]]
queue          = "translation-dlq"
max_batch_size = 10

[[d1_databases]]
binding      = "DB"
database_name = "i18n-content"
database_id  = "YOUR_D1_DATABASE_ID"
```

---

## 2. Message Schema

Define a typed message contract that both producer and consumer import:

```typescript
// src/types/translation-job.ts

export type TranslationProvider = "deepl" | "openai" | "google";

export interface TranslationJobMessage {
  /** Idempotency key — stable across retries */
  jobId: string;
  /** Reference to the content being translated */
  contentId: string;
  contentType: "product" | "article" | "ui_string";
  /** Source text (plain text or HTML) */
  sourceText: string;
  /** BCP 47 source language */
  sourceLang: string;
  /** Target locales for this job */
  targetLocales: string[];
  /** Provider preference */
  provider: TranslationProvider;
  /** ISO 8601 timestamp of when the job was enqueued */
  enqueuedAt: string;
}

export interface TranslationResultRow {
  job_id: string;
  content_id: string;
  locale: string;
  translated_text: string;
  provider: string;
  status: "pending" | "completed" | "failed";
  created_at: string;
}
```

---

## 3. Producer: Enqueue on Content Create

```typescript
// src/api/create-product.ts
import type { Queue } from "@cloudflare/workers-types";
import type { TranslationJobMessage } from "../types/translation-job";

interface Env {
  TRANSLATION_QUEUE: Queue<TranslationJobMessage>;
  DB: D1Database;
  SUPPORTED_LOCALES: string;
  DEFAULT_LOCALE: string;
}

export async function handleCreateProduct(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    title: string;
    description: string;
    sku: string;
  }>();

  const productId = crypto.randomUUID();
  const defaultLocale = env.DEFAULT_LOCALE;
  const targetLocales = env.SUPPORTED_LOCALES
    .split(",")
    .filter((l) => l !== defaultLocale);

  // 1. Write the product in the default locale immediately.
  await env.DB.prepare(
    `INSERT INTO products (id, locale, title, description, sku, translation_status)
     VALUES (?, ?, ?, ?, ?, 'source')`
  )
    .bind(productId, defaultLocale, body.title, body.description, body.sku)
    .run();

  // 2. Insert placeholder rows for each target locale so the UI can
  //    show "translation pending" without a missing-row error.
  const inserts = targetLocales.map((locale) =>
    env.DB.prepare(
      `INSERT OR IGNORE INTO products (id, locale, title, description, sku, translation_status)
       VALUES (?, ?, '', '', ?, 'pending')`
    ).bind(productId, locale, body.sku)
  );
  await env.DB.batch(inserts);

  // 3. Enqueue a single translation job covering all target locales.
  //    jobId is deterministic so a duplicate create does not produce
  //    duplicate translations (at-least-once idempotency).
  const jobId = `product:${productId}:v1`;

  const message: TranslationJobMessage = {
    jobId,
    contentId: productId,
    contentType: "product",
    sourceText: JSON.stringify({ title: body.title, description: body.description }),
    sourceLang: defaultLocale,
    targetLocales,
    provider: "deepl",
    enqueuedAt: new Date().toISOString(),
  };

  await env.TRANSLATION_QUEUE.send(message);

  return new Response(
    JSON.stringify({ id: productId, status: "created", translationStatus: "pending" }),
    { status: 201, headers: { "content-type": "application/json" } }
  );
}
```

The key discipline: **return the HTTP response before the queue message is even delivered to the consumer**. The caller gets a 201 instantly; translation happens in the background.

---

## 4. Consumer: Process Batches and Call the Translation API

```typescript
// src/consumers/translation-consumer.ts
import type {
  MessageBatch,
  Message,
  D1Database,
} from "@cloudflare/workers-types";
import type { TranslationJobMessage } from "../types/translation-job";

interface Env {
  DB: D1Database;
  DEEPL_API_KEY: string;
  WEBHOOK_SECRET: string;
  ORIGIN_WEBHOOK_URL: string;
}

interface DeepLTranslation {
  text: string;
  detected_source_language: string;
}

/**
 * Call DeepL to translate one text into multiple target languages in one request.
 * Returns a map of { locale: translatedText }.
 */
async function callDeepL(
  text: string,
  targetLangs: string[],
  apiKey: string
): Promise<Map<string, string>> {
  // DeepL supports multiple target_lang in a single request via repeated fields.
  const params = new URLSearchParams();
  params.append("text", text);
  for (const lang of targetLangs) {
    params.append("target_lang", lang.toUpperCase());
  }

  const response = await fetch("https://api-free.deepl.com/v2/translate", {
    method: "POST",
    headers: {
      Authorization: `DeepL-Auth-Key ${apiKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
  });

  if (!response.ok) {
    throw new Error(`DeepL error ${response.status}: ${await response.text()}`);
  }

  const data = await response.json<{ translations: DeepLTranslation[] }>();
  const result = new Map<string, string>();
  targetLangs.forEach((lang, i) => {
    result.set(lang, data.translations[i]?.text ?? "");
  });
  return result;
}

async function processMessage(
  msg: Message<TranslationJobMessage>,
  env: Env
): Promise<void> {
  const job = msg.body;

  // Idempotency check: skip if this job was already completed.
  const { results } = await env.DB.prepare(
    `SELECT status FROM translation_jobs WHERE job_id = ? AND status = 'completed'`
  )
    .bind(job.jobId)
    .all<{ status: string }>();

  if (results && results.length > 0) {
    console.log(`Job ${job.jobId} already completed — skipping`);
    msg.ack(); // Acknowledge so it is not re-delivered.
    return;
  }

  // Translate all target locales in one API call.
  const translations = await callDeepL(
    job.sourceText,
    job.targetLocales,
    env.DEEPL_API_KEY
  );

  // Write translated content to D1 in a single batch.
  const updates = job.targetLocales.map((locale) => {
    const translated = translations.get(locale) ?? "";
    const parsed = JSON.parse(job.sourceText) as {
      title: string;
      description: string;
    };
    const translatedParsed = (() => {
      try {
        return JSON.parse(translated) as { title: string; description: string };
      } catch {
        return { title: translated, description: "" };
      }
    })();

    return env.DB.prepare(
      `UPDATE products
       SET title = ?, description = ?, translation_status = 'completed'
       WHERE id = ? AND locale = ?`
    ).bind(
      translatedParsed.title,
      translatedParsed.description,
      job.contentId,
      locale
    );
  });

  await env.DB.batch(updates);

  // Record job completion.
  await env.DB.prepare(
    `INSERT OR REPLACE INTO translation_jobs (job_id, content_id, status, completed_at)
     VALUES (?, ?, 'completed', ?)`
  )
    .bind(job.jobId, job.contentId, new Date().toISOString())
    .run();

  // Notify origin via webhook so it can invalidate caches.
  await fetch(env.ORIGIN_WEBHOOK_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-webhook-secret": env.WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      event: "translation.completed",
      contentId: job.contentId,
      locales: job.targetLocales,
    }),
  });

  msg.ack();
}

export const translationConsumer = {
  async queue(
    batch: MessageBatch<TranslationJobMessage>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processMessage(msg, env);
      } catch (err) {
        console.error(`Failed to process job ${msg.body.jobId}:`, err);
        // Do NOT ack — Queues will retry automatically.
        msg.retry({ delaySeconds: Math.min(2 ** msg.attempts * 5, 300) });
      }
    }
  },
};
```

`msg.retry({ delaySeconds })` requests a delayed retry (exponential back-off from 5 s to 5 min). The queue retries up to `max_retries` times before forwarding to the DLQ.

---

## 5. Dead-Letter Queue Handler

```typescript
// src/consumers/dlq-handler.ts
import type { MessageBatch, D1Database, KVNamespace } from "@cloudflare/workers-types";
import type { TranslationJobMessage } from "../types/translation-job";

interface Env {
  DB: D1Database;
  ALERT_KV: KVNamespace;
}

export const dlqConsumer = {
  async queue(
    batch: MessageBatch<TranslationJobMessage>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;
      console.error(`DLQ: job ${job.jobId} exhausted retries`, job);

      // Mark content as failed so the UI can surface an error state.
      for (const locale of job.targetLocales) {
        await env.DB.prepare(
          `UPDATE products SET translation_status = 'failed' WHERE id = ? AND locale = ?`
        )
          .bind(job.contentId, locale)
          .run();
      }

      // Store a summary in KV for an alerting dashboard.
      await env.ALERT_KV.put(
        `dlq:${job.jobId}`,
        JSON.stringify({ job, failedAt: new Date().toISOString() }),
        { expirationTtl: 60 * 60 * 24 * 7 } // retain for 7 days
      );

      msg.ack();
    }
  },
};
```

---

## 6. D1 Schema for Job Tracking

```sql
-- migrations/0002_translation_jobs.sql
CREATE TABLE IF NOT EXISTS translation_jobs (
  job_id       TEXT PRIMARY KEY,
  content_id   TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
  completed_at TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_jobs_content ON translation_jobs (content_id);
CREATE INDEX idx_jobs_status  ON translation_jobs (status);
```

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Translating synchronously in the create handler | Adds seconds of latency; fails the create if the translation API is down | Enqueue and return immediately |
| One message per target locale | 12 messages × 50,000 products = 600,000 messages; wasteful | Bundle all target locales in one message; call the translation API with all targets in a single batch request |
| Not checking idempotency | At-least-once delivery means duplicates are possible; double-translating wastes API quota | Check the `translation_jobs` table before calling the API |
| Acking inside the try block before the DB write completes | If the DB write fails after ack, the message is lost | Only ack after all side effects have committed |
| Not setting `delaySeconds` on retry | All retries fire immediately, hammering a degraded translation API | Use exponential back-off via `msg.retry({ delaySeconds })` |

---

## Gotchas

- **Batch size vs. API limits:** DeepL free tier limits 500,000 characters/month; pro tier has higher limits per minute. If a batch of 50 products × 12 locales × 500 chars = 300,000 characters in one consumer invocation, you may hit rate limits. Add token-bucket logic or split into sub-batches.
- **`msg.ack()` and `msg.retry()` are mutually exclusive** — calling both on the same message is a programming error. In catch blocks, call only `retry()`.
- **Consumer Worker CPU limit:** Queues consumers run with the same 30-second CPU time limit as a normal Worker. Long-running translation API calls with many target languages can time out. Keep per-message processing under ~500 ms; split large jobs into smaller messages if needed.
- **Queue ordering:** Queues provide at-least-once, roughly FIFO delivery but not guaranteed strict ordering. Do not assume messages are processed in enqueue order.
- **`max_batch_timeout`:** If the queue is sparse, a batch waits up to `max_batch_timeout` seconds to accumulate messages before dispatching. Set this lower (e.g., 5 s) for latency-sensitive use cases, higher for throughput-oriented batch translation.
- **Secrets in messages:** Never put API keys or tokens in queue message bodies — messages may appear in logs and DLQ storage. Pass them only through `env` bindings.

---

## Verification

```bash
# Publish a test message directly via Wrangler
wrangler queues send translation-jobs \
  --message '{"jobId":"test-001","contentId":"prod-001","contentType":"product","sourceText":"{\"title\":\"Red Shoes\",\"description\":\"Comfortable.\"}","sourceLang":"en","targetLocales":["fr","de"],"provider":"deepl","enqueuedAt":"2026-08-22T00:00:00Z"}'

# Tail consumer logs to watch processing
wrangler tail --format pretty i18n-gateway

# Check D1 for completed translation
wrangler d1 execute i18n-content \
  --command "SELECT id, locale, title, translation_status FROM products WHERE id = 'prod-001'"

# Check DLQ for failures after retries exhausted
wrangler queues list
wrangler kv key list --namespace-id YOUR_ALERT_KV_NAMESPACE_ID | grep dlq
```

---

## Related Articles

- `translation-kv-caching-ttl-strategy.md`
- `d1-schema-locale-preferences-content-translations-2026.md`
- `i18n-ai-translation-pipelines-2026.md`
- `machine-translation-post-editing.md`
- `workers-durable-objects-locale-session-state.md`
- `deepl-google-mt-quality-gates-ci.md`

---

## Sources

- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Queues consumer API — https://developers.cloudflare.com/queues/configuration/javascript-apis/
- Queues dead-letter queues — https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- DeepL API reference — https://developers.deepl.com/docs/api-reference/translate
- Cloudflare D1 batch operations — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
