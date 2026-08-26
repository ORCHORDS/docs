# Workers AI Embedding Batch Generation with Vectorize Upsert

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You have a corpus of documents (product descriptions, KB articles, user profiles) and you want to generate dense embeddings for each one using Workers AI, then upsert them into a Vectorize index so they are immediately queryable for semantic similarity search.

## Context
Workers AI exposes the `@cf/baai/bge-base-en-v1.5` (768-dim) and `@cf/baai/bge-small-en-v1.5` (384-dim) models via `env.AI.run()`. Vectorize `upsert()` accepts batches of up to 1,000 vectors per call. The pattern below chunks an input list of documents, calls the embedding model once per chunk, then upserts the resulting vectors. Running this in a Durable Object alarm or a Queue consumer avoids the 30-second CPU wall of a plain Worker.

## Embedding Model Setup

`wrangler.toml`:
```toml
name = "embedding-sync"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[ai]]
binding = "AI"

[[vectorize]]
binding = "PRODUCT_VECTORS"
index_name = "product-embeddings"
```

Create the index once:
```bash
npx wrangler vectorize create product-embeddings \
  --dimensions=768 \
  --metric=cosine
```

## Batch Embedding Worker

```typescript
// src/index.ts
export interface Env {
  AI: Ai;
  PRODUCT_VECTORS: VectorizeIndex;
  SYNC_QUEUE: Queue<SyncMessage>;
}

interface Document {
  id: string;
  text: string;
  metadata?: Record<string, string | number | boolean>;
}

interface SyncMessage {
  docs: Document[];
}

const EMBED_CHUNK = 50; // max texts per AI.run call to avoid timeouts
const UPSERT_CHUNK = 500; // max vectors per Vectorize upsert

function chunkArray<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    out.push(arr.slice(i, i + size));
  }
  return out;
}

async function embedAndUpsert(
  docs: Document[],
  env: Env,
  ctx: ExecutionContext
): Promise<{ inserted: number; errors: string[] }> {
  const errors: string[] = [];
  let inserted = 0;

  const embedChunks = chunkArray(docs, EMBED_CHUNK);

  for (const chunk of embedChunks) {
    // Generate embeddings for this chunk
    let embeddingResult: { data: number[][] };
    try {
      embeddingResult = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
        text: chunk.map((d) => d.text),
      });
    } catch (err) {
      errors.push(`Embedding failed for chunk starting at id=${chunk[0].id}: ${err}`);
      continue;
    }

    // Pair each doc with its vector
    const vectors: VectorizeVector[] = chunk.map((doc, i) => ({
      id: doc.id,
      values: embeddingResult.data[i],
      metadata: doc.metadata ?? {},
      namespace: "default",
    }));

    // Upsert in Vectorize-safe batches
    for (const upsertBatch of chunkArray(vectors, UPSERT_CHUNK)) {
      try {
        const result = await env.PRODUCT_VECTORS.upsert(upsertBatch);
        inserted += result.count;
      } catch (err) {
        errors.push(`Vectorize upsert failed: ${err}`);
      }
    }
  }

  return { inserted, errors };
}

// HTTP endpoint: POST /sync  body: { docs: [...] }
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (req.method !== "POST" || new URL(req.url).pathname !== "/sync") {
      return new Response("Not found", { status: 404 });
    }

    const body = (await req.json()) as { docs: Document[] };
    if (!Array.isArray(body.docs) || body.docs.length === 0) {
      return new Response(JSON.stringify({ error: "docs array required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // For large batches, offload to a Queue so the HTTP response returns fast
    if (body.docs.length > 200) {
      const batches = chunkArray(body.docs, 200);
      for (const batch of batches) {
        await env.SYNC_QUEUE.send({ docs: batch });
      }
      return new Response(
        JSON.stringify({ queued: body.docs.length }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    const result = await embedAndUpsert(body.docs, env, ctx);
    return new Response(JSON.stringify(result), {
      headers: { "Content-Type": "application/json" },
    });
  },

  // Queue consumer for large batches
  async queue(batch: MessageBatch<SyncMessage>, env: Env, ctx: ExecutionContext): Promise<void> {
    for (const msg of batch.messages) {
      const { inserted, errors } = await embedAndUpsert(msg.body.docs, env, ctx);
      if (errors.length > 0) {
        console.error("Embedding errors", errors);
        msg.retry(); // let DLQ handle persistent failures
      } else {
        console.log(`Upserted ${inserted} vectors`);
        msg.ack();
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Semantic Search Endpoint

```typescript
// src/search.ts — add as a separate route or a second Worker
export async function handleSearch(req: Request, env: Env): Promise<Response> {
  const { query, topK = 5, filter } = (await req.json()) as {
    query: string;
    topK?: number;
    filter?: VectorizeVectorMetadataFilter;
  };

  const { data: queryVec } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [query],
  });

  const results = await env.PRODUCT_VECTORS.query(queryVec[0], {
    topK,
    returnMetadata: "all",
    ...(filter ? { filter } : {}),
  });

  return new Response(JSON.stringify(results.matches), {
    headers: { "Content-Type": "application/json" },
  });
}
```

## Incremental Sync Pattern

For keeping Vectorize in sync with a D1 table:

```typescript
// Track last-synced timestamp in KV
async function incrementalSync(env: Env & { KV: KVNamespace; DB: D1Database }) {
  const lastSync = (await env.KV.get("last_embed_sync")) ?? "1970-01-01T00:00:00Z";

  const { results } = await env.DB.prepare(
    `SELECT id, body AS text, category, price
     FROM products
     WHERE updated_at > ?
     ORDER BY updated_at ASC
     LIMIT 500`
  )
    .bind(lastSync)
    .all<{ id: string; text: string; category: string; price: number }>();

  if (results.length === 0) return;

  const docs: Document[] = results.map((r) => ({
    id: r.id,
    text: r.text,
    metadata: { category: r.category, price: r.price },
  }));

  await embedAndUpsert(docs, env as unknown as Env, {} as ExecutionContext);
  await env.KV.put("last_embed_sync", new Date().toISOString());
}
```

## Anti-patterns
- **Embedding one document at a time** — batching reduces AI inference round-trips by up to 50x for the same number of documents.
- **Ignoring the 1,000-vector Vectorize upsert limit** — exceeding it returns a 413 and silently drops the whole batch.
- **Using a plain Worker for 10k+ document syncs** — CPU time limit (30 s on Bundled, 5 minutes on Unbound) will terminate the request; use Queue consumers or DO alarms instead.
- **Storing full document text in Vectorize metadata** — metadata is capped at 1 KB per vector; store only filterable fields and retrieve full text from D1/R2 by ID.
- **Sharing one Vectorize index across incompatible embedding models** — dimension and metric are fixed at creation; mixing models corrupts similarity scores.

## Gotchas
- `bge-base-en-v1.5` returns 768-dim vectors; `bge-small-en-v1.5` returns 384-dim. The index dimension must match at creation time — it cannot be changed later.
- Workers AI `text` input can be a single string or an array; using an array gives you one `data[i]` per element in the response — ensure index alignment if any texts are empty strings (model returns a zero-vector).
- Vectorize `upsert()` is an upsert-by-ID: re-ingesting the same ID replaces the old vector and metadata atomically.
- `returnMetadata: "all"` in `query()` returns the full metadata map; `"indexed"` returns only the filterable subset — choose carefully to avoid over-fetching.
- Rate limits on Workers AI models (requests per minute) can cause 429 errors; add exponential back-off around `env.AI.run()` calls in production.

## Verification
1. POST a small batch: `curl -X POST https://<worker>/sync -H 'Content-Type: application/json' -d '{"docs":[{"id":"1","text":"blue running shoes"}]}'` — expect `{"inserted":1,"errors":[]}`.
2. Query: `curl -X POST https://<worker>/search -d '{"query":"sneakers for jogging","topK":3}'` — the inserted vector should appear in results.
3. Check index stats: `npx wrangler vectorize info product-embeddings` — `vectorCount` should increment.
4. Verify incremental sync by updating a D1 row and re-running the sync cron; confirm the vector's metadata reflects the new values via a `query()` call with `returnMetadata: "all"`.

## Related
- `vectorize-best-practices.md`
- `vectorize-hybrid-metadata-filter-search.md`
- `workers-ai-edge-inference.md`
- `cloudflare-queues-dead-letter-dlq.md`
- `d1-time-series-patterns.md`

## Sources
- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- https://developers.cloudflare.com/vectorize/get-started/embeddings/
