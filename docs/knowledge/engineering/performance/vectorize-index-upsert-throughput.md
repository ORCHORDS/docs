# Vectorize Index Upsert Throughput

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
Bulk-loading embeddings into a Vectorize index via individual upsert calls stalls at ~200 vectors/s and triggers `429 Too Many Requests` errors. Batching Workers AI embedding generation with Vectorize upsert batches raises sustainable throughput to 10 000+ vectors/s while staying within per-account rate limits.

## Context
Vectorize indexes are built for high-read, moderate-write workloads: queries are fast (ANN via HNSW), but upsert throughput is bounded by the upsert rate limit (currently 1 000 vectors per batch, 1 000 upserts/s account-wide in production). Workers AI `@cf/baai/bge-base-en-v1.5` produces 768-dimension embeddings with a batch limit of 100 inputs per `run()` call. The optimal pipeline fans out embedding generation to Workers AI in parallel batches of ≤ 100 texts, then upserts the resulting vectors to Vectorize in batches of ≤ 1 000. Adding a Queue between the ingestion Worker and the index worker provides backpressure, automatic retry, and throughput smoothing.

## Pattern 1 — Schema and Environment Bindings

```typescript
// wrangler.toml (relevant sections)
// [[vectorize]]
// binding = "VECTORIZE"
// index_name = "product-embeddings"
//
// [ai]
// binding = "AI"
//
// [[queues.producers]]
// binding = "EMBED_QUEUE"
// queue = "embed-jobs"
//
// [[queues.consumers]]
// queue = "embed-jobs"
// max_batch_size = 100
// max_batch_timeout = 5
// max_retries = 3

interface EmbedJob {
  id: string;         // Document ID, used as Vectorize vector id
  text: string;       // Text to embed
  metadata: Record<string, string | number | boolean>;
}

interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  EMBED_QUEUE: Queue<EmbedJob>;
  KV: KVNamespace;
}
```

## Pattern 2 — Chunked Enqueue from Ingestion Worker

```typescript
// Ingestion endpoint — accepts a bulk document payload and enqueues embed jobs
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const docs = await request.json<EmbedJob[]>();
    if (!Array.isArray(docs) || docs.length === 0) {
      return new Response("Bad Request: expected non-empty array", { status: 400 });
    }

    // Chunk into batches of 100 (Queue sendBatch limit is 100 messages)
    const BATCH_SIZE = 100;
    for (let i = 0; i < docs.length; i += BATCH_SIZE) {
      const chunk = docs.slice(i, i + BATCH_SIZE);
      await env.EMBED_QUEUE.sendBatch(chunk.map((doc) => ({ body: doc })));
    }

    return Response.json({ enqueued: docs.length });
  },
};
```

## Pattern 3 — Queue Consumer: Batch Embed + Vectorize Upsert

```typescript
// Consumer Worker — receives up to 100 jobs per batch from the queue
export default {
  async queue(batch: MessageBatch<EmbedJob>, env: Env): Promise<void> {
    const jobs = batch.messages.map((m) => m.body);

    // Step 1: Generate embeddings for all texts in one Workers AI call
    const texts = jobs.map((j) => j.text);
    let embeddings: number[][];

    try {
      const result = await env.AI.run("@cf/baai/bge-base-en-v1.5", { text: texts });
      embeddings = result.data;
    } catch (err) {
      // Transient AI failure — retry whole batch
      console.error("Workers AI embedding failed", err);
      batch.retryAll();
      return;
    }

    // Step 2: Build Vectorize vector objects
    const vectors: VectorizeVector[] = jobs.map((job, i) => ({
      id: job.id,
      values: embeddings[i],
      metadata: job.metadata,
    }));

    // Step 3: Upsert to Vectorize (max 1 000 vectors per call)
    // Our batch is ≤ 100, so one upsert call suffices
    try {
      await env.VECTORIZE.upsert(vectors);
      batch.ackAll();
    } catch (err) {
      console.error("Vectorize upsert failed", err);
      batch.retryAll();
    }
  },
};
```

## Pattern 4 — Parallel Embedding for Large In-Memory Batches

```typescript
// When processing outside a Queue (e.g. a one-shot migration Worker),
// fan out Workers AI calls in parallel with a concurrency cap.
async function embedAndUpsertBulk(
  env: Env,
  docs: EmbedJob[],
  concurrency = 5,
): Promise<void> {
  const AI_BATCH = 100;      // Workers AI max texts per run()
  const VZ_BATCH = 1_000;    // Vectorize max vectors per upsert()

  // Split into AI batches
  const aiBatches: EmbedJob[][] = [];
  for (let i = 0; i < docs.length; i += AI_BATCH) {
    aiBatches.push(docs.slice(i, i + AI_BATCH));
  }

  // Embed in parallel with concurrency limit
  const allVectors: VectorizeVector[] = [];
  const queue = [...aiBatches];

  async function worker(): Promise<void> {
    while (queue.length > 0) {
      const batch = queue.shift()!;
      const { data: embeddings } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
        text: batch.map((d) => d.text),
      });
      embeddings.forEach((values, idx) => {
        allVectors.push({ id: batch[idx].id, values, metadata: batch[idx].metadata });
      });
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));

  // Upsert to Vectorize in batches of 1 000
  for (let i = 0; i < allVectors.length; i += VZ_BATCH) {
    await env.VECTORIZE.upsert(allVectors.slice(i, i + VZ_BATCH));
  }
}
```

## Pattern 5 — Deduplication and Progress Tracking via KV

```typescript
const PROGRESS_PREFIX = "vz:progress:";

async function upsertWithDedup(
  env: Env,
  vectors: VectorizeVector[],
  indexId: string,
): Promise<{ upserted: number; skipped: number }> {
  const keys = vectors.map((v) => `${PROGRESS_PREFIX}${indexId}:${v.id}`);

  // Bulk check KV for already-indexed IDs (max 100 keys per getAll not available — use batch gets)
  const existingChecks = await Promise.all(
    keys.map((k) => env.KV.get(k, { type: "text" })),
  );

  const toUpsert = vectors.filter((_, i) => existingChecks[i] === null);
  const skipped = vectors.length - toUpsert.length;

  if (toUpsert.length > 0) {
    await env.VECTORIZE.upsert(toUpsert);

    // Mark as indexed with 24 h TTL (re-index allowed after expiry)
    await Promise.allSettled(
      toUpsert.map((v) =>
        env.KV.put(`${PROGRESS_PREFIX}${indexId}:${v.id}`, "1", { expirationTtl: 86_400 }),
      ),
    );
  }

  return { upserted: toUpsert.length, skipped };
}
```

## Anti-patterns
- Upsering one vector at a time in a loop — each `upsert()` is an HTTP call; serial single-vector upserts achieve <100 vectors/s and exhaust the per-Worker CPU budget before the data is loaded
- Sending texts longer than the model's context window (512 tokens for `bge-base-en-v1.5`) — the model silently truncates, producing lower-quality embeddings; chunk long documents before embedding
- Not chunking `Workers AI.run()` input below the 100-item limit — requests with >100 texts return a 400 error
- Sharing a single Vectorize index across multiple dimensions/models — embedding dimensions must match the index's configured dimensions; mixing models requires separate indexes
- Calling `VECTORIZE.upsert()` without handling `429` rate-limit responses — always wrap in retry logic with exponential backoff when doing bulk loads outside a Queue

## Gotchas
- Vectorize upserts are eventually consistent — a vector upserted now may not appear in query results for up to 1 minute; do not immediately query after upsert in tests expecting instant visibility
- The `metadata` object per vector supports only string, number, and boolean values; nested objects are rejected silently or cause a validation error depending on SDK version
- Workers AI batch size is 100 **inputs**, not 100 tokens — a batch of 100 texts each 1 token long is still 100 inputs; reduce batch size for very long texts to avoid context-window truncation
- Vectorize indexes have a per-account vector limit; monitor `VECTORIZE.describe()` output for `vectorsCount` and alert before approaching the limit to avoid silent upsert drops
- `VectorizeVector.id` must be a string of ≤ 64 bytes; numeric IDs must be stringified, and UUIDs with hyphens (36 chars) are safe

## Verification
```bash
# Check index status and vector count
npx wrangler vectorize get-index product-embeddings

# Query a test vector to verify upsert succeeded
npx wrangler vectorize query product-embeddings \
  --vector "[0.1, 0.2, ...]" \
  --top-k 3 \
  --return-metadata all

# Tail the consumer Worker for embed throughput
wrangler tail embed-consumer --format json | \
  jq '{batchSize: .event.batchSize, outcome: .outcome}'

# Analytics Engine throughput query
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT toStartOfMinute(timestamp) AS min, sum(double1) AS vectors_upserted
          FROM vectorize_ingest WHERE timestamp > now() - INTERVAL '1' HOUR
          GROUP BY min ORDER BY min"
```

## Related
- `vectorize-query-latency-optimization.md`
- `workers-ai-batch-inference-throughput.md`
- `workers-ai-inference-response-caching.md`
- `queues-consumer-backpressure-flow-control.md`
- `kv-bulk-get-batching.md`

## Sources
- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- https://developers.cloudflare.com/vectorize/platform/limits/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
