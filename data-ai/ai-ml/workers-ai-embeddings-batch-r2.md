# Workers AI Embeddings Batch Processing with R2

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have tens of thousands of documents stored in R2 that need to be embedded and indexed into Vectorize. Running
individual embedding requests per document is too slow and risks hitting Workers AI rate limits. You need a
fault-tolerant, resumable batch pipeline that reads from R2, embeds in micro-batches, and writes vectors to Vectorize
while recording progress in D1.

## Context

Workers AI enforces per-minute token and request limits that vary by model and account tier. For the
`@cf/baai/bge-base-en-v1.5` embedding model (768-dim) the practical safe throughput is around 200 texts/min on the
free tier and higher on paid. A Queue-backed batch Worker consumes R2 object keys from a queue, embeds each batch of
texts, upserts into Vectorize, and checkpoints completion in D1. Retries are handled by Queue dead-letter redelivery,
so partial batch failures do not re-process already-embedded documents.

## R2 Object Discovery and Queue Population

Enumerate R2 keys and enqueue them for the batch Worker. Run this as a scheduled Cron Trigger.

```typescript
interface Env {
  DOCS_BUCKET: R2Bucket;
  EMBED_QUEUE: Queue<{ key: string }>;
  DB: D1Database;
  AI: Ai;
  VECTORIZE: VectorizeIndex;
}

export const scheduled: ExportedHandlerScheduledHandler<Env> = async (
  _event,
  env
) => {
  let cursor: string | undefined;
  let enqueued = 0;

  do {
    const list = await env.DOCS_BUCKET.list({
      limit: 1000,
      cursor,
      prefix: "docs/",
    });

    const newKeys: string[] = [];
    for (const obj of list.objects) {
      // Skip already-embedded keys
      const row = await env.DB.prepare(
        "SELECT 1 FROM embed_status WHERE r2_key = ? AND status = 'done'"
      )
        .bind(obj.key)
        .first();
      if (!row) newKeys.push(obj.key);
    }

    if (newKeys.length > 0) {
      // Enqueue in batches of 10 so each Queue message = one micro-batch
      for (let i = 0; i < newKeys.length; i += 10) {
        const chunk = newKeys.slice(i, i + 10);
        await env.EMBED_QUEUE.sendBatch(
          chunk.map((key) => ({ body: { key } }))
        );
      }
      enqueued += newKeys.length;
    }

    cursor = list.truncated ? list.cursor : undefined;
  } while (cursor);

  console.log(`Enqueued ${enqueued} keys for embedding`);
};
```

## Queue Consumer: Fetch, Embed, Upsert

Process each batch message: read the R2 object, run embedding inference, write to Vectorize, record completion.

```typescript
async function embedAndUpsert(
  env: Env,
  keys: string[]
): Promise<{ succeeded: string[]; failed: string[] }> {
  const succeeded: string[] = [];
  const failed: string[] = [];

  // Fetch all documents for this micro-batch in parallel
  const fetchResults = await Promise.allSettled(
    keys.map(async (key) => {
      const obj = await env.DOCS_BUCKET.get(key);
      if (!obj) throw new Error(`R2 object not found: ${key}`);
      const text = await obj.text();
      return { key, text: text.slice(0, 2048) }; // truncate to model max
    })
  );

  const docs: { key: string; text: string }[] = [];
  for (let i = 0; i < fetchResults.length; i++) {
    const result = fetchResults[i];
    if (result.status === "fulfilled") {
      docs.push(result.value);
    } else {
      failed.push(keys[i]);
    }
  }

  if (!docs.length) return { succeeded, failed };

  // Single batched embedding call
  const embeddingResponse = await (env.AI as any).run(
    "@cf/baai/bge-base-en-v1.5",
    { text: docs.map((d) => d.text) }
  ) as { data: number[][] };

  const vectors = embeddingResponse.data.map((values, i) => ({
    id: docs[i].key,
    values,
    metadata: { r2Key: docs[i].key, indexedAt: Date.now() },
  }));

  try {
    await env.VECTORIZE.upsert(vectors);
    for (const doc of docs) succeeded.push(doc.key);
  } catch (err) {
    // Vectorize upsert is atomic per batch — on failure, none are written
    for (const doc of docs) failed.push(doc.key);
  }

  return { succeeded, failed };
}

export const queue: ExportedHandlerQueueHandler<Env, { key: string }> = async (
  batch,
  env
) => {
  const keys = batch.messages.map((m) => m.body.key);
  const { succeeded, failed } = await embedAndUpsert(env, keys);

  // Checkpoint successes in D1
  if (succeeded.length > 0) {
    const placeholders = succeeded.map(() => "(?, 'done', ?)").join(",");
    await env.DB.prepare(
      `INSERT OR REPLACE INTO embed_status (r2_key, status, indexed_at)
       VALUES ${placeholders}`
    )
      .bind(...succeeded.flatMap((k) => [k, Date.now()]))
      .run();
  }

  // Retry failed messages via Queue redelivery
  for (const msg of batch.messages) {
    if (failed.includes(msg.body.key)) {
      msg.retry({ delaySeconds: 60 });
    } else {
      msg.ack();
    }
  }
};
```

## Progress Monitoring and D1 Schema

```typescript
// schema.sql
/*
CREATE TABLE IF NOT EXISTS embed_status (
  r2_key     TEXT    PRIMARY KEY,
  status     TEXT    NOT NULL,  -- 'pending' | 'done' | 'failed'
  indexed_at INTEGER
);
*/

// Query embedding progress from a diagnostic Worker route
async function getProgress(env: Env): Promise<Response> {
  const stats = await env.DB.prepare(
    `SELECT status, COUNT(*) AS n FROM embed_status GROUP BY status`
  ).all<{ status: string; n: number }>();

  const summary = Object.fromEntries(
    stats.results.map((r) => [r.status, r.n])
  );

  return Response.json({ progress: summary });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname === "/progress") {
      return getProgress(env);
    }
    return new Response("Not Found", { status: 404 });
  },
  scheduled,
  queue,
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Calling `env.AI.run()` once per document inside a loop — each call incurs HTTP round-trip latency and counts
  against per-request rate limits; always batch texts into a single call up to the model's `text` array limit.
- Storing full document text in Vectorize metadata — metadata is for filtering identifiers only; retrieve the source
  text from R2 using the stored `r2Key` when needed.
- Ignoring Vectorize upsert batch size limits — the current maximum is 1 000 vectors per `upsert()` call; split
  larger batches accordingly.

## Gotchas

- `env.AI.run()` with the `text` array variant for BGE models returns `{ data: number[][] }`, not `{ result: ... }`.
  The schema differs from text-generation models; always check the model-specific response shape.
- R2 `list()` does not guarantee lexicographic order for resumable cursors across separate cron invocations. Use the
  D1 checkpoint table as the true source of truth for what has been embedded, not R2 cursor position.

## Verification

```bash
# Trigger the scheduled job manually (wrangler)
wrangler dev --test-scheduled

# Check queue depth in Cloudflare dashboard or via API
curl -s "https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/queues/{QUEUE_ID}" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.producers'

# Check embedding progress via Worker diagnostic route
curl https://your-worker.workers.dev/progress | jq .
# Expected: {"progress":{"done":12500,"pending":0}}
```

## Related

- `ai-ml/embedding-batching.md`
- `ai-ml/embedding-generation-patterns.md`
- `ai-ml/workers-ai-queue-batch-processing.md`
- `ai-ml/cloudflare-vectorize-patterns.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/vectorize/reference/client-api/
