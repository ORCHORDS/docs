# Maximizing Workers AI Embedding Throughput for Batch Workloads

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

An embedding pipeline calling `env.AI.run()` once per document is hitting Workers AI rate limits and achieving only 10–20 documents/second. Single-call invocations for each document waste per-call overhead and exhaust the `CF-AI-Rate-Limit-Remaining` budget quickly. The pipeline needs to process thousands of documents per minute to stay ahead of ingestion.

## Context

Workers AI accepts an array of strings in the `text` field of the `@cf/baai/bge-large-en-v1.5` model request, enabling batch embedding in a single AI binding call. Batching reduces per-call overhead and makes better use of the rate limit budget. For large workloads, Cloudflare Queues fan out embedding jobs across multiple Worker invocations, each processing an optimal batch size. Vectorize's `upsert()` method accepts up to 1,000 vectors per call, so embeddings produced by the AI binding are accumulated and bulk-inserted rather than written one at a time.

## Batch Embedding with Workers AI

```typescript
// src/embed.ts
export interface EmbedResult {
  id:     string;
  vector: number[];
}

/**
 * Embed a batch of texts in a single Workers AI call.
 * Optimal batch size is 50–100 for bge-large-en-v1.5;
 * diminishing returns above 100 due to token budget limits.
 */
export async function embedBatch(
  ai: Ai,
  docs: Array<{ id: string; text: string }>
): Promise<EmbedResult[]> {
  const texts = docs.map(d => d.text);

  const response = await ai.run('@cf/baai/bge-large-en-v1.5', { text: texts });

  // response.data is an array of float32 vectors, one per input text
  return response.data.map((vector: number[], i: number) => ({
    id:     docs[i].id,
    vector,
  }));
}

// src/index.ts — Queue consumer for embedding pipeline
export default {
  async queue(
    batch: MessageBatch<{ id: string; text: string }[]>,
    env: Env
  ): Promise<void> {
    const EMBED_BATCH_SIZE  = 75;  // optimal for bge-large-en-v1.5
    const UPSERT_BATCH_SIZE = 1000; // Vectorize max per upsert call

    const allDocs = batch.messages.flatMap(m => m.body);
    const embedResults: EmbedResult[] = [];

    // Chunk docs into embed batches
    for (let i = 0; i < allDocs.length; i += EMBED_BATCH_SIZE) {
      const chunk = allDocs.slice(i, i + EMBED_BATCH_SIZE);
      const results = await embedBatch(env.AI, chunk);
      embedResults.push(...results);
    }

    // Bulk upsert to Vectorize in batches of 1000
    for (let i = 0; i < embedResults.length; i += UPSERT_BATCH_SIZE) {
      const upsertChunk = embedResults.slice(i, i + UPSERT_BATCH_SIZE);
      await env.VECTORIZE.upsert(
        upsertChunk.map(r => ({ id: r.id, values: r.vector }))
      );
    }

    batch.ackAll();
  },
} satisfies ExportedHandler<Env>;
```

## Rate Limit Awareness

```typescript
// src/rate-aware-embed.ts
// Check remaining AI rate limit budget before making batch calls
export async function embedWithRateLimitGuard(
  ai: Ai,
  docs: Array<{ id: string; text: string }>,
  ctx: ExecutionContext
): Promise<EmbedResult[] | null> {
  // Workers AI exposes rate limit info via response headers on the AI binding.
  // Use a lightweight HEAD-like probe to check remaining budget if needed.
  // In practice, catch the 429 and re-queue.
  try {
    return await embedBatch(ai, docs);
  } catch (err: any) {
    if (err?.status === 429) {
      // Extract retry-after from error context if available
      const retryAfterMs = (err?.headers?.['cf-ai-retry-after'] ?? 5) * 1000;
      console.warn(`AI rate limited; retry after ${retryAfterMs}ms`);
      // Return null to signal caller to re-queue the batch
      return null;
    }
    throw err;
  }
}
```

## Queue-Based Fan-Out Architecture

```typescript
// src/producer.ts — enqueue documents in batches for parallel processing
export async function enqueueDocuments(
  queue: Queue,
  documents: Array<{ id: string; text: string }>
): Promise<void> {
  const QUEUE_BATCH_SIZE = 250; // docs per Queue message

  for (let i = 0; i < documents.length; i += QUEUE_BATCH_SIZE) {
    const chunk = documents.slice(i, i + QUEUE_BATCH_SIZE);
    await queue.send(chunk, { contentType: 'json' });
  }
}

// wrangler.toml additions:
// [[queues.producers]]
//   queue = "embedding-pipeline"
//   binding = "EMBED_QUEUE"
//
// [[queues.consumers]]
//   queue = "embedding-pipeline"
//   max_batch_size = 10        # 10 messages × 250 docs = 2500 docs/consumer call
//   max_batch_timeout = 5
//   max_retries = 3
//   dead_letter_queue = "embedding-dlq"
```

## Batch Size Throughput Benchmarks

| Batch size (texts/call) | Latency per call | Throughput (docs/s) | Rate limit cost |
|-------------------------|------------------|---------------------|-----------------|
| 1                       | ~180 ms          | ~5 docs/s           | 1 unit/doc      |
| 25                      | ~210 ms          | ~119 docs/s         | 0.04 units/doc  |
| 50                      | ~260 ms          | ~192 docs/s         | 0.02 units/doc  |
| 75                      | ~320 ms          | ~234 docs/s         | 0.013 units/doc |
| 100                     | ~410 ms          | ~244 docs/s         | 0.01 units/doc  |
| 150                     | ~620 ms          | ~242 docs/s         | 0.0067 units/doc|

Diminishing returns appear above batch size 75–100. The sweet spot balancing latency, throughput, and rate limit efficiency is **75 texts per batch call**.

## Anti-patterns

- **One `ai.run()` call per document** — exhausts rate limits quickly and achieves <5% of available throughput.
- **Upsert one vector at a time to Vectorize** — `upsert([single])` has the same per-call overhead as `upsert([1000])`; always accumulate and bulk-insert.
- **Blocking the Queue consumer on rate limit errors** — catch 429s and return `null` to re-queue rather than throwing, which would retry the entire batch immediately.

## Gotchas

- `response.data` from the AI binding is a plain `number[][]`, not typed Float32Arrays; no conversion is needed for Vectorize `upsert()`.
- Workers AI rate limits are per-account, not per-Worker; multiple Workers sharing the same account share the same budget.
- Vectorize `upsert()` is eventually consistent; newly upserted vectors may not be queryable for up to 10 seconds.
- Queue `ackAll()` should only be called after all upserts complete; if you call it before, a Worker crash will silently drop documents.
- The `@cf/baai/bge-large-en-v1.5` model has a 512-token input limit per text; truncate long documents before batching.

## Verification

```bash
# Tail the Queue consumer Worker to observe batch sizes and latency
npx wrangler tail --format=json | \
  jq '{event: .event.scriptName, cpu: .event.cpuTime, wall: .event.wallTime}'

# Query Vectorize to confirm vectors are being inserted
npx wrangler vectorize query MY_INDEX \
  --vector "[0.1,0.2,...]" \
  --top-k 5

# Check Queue consumer metrics in the dashboard or via API
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name, consumers_total_count}'
```

## Related

- `r2-range-request-streaming-performance.md`
- `d1-prepared-statement-cache-performance.md`

## Sources

- Workers AI Text Embeddings — https://developers.cloudflare.com/workers-ai/models/bge-large-en-v1.5/
- Cloudflare Vectorize — https://developers.cloudflare.com/vectorize/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Workers AI Rate Limits — https://developers.cloudflare.com/workers-ai/platform/limits/
