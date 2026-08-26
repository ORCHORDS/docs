# Workers AI: Batch Embedding Pipeline with Queues + Vectorize

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to embed thousands of documents (product catalog, knowledge-base articles, support tickets) into a Vectorize index for semantic search or RAG. Doing this synchronously in a single request exhausts CPU limits and yields poor throughput. You need an async, retryable batch pipeline.

## Context

The architecture uses three Cloudflare primitives:

1. **Workers Queue (producer)** — an ingestion endpoint that enqueues document metadata in batches.
2. **Workers Queue (consumer)** — a batch consumer that calls `env.AI.run('@cf/baai/bge-base-en-v1.5', { text: [...] })` to produce embeddings, then upserts them into Vectorize.
3. **D1** — tracks per-document status (`pending → embedding → indexed | failed`) and stores retry counters.

Queues deliver messages in batches (up to 100 per invocation) and retry failed messages automatically with exponential back-off. Vectorize supports batch upserts of up to 1 000 vectors per call. Together they handle large corpora without custom orchestration.

Model: `@cf/baai/bge-base-en-v1.5` — 768-dimension, English-optimised, low latency (~20 ms per batch of 32 texts on Workers AI free tier).

## Solution

### 1. D1 schema

```sql
-- migrations/0001_embedding_pipeline.sql
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  content     TEXT NOT NULL,
  metadata    TEXT NOT NULL DEFAULT '{}',  -- JSON
  status      TEXT NOT NULL DEFAULT 'pending',  -- pending | embedding | indexed | failed
  retry_count INTEGER NOT NULL DEFAULT 0,
  error       TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  indexed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
```

### 2. wrangler.toml bindings

```toml
[[queues.producers]]
  binding   = "EMBED_QUEUE"
  queue     = "embed-pipeline"

[[queues.consumers]]
  queue                     = "embed-pipeline"
  max_batch_size            = 32
  max_batch_timeout         = 5
  max_retries               = 3
  dead_letter_queue         = "embed-dlq"

[[ai]]
  binding = "AI"

[[vectorize]]
  binding  = "VECTORIZE"
  index_name = "documents-index"

[[d1_databases]]
  binding      = "DB"
  database_name = "embed-pipeline-db"
  database_id   = "<your-d1-id>"
```

### 3. Ingestion endpoint (producer worker)

```typescript
// src/ingest.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  EMBED_QUEUE: Queue<DocumentMessage>;
  DB: D1Database;
  AI: Ai;
}

interface DocumentMessage {
  id: string;
  content: string;
  metadata: Record<string, string>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const docs = await request.json<DocumentMessage[]>();
    if (!Array.isArray(docs) || docs.length === 0) {
      return new Response(JSON.stringify({ error: 'body must be a non-empty array' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Batch insert into D1 (mark pending)
    const placeholders = docs.map(() => '(?, ?, ?, \'pending\')').join(', ');
    const values = docs.flatMap((d) => [d.id, d.content, JSON.stringify(d.metadata ?? {})]);
    await env.DB.prepare(
      `INSERT OR IGNORE INTO documents (id, content, metadata, status) VALUES ${placeholders}`
    ).bind(...values).run();

    // Enqueue in batches of 100 (Queue send limit)
    const BATCH = 100;
    for (let i = 0; i < docs.length; i += BATCH) {
      const slice = docs.slice(i, i + BATCH);
      await env.EMBED_QUEUE.sendBatch(slice.map((d) => ({ body: d })));
    }

    return new Response(
      JSON.stringify({ queued: docs.length }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  },
};
```

### 4. Batch consumer worker

```typescript
// src/consumer.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  DB: D1Database;
}

interface DocumentMessage {
  id: string;
  content: string;
  metadata: Record<string, string>;
}

interface EmbeddingResult {
  data: number[][];
  shape: [number, number];
}

export default {
  async queue(
    batch: MessageBatch<DocumentMessage>,
    env: Env
  ): Promise<void> {
    const messages = batch.messages;
    const ids = messages.map((m) => m.body.id);

    // Mark as 'embedding' in D1
    await markStatus(env.DB, ids, 'embedding');

    // Generate embeddings in one AI call (max 100 texts per call)
    const texts = messages.map((m) => m.body.content);

    let embeddings: number[][];
    try {
      const result = await env.AI.run(
        '@cf/baai/bge-base-en-v1.5',
        { text: texts }
      ) as EmbeddingResult;
      embeddings = result.data;
    } catch (err) {
      // Retry all messages — Queue will back off automatically
      console.error('Embedding generation failed:', err);
      batch.retryAll();
      await markStatus(env.DB, ids, 'pending'); // reset so status stays consistent
      return;
    }

    // Build Vectorize upsert payload
    const vectors: VectorizeVector[] = messages.map((m, i) => ({
      id: m.body.id,
      values: embeddings[i],
      metadata: m.body.metadata ?? {},
    }));

    // Upsert into Vectorize (max 1000 per call)
    const VBATCH = 1000;
    for (let i = 0; i < vectors.length; i += VBATCH) {
      await env.VECTORIZE.upsert(vectors.slice(i, i + VBATCH));
    }

    // Mark as indexed in D1
    await env.DB.prepare(
      `UPDATE documents
         SET status = 'indexed', indexed_at = datetime('now'), error = NULL
       WHERE id IN (${ids.map(() => '?').join(', ')})`
    ).bind(...ids).run();

    // Acknowledge all messages
    batch.ackAll();
  },
};

async function markStatus(
  db: D1Database,
  ids: string[],
  status: string
): Promise<void> {
  await db.prepare(
    `UPDATE documents SET status = ? WHERE id IN (${ids.map(() => '?').join(', ')})`
  ).bind(status, ...ids).run();
}
```

### 5. Failed embedding retry from DLQ

```typescript
// src/dlq-handler.ts — consumes embed-dlq queue
export default {
  async queue(
    batch: MessageBatch<DocumentMessage>,
    env: Env
  ): Promise<void> {
    const ids = batch.messages.map((m) => m.body.id);

    // Record permanent failure in D1
    for (const id of ids) {
      await env.DB.prepare(
        `UPDATE documents
           SET status = 'failed',
               retry_count = retry_count + 1,
               error = 'DLQ: exhausted retries'
         WHERE id = ?`
      ).bind(id).run();
    }

    // Alert via email / webhook here if needed
    console.error('DLQ messages:', ids);
    batch.ackAll();
  },
};
```

### 6. Progress query

```typescript
// GET /status?ids=id1,id2,id3
async function statusHandler(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const ids = (url.searchParams.get('ids') ?? '').split(',').filter(Boolean);
  if (!ids.length) return new Response('[]', { headers: { 'Content-Type': 'application/json' } });

  const { results } = await env.DB.prepare(
    `SELECT id, status, retry_count, error, indexed_at FROM documents WHERE id IN (${ids.map(() => '?').join(', ')})`
  ).bind(...ids).all();

  return new Response(JSON.stringify(results), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Implementation Details

- `bge-base-en-v1.5` accepts up to 512 tokens per text. Texts longer than this are silently truncated by the model; split long documents before enqueueing.
- Vectorize free tier supports 5 M vectors / 768 dimensions. Monitor usage via `wrangler vectorize get documents-index --json`.
- Queue `max_batch_size = 32` is intentional — Workers AI embedding throughput is ~32 texts per 20 ms. Larger batches increase per-invocation CPU time without proportional speedup.
- D1's `INSERT OR IGNORE` prevents re-queuing already-indexed documents on re-ingest.
- `batch.retryAll()` / `message.retry()` cause the Queue to re-deliver with back-off (1 s → 10 s → 100 s by default).

## Anti-patterns

- **Calling `env.AI.run` once per document**: 10× slower and hits rate limits faster than batching all texts in one call.
- **Omitting the DLQ**: messages that exhaust retries are silently dropped, leaving orphaned `embedding` rows in D1.
- **Storing raw embeddings in D1**: 768 floats × 4 bytes = 3 KB per row. D1 row size limit is 1 MB but large tables degrade query performance — use Vectorize for vector data.
- **Not acknowledging on success**: omitting `batch.ackAll()` causes the Queue to re-deliver already-indexed documents, wasting AI quota.

## Gotchas

- Vectorize upsert is eventually consistent — newly upserted vectors may not appear in queries for up to 10 seconds.
- The AI binding throws `Error: 429 Too Many Requests` under heavy load on the free tier; handle it in the consumer and rely on Queue retry back-off rather than in-process retry loops.
- `wrangler queues create embed-pipeline` and `wrangler vectorize create documents-index --dimensions=768 --metric=cosine` must be run before deploying — they are not created by `wrangler deploy`.
- Changing the embedding model changes the vector dimensions; you must recreate the Vectorize index and re-embed all documents.

## Verification

```bash
# Deploy
wrangler deploy

# Ingest test batch
curl -X POST https://<worker>.workers.dev/ingest \
  -H 'Content-Type: application/json' \
  -d '[{"id":"doc-1","content":"Cloudflare Workers run on V8","metadata":{"source":"docs"}}]'

# Poll status
curl 'https://<worker>.workers.dev/status?ids=doc-1'
# {"id":"doc-1","status":"indexed", ...}

# Verify vector exists
wrangler vectorize get-vectors documents-index --ids=doc-1
```

## Related

- `documentation/docs/policies/ai-ml/workers-ai-rag-vectorize-d1.md` — using the Vectorize index for semantic search / RAG.
- `documentation/docs/policies/ai-ml/workers-ai-streaming-text-generation.md` — streaming inference at query time.

## Sources

- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- Vectorize batch upsert: https://developers.cloudflare.com/vectorize/reference/client-api/#upserting-vectors
- bge-base-en-v1.5 model card: https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
