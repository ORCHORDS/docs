# CQRS Read Model with D1 and Vectorize for Semantic Search

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A write model captures structured domain events in D1, but the product team needs a search surface that understands natural-language queries ("comfortable running shoes under $80") not just keyword filters. Duplicating embedding generation inside every query Worker couples read logic to the AI layer and produces inconsistent vectors when models are updated.

## Context

CQRS separates write and read responsibilities; the read model is a purpose-built projection of the write model optimised for its query patterns. When the query pattern is semantic, the read model is a Vectorize index maintained by a projection Worker that subscribes to domain events via Queues. Write Workers own D1; projection Workers own Vectorize. Query Workers combine D1 metadata filters with Vectorize ANN (approximate nearest neighbour) search to return ranked, semantically relevant results — a pattern sometimes called "hybrid search."

## Architecture

```
Write Path
  └─ D1 (canonical write model)
  └─ Queue: "domain-events"

Projection Worker (Queue consumer)
  ├─ re-reads D1 row for full content
  ├─ generates embedding via Workers AI
  └─ upserts vector into Vectorize index (metadata = D1 primary key)

Query Worker (read path)
  ├─ embed query string → Workers AI
  ├─ Vectorize.query(vector, {topK, filter}) → ranked id list
  └─ D1 SELECT WHERE id IN (...) → enriched results
```

## D1 Write Model Schema

```sql
-- migrations/0001_products.sql
CREATE TABLE products (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT NOT NULL,
  category    TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  active      INTEGER NOT NULL DEFAULT 1,
  updated_at  TEXT NOT NULL
);

-- Projection checkpoint: tracks last processed event offset
CREATE TABLE vectorize_checkpoint (
  index_name  TEXT PRIMARY KEY,
  last_event_id TEXT
);
```

## Projection Worker: D1 → Vectorize

```typescript
// src/projection-worker.ts
interface Env {
  DB: D1Database;
  AI: Ai;
  PRODUCT_INDEX: VectorizeIndex;
}

interface ProductEvent {
  eventId: string;
  productId: string;
  type: "ProductCreated" | "ProductUpdated" | "ProductDeleted";
}

interface ProductRow {
  id: string;
  name: string;
  description: string;
  category: string;
  price_cents: number;
  active: number;
}

async function embedProduct(env: Env, product: ProductRow): Promise<number[]> {
  // Combine fields into a single semantic text blob for embedding
  const text = [
    product.name,
    product.description,
    `Category: ${product.category}`,
    `Price: $${(product.price_cents / 100).toFixed(2)}`,
  ].join(". ");

  const result = await env.AI.run(
    "@cf/baai/bge-small-en-v1.5",
    { text: [text] }
  ) as { data: number[][] };

  return result.data[0];
}

export default {
  async queue(batch: MessageBatch<ProductEvent>, env: Env): Promise<void> {
    const toUpsert: VectorizeVector[] = [];
    const toDelete: string[] = [];

    for (const msg of batch.messages) {
      const { productId, type } = msg.body;
      try {
        if (type === "ProductDeleted") {
          toDelete.push(productId);
          msg.ack();
          continue;
        }

        const row = await env.DB.prepare(
          "SELECT id, name, description, category, price_cents, active FROM products WHERE id = ?1"
        )
          .bind(productId)
          .first<ProductRow>();

        if (!row) {
          // Product was deleted between event and processing
          toDelete.push(productId);
          msg.ack();
          continue;
        }

        const vector = await embedProduct(env, row);

        toUpsert.push({
          id: row.id,
          values: vector,
          metadata: {
            name: row.name,
            category: row.category,
            price_cents: row.price_cents,
            active: row.active === 1,
          },
        });

        msg.ack();
      } catch (err) {
        console.error(`Projection failed for ${productId}:`, err);
        msg.retry({ delaySeconds: 60 });
      }
    }

    // Batch Vectorize operations
    if (toUpsert.length > 0) {
      await env.PRODUCT_INDEX.upsert(toUpsert);
    }
    if (toDelete.length > 0) {
      await env.PRODUCT_INDEX.deleteByIds(toDelete);
    }
  },
};
```

## Query Worker: Hybrid Semantic + Metadata Search

```typescript
// src/query-worker.ts
interface Env {
  DB: D1Database;
  AI: Ai;
  PRODUCT_INDEX: VectorizeIndex;
}

interface SearchRequest {
  query: string;
  category?: string;
  maxPrice?: number;
  minPrice?: number;
  topK?: number;
}

interface SearchResult {
  id: string;
  name: string;
  description: string;
  category: string;
  priceCents: number;
  score: number;
}

async function semanticSearch(
  env: Env,
  req: SearchRequest
): Promise<SearchResult[]> {
  const topK = req.topK ?? 10;

  // 1. Embed the query
  const embedResult = await env.AI.run(
    "@cf/baai/bge-small-en-v1.5",
    { text: [req.query] }
  ) as { data: number[][] };

  const queryVector = embedResult.data[0];

  // 2. Build Vectorize metadata filter
  const filter: VectorizeVectorMetadataFilter = { active: { $eq: true } };
  if (req.category) {
    (filter as any).category = { $eq: req.category };
  }

  // 3. ANN search
  const vectorResults = await env.PRODUCT_INDEX.query(queryVector, {
    topK: topK * 2, // over-fetch to allow metadata post-filtering
    filter,
    returnMetadata: "indexed",
  });

  if (vectorResults.matches.length === 0) return [];

  // 4. Price filter (Vectorize metadata filter only supports equality natively;
  //    range filters require post-processing or D1 join)
  const candidateIds = vectorResults.matches
    .map((m) => ({ id: m.id, score: m.score }))
    .filter((m) => {
      const meta = vectorResults.matches.find((v) => v.id === m.id)?.metadata as any;
      if (req.maxPrice && meta?.price_cents > req.maxPrice * 100) return false;
      if (req.minPrice && meta?.price_cents < req.minPrice * 100) return false;
      return true;
    })
    .slice(0, topK);

  if (candidateIds.length === 0) return [];

  // 5. Hydrate from D1 (source of truth for display data)
  const placeholders = candidateIds.map((_, i) => `?${i + 1}`).join(", ");
  const rows = await env.DB.prepare(
    `SELECT id, name, description, category, price_cents
     FROM products
     WHERE id IN (${placeholders}) AND active = 1`
  )
    .bind(...candidateIds.map((c) => c.id))
    .all<{ id: string; name: string; description: string; category: string; price_cents: number }>();

  // 6. Merge scores and return ranked results
  const scoreMap = new Map(candidateIds.map((c) => [c.id, c.score]));
  return (rows.results ?? [])
    .map((row) => ({
      id: row.id,
      name: row.name,
      description: row.description,
      category: row.category,
      priceCents: row.price_cents,
      score: scoreMap.get(row.id) ?? 0,
    }))
    .sort((a, b) => b.score - a.score);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/search") {
      return new Response("Not Found", { status: 404 });
    }

    const body = (await request.json()) as SearchRequest;
    if (!body.query || body.query.trim().length === 0) {
      return new Response(JSON.stringify({ error: "query is required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const results = await semanticSearch(env, body);
    return Response.json({ results, total: results.length });
  },
};
```

## wrangler.toml

```toml
name = "product-search"
main = "src/query-worker.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[vectorize]]
binding = "PRODUCT_INDEX"
index_name = "products-semantic"

[[d1_databases]]
binding = "DB"
database_name = "products-db"
database_id = "YOUR_D1_ID"
```

Create the Vectorize index (1536 dims for bge-small-en-v1.5 = 384 dims):

```bash
wrangler vectorize create products-semantic \
  --dimensions=384 \
  --metric=cosine
```

## Index Freshness and Consistency

Vectorize updates are eventually consistent with the D1 write model. Clients must not assume search results reflect writes made within the last few seconds. For UX: show a "recently added" badge using D1's `updated_at` when the product was written within the last minute, regardless of whether it appears in Vectorize results yet.

## Anti-patterns

- **Querying Vectorize without a D1 hydration step** — Vectorize metadata storage is limited and may lag D1 mutations; always hydrate display data from D1.
- **Storing embeddings in D1 BLOB columns** — 384-float vectors are ~1.5 KB each; storing thousands in D1 degrades query performance and wastes D1 storage quota.
- **Re-embedding on every query** — embedding the query string adds ~50 ms; cache the embedding for identical queries in KV with a short TTL (30 s).
- **Using different embedding models for indexing and querying** — vectors must be from the same model and tokenizer; a model change requires full re-indexing.
- **Not handling projection lag in the UI** — a product just created will not appear in semantic search for several seconds; provide a fallback exact-match path via D1 for immediately-after-write scenarios.

## Gotchas

- `VectorizeIndex.query()` `topK` is capped at 20 by default on some plans; check your limit before setting `topK` above 20.
- Vectorize `filter` only supports indexed metadata fields declared at index creation time; add fields with `wrangler vectorize create --metadata-index-property`.
- `@cf/baai/bge-small-en-v1.5` produces 384-dimensional vectors, not 1536; dimension mismatch at index creation causes all upserts to fail silently.
- Vectorize `deleteByIds` accepts up to 100 IDs per call; for bulk deletions, batch in groups of 100.
- Cosine similarity scores from Vectorize are in [0, 1] where 1 is identical; scores below ~0.7 for this model are usually noise and should be filtered out.

## Verification

1. Insert a product via the write API; confirm the projection Worker logs an upsert to Vectorize within ~5 s.
2. POST to `/search` with `{"query": "comfortable running shoes"}` and verify relevant products appear with scores > 0.75.
3. Update a product description; wait for projection; re-run the same query and confirm the updated description influences ranking.
4. Delete a product; confirm it no longer appears in search results after the next projection cycle.
5. Benchmark: run 50 concurrent search requests and confirm P99 < 200 ms (embedding + Vectorize + D1 hydration).

## Related

- `cqrs-cloudflare-workers-d1.md`
- `read-model-projection-workers-kv-cqrs.md`
- `event-driven-architecture-overview.md`
- `domain-event-ai-enrichment-pipeline-workers.md`
- `event-sourcing-projections-snapshots.md`

## Sources

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/workers-ai/models/text-embeddings/
- https://developers.cloudflare.com/d1/
