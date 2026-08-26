# Workers AI Batch Text Embedding Pipeline Queues

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project needs to embed every anonymous post for semantic search. At peak, 5,000 posts per minute arrive. Calling Workers AI embedding synchronously in the post-submission Worker adds 80–200ms to the write path and can exhaust AI binding concurrency limits during traffic spikes. Vectorize upserts for individual posts are wasteful — Vectorize batch upserts are far more efficient. The solution: decouple embedding from submission using Cloudflare Queues, batch up to 100 posts per consumer invocation, and write embeddings to Vectorize in a single batch call.

---

## Context

The pipeline has three stages:

1. **Producer Worker** (post submission): writes a lightweight message to the Queue containing the post ID and text. Returns to the user immediately — no AI call in the hot path.
2. **Consumer Worker** (Queues trigger, batched): receives up to 100 messages per invocation, calls `ai.run('@cf/baai/bge-large-en-v1.5', { text: [...] })` in batch mode, and upserts vectors into Vectorize.
3. **Dead-letter handling**: messages that fail after retries are written to a D1 error log for manual reprocessing.

Key constraints:
- Workers AI batch embedding API accepts up to 100 texts per call.
- Queues consumer `maxBatchSize` must align with the AI batch limit.
- Vectorize `upsert` accepts up to 1000 vectors per call.
- The consumer must ack messages per-item so partial failures don't retry successfully embedded posts.

---

## Queue and Binding Setup

```toml
# wrangler.toml
[[queues.producers]]
queue = "example project-embedding-queue"
binding = "EMBEDDING_QUEUE"

[[queues.consumers]]
queue            = "example project-embedding-queue"
max_batch_size   = 100        # align with Workers AI batch limit
max_batch_timeout = 5         # seconds to wait before processing a partial batch
max_retries      = 3
dead_letter_queue = "example project-embedding-dlq"

[ai]
binding = "AI"

[[vectorize]]
binding = "VECTORIZE"
index_name = "example project-posts-v2"
```

---

## Producer Worker

```typescript
// src/workers/post-submission.ts
export interface Env {
  EMBEDDING_QUEUE: Queue<EmbeddingMessage>;
  DB: D1Database;
}

interface EmbeddingMessage {
  postId:    string;
  text:      string;
  authorKey: string; // anonymous author hash
  ts:        number;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = await req.json<{ text: string; authorKey: string }>();

    if (!body.text || body.text.length > 5000) {
      return Response.json({ error: 'Invalid post' }, { status: 400 });
    }

    const postId = crypto.randomUUID();
    const ts     = Date.now();

    // 1. Write the post to D1 first (source of truth)
    await env.DB.prepare(
      `INSERT INTO posts (id, text, author_key, ts, embedding_status)
       VALUES (?, ?, ?, ?, 'pending')`
    ).bind(postId, body.text, body.authorKey, ts).run();

    // 2. Enqueue for async embedding — fire and don't wait
    await env.EMBEDDING_QUEUE.send({
      postId,
      text: body.text,
      authorKey: body.authorKey,
      ts,
    });

    // 3. Return immediately; the user doesn't wait for embedding
    return Response.json({ postId, status: 'accepted' }, { status: 202 });
  },
};
```

---

## Consumer Worker

```typescript
// src/workers/embedding-consumer.ts
import type { MessageBatch, Message } from '@cloudflare/workers-types';

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  DB: D1Database;
}

interface EmbeddingMessage {
  postId:    string;
  text:      string;
  authorKey: string;
  ts:        number;
}

export default {
  async queue(
    batch: MessageBatch<EmbeddingMessage>,
    env: Env
  ): Promise<void> {
    const messages: Message<EmbeddingMessage>[] = batch.messages;

    // Deduplicate by postId in case of retry-induced duplicates in the batch
    const seen = new Set<string>();
    const unique = messages.filter((m) => {
      if (seen.has(m.body.postId)) {
        m.ack(); // drop duplicate silently
        return false;
      }
      seen.add(m.body.postId);
      return true;
    });

    if (unique.length === 0) return;

    // Batch embed: Workers AI accepts up to 100 texts per call
    let embeddings: number[][];
    try {
      const result = await env.AI.run(
        '@cf/baai/bge-large-en-v1.5' as any,
        { text: unique.map((m) => m.body.text) }
      ) as { data: number[][] };

      embeddings = result.data;
    } catch (err) {
      // Entire batch failed — retry all messages
      // Do NOT ack; Queues will retry up to max_retries
      console.error('Workers AI embedding batch failed:', err);
      batch.retryAll();
      return;
    }

    // Prepare Vectorize upsert payload
    const vectors: VectorizeVector[] = unique.map((m, i) => ({
      id:       m.body.postId,
      values:   embeddings[i],
      metadata: {
        authorKey:  m.body.authorKey,
        ts:         m.body.ts,
        textSnippet: m.body.text.slice(0, 200), // store first 200 chars for reranking
      },
    }));

    // Upsert into Vectorize — idempotent on postId
    let upsertSuccess = false;
    try {
      await env.VECTORIZE.upsert(vectors);
      upsertSuccess = true;
    } catch (err) {
      console.error('Vectorize upsert failed:', err);
      // Retry all if Vectorize is unavailable
      batch.retryAll();
      return;
    }

    if (upsertSuccess) {
      // Update embedding_status in D1 and ack each message
      const ids = unique.map((m) => m.body.postId);
      const placeholders = ids.map(() => '?').join(', ');

      await env.DB.prepare(
        `UPDATE posts SET embedding_status = 'indexed', indexed_at = ?
         WHERE id IN (${placeholders})`
      ).bind(Date.now(), ...ids).run();

      // Ack all successfully processed messages
      for (const m of unique) {
        m.ack();
      }
    }
  },
};
```

---

## Partial Failure Handling

```typescript
// src/workers/embedding-consumer-partial.ts
// More granular version: ack per-message, retry only failed ones

export default {
  async queue(
    batch: MessageBatch<EmbeddingMessage>,
    env: Env
  ): Promise<void> {
    const messages = batch.messages;

    // Embed all in one batch call
    const result = await env.AI.run(
      '@cf/baai/bge-large-en-v1.5' as any,
      { text: messages.map((m) => m.body.text) }
    ) as { data: number[][] };

    const vectors = result.data;

    // Upsert one-by-one to isolate failures
    await Promise.allSettled(
      messages.map(async (msg, i) => {
        try {
          await env.VECTORIZE.upsert([{
            id:     msg.body.postId,
            values: vectors[i],
            metadata: { authorKey: msg.body.authorKey, ts: msg.body.ts },
          }]);
          msg.ack();
        } catch (err) {
          // msg.retry() schedules this specific message for redelivery
          msg.retry({ delaySeconds: 30 });
          console.error(`Failed to upsert ${msg.body.postId}:`, err);
        }
      })
    );
  },
};
```

---

## Dead-Letter Queue Consumer

```typescript
// src/workers/embedding-dlq-consumer.ts
// Processes messages that exhausted all retries

export default {
  async queue(
    batch: MessageBatch<EmbeddingMessage>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      // Write to D1 for manual reprocessing
      await env.DB.prepare(
        `INSERT OR IGNORE INTO embedding_failures
           (post_id, text, author_key, ts, failed_at)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(
        msg.body.postId,
        msg.body.text,
        msg.body.authorKey,
        msg.body.ts,
        Date.now()
      ).run();

      // Update post status so the post still appears (without embedding)
      await env.DB.prepare(
        `UPDATE posts SET embedding_status = 'failed' WHERE id = ?`
      ).bind(msg.body.postId).run();

      msg.ack();
    }
  },
};
```

---

## Backfill Pipeline for Existing Posts

```typescript
// src/workers/embedding-backfill.ts
// Scheduled cron trigger to re-enqueue posts with embedding_status='pending'

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Process in pages to avoid D1 row limit per query
    let cursor = 0;
    const PAGE_SIZE = 500;

    while (true) {
      const rows = await env.DB.prepare(
        `SELECT id, text, author_key, ts FROM posts
         WHERE embedding_status = 'pending'
         ORDER BY ts ASC
         LIMIT ? OFFSET ?`
      ).bind(PAGE_SIZE, cursor).all<{ id: string; text: string; author_key: string; ts: number }>();

      if (!rows.results.length) break;

      // Send as a batch to the queue
      await env.EMBEDDING_QUEUE.sendBatch(
        rows.results.map((r) => ({
          body: {
            postId:    r.id,
            text:      r.text,
            authorKey: r.author_key,
            ts:        r.ts,
          },
        }))
      );

      cursor += PAGE_SIZE;
      if (rows.results.length < PAGE_SIZE) break;
    }
  },
};
```

---

## Anti-patterns

- **Synchronous embedding in the submission Worker**: Blocks the HTTP response for 80–200ms, prevents horizontal scaling, and creates a tight coupling between post submission reliability and AI service availability.
- **One Queue message per token or per sentence**: Queue messages have overhead. One message per post (up to 5000 characters) is the right granularity; sentence-level splitting belongs inside the consumer, not in message design.
- **Ignoring `maxBatchSize` vs AI batch limit alignment**: If `maxBatchSize = 150` but the AI API accepts 100 texts max, every invocation will throw. The Queues consumer max batch size must be <= the AI API limit.
- **Using `batch.retryAll()` for partial failures**: If 1 out of 100 messages fails, `retryAll()` re-processes all 99 successful ones (wasting cost and Vectorize capacity). Use per-message `msg.retry()` for partial failure isolation.
- **Missing deduplication**: Queues delivers at-least-once. Without deduplication on `postId`, duplicate embeddings can be upserted. `VECTORIZE.upsert` is idempotent on the vector ID, so duplicates are safe but wasteful.

---

## Gotchas

- Workers AI batch embedding returns `result.data` as an array of float arrays in the same order as the input texts. If the input array has 100 texts, `result.data` has 100 arrays. Index alignment is required; do not sort the input.
- Queues consumer invocations have a 30-second CPU time limit. For batches of 100 texts at ~1000 tokens each, the embedding call typically takes 500–1500ms — well within the limit. Monitor this if text lengths increase.
- `VECTORIZE.upsert` accepts up to 1000 vectors per call. At `maxBatchSize = 100`, you are well under the limit. Do not reduce batch size to 10 "for safety" — fewer, larger batches are significantly more efficient.
- The D1 `UPDATE ... WHERE id IN (?)` with `.bind(...ids)` has a maximum of 32766 bound parameters. At 100 IDs per batch this is never an issue, but document this limit for teams that might increase batch sizes.
- Workers AI uses `@cf/baai/bge-large-en-v1.5` (1024 dims) by default. Vectorize index must be created with matching dimensions. A dimension mismatch silently drops vectors in some Vectorize versions; verify with `VECTORIZE.describe()`.

---

## Verification

```bash
# 1. Publish a test message directly to the queue
npx wrangler queues send example project-embedding-queue \
  --message='{"postId":"test-embed-001","text":"Anonymous social platform test post","authorKey":"anon-hash-abc","ts":1724342400000}'

# 2. Check the consumer Worker logs
npx wrangler tail embedding-consumer --format=pretty

# 3. Verify the vector was upserted in Vectorize
npx wrangler vectorize query example project-posts-v2 \
  --vector='[0.1, 0.2, ...]' \
  --top-k=1 \
  --filter='{"id": "test-embed-001"}'

# 4. Check D1 for status update
npx wrangler d1 execute example project_DB \
  --command="SELECT id, embedding_status, indexed_at FROM posts WHERE id='test-embed-001'"
# Expected: embedding_status='indexed'
```

---

## Related

- `workers-ai-embeddings-batch-r2.md` — batch embedding with R2 storage for offline export
- `vectorize-batch-upsert-incremental-sync.md` — Vectorize batch upsert patterns and limits
- `workers-ai-queue-batch-processing.md` — general Queues batch processing patterns
- `embedding-batching.md` — batching strategies for embedding generation
- `vectorize-pre-post-filter-ann-metadata.md` — metadata filter patterns for the search query side
- `rag-ingestion-pipeline.md` — end-to-end RAG ingestion architecture

---

## Sources

- Cloudflare Queues consumers: https://developers.cloudflare.com/queues/configuration/consumer-workers/
- Queues batch processing: https://developers.cloudflare.com/queues/configuration/batching-retries/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Vectorize upsert: https://developers.cloudflare.com/vectorize/reference/client-api/
- Workers AI batch text embedding: https://developers.cloudflare.com/workers-ai/models/bge-large-en-v1.5/
