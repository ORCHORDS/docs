# Workers AI Embeddings and Semantic Search with Vectorize

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Keyword search over a D1 product catalogue misses semantically related results — a search for "running footwear" finds nothing when products are described as "athletic sneakers". Generating embeddings with Workers AI and storing them in a Vectorize index enables similarity search that understands meaning, and merging those scores with D1 full-text search results produces a hybrid ranking that is both semantically aware and keyword-precise.

---

## Context

`@cf/baai/bge-base-en-v1.5` produces 768-dimensional float32 embeddings for arbitrary English text directly in the Workers AI runtime. Vectorize is Cloudflare's vector database; it stores embedding vectors alongside metadata and exposes a `query()` method that returns the top-k nearest neighbours by cosine similarity. The recommended pattern is to embed each document at write time (upsert to Vectorize + store metadata in D1) and embed the query at read time, then merge Vectorize scores with D1 FTS scores using a weighted formula. All three — Workers AI, Vectorize, and D1 — are bound to the same Worker, so every hop is within the Cloudflare network.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "semantic-search-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[ai]
binding = "AI"

[[vectorize]]
binding = "VECTOR_INDEX"
index_name = "products"
# Create with: npx wrangler vectorize create products --dimensions=768 --metric=cosine

[[d1_databases]]
binding = "DB"
database_name = "catalogue"
database_id = "YOUR_D1_DATABASE_ID"
```

```sql
-- D1 product table with FTS virtual table
CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  category TEXT NOT NULL,
  price_usd REAL NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS products_fts
  USING fts5(id UNINDEXED, name, description, content='products', content_rowid='rowid');

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS products_ai AFTER INSERT ON products BEGIN
  INSERT INTO products_fts(rowid, id, name, description)
  VALUES (new.rowid, new.id, new.name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS products_ad AFTER DELETE ON products BEGIN
  INSERT INTO products_fts(products_fts, rowid, id, name, description)
  VALUES ('delete', old.rowid, old.id, old.name, old.description);
END;
```

## Section 2 — Ingestion: embed and upsert

```typescript
import { Ai } from "@cloudflare/workers-types";

export interface Env {
  AI: Ai;
  VECTOR_INDEX: VectorizeIndex;
  DB: D1Database;
}

const EMBED_MODEL = "@cf/baai/bge-base-en-v1.5";

/** Generate a single embedding vector for a text string */
async function embed(ai: Ai, text: string): Promise<number[]> {
  const result = (await ai.run(EMBED_MODEL, {
    text: [text],
  })) as { data: number[][] };

  if (!result.data?.[0]) throw new Error("Embedding returned no vectors");
  return result.data[0];
}

interface Product {
  id: string;
  name: string;
  description: string;
  category: string;
  price_usd: number;
}

/** Ingest a product: insert into D1 + embed + upsert to Vectorize */
async function ingestProduct(env: Env, product: Product): Promise<void> {
  // 1. Insert into D1 (FTS triggers fire automatically)
  await env.DB.prepare(
    `INSERT INTO products (id, name, description, category, price_usd)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET
       name = excluded.name,
       description = excluded.description,
       category = excluded.category,
       price_usd = excluded.price_usd`
  )
    .bind(
      product.id,
      product.name,
      product.description,
      product.category,
      product.price_usd
    )
    .run();

  // 2. Embed the concatenated name + description for richer semantics
  const textToEmbed = `${product.name}. ${product.description}`;
  const vector = await embed(env.AI, textToEmbed);

  // 3. Upsert to Vectorize — store lightweight metadata for result merging
  await env.VECTOR_INDEX.upsert([
    {
      id: product.id,
      values: vector,
      metadata: {
        name: product.name,
        category: product.category,
        price_usd: product.price_usd,
      },
    },
  ]);
}
```

## Section 3 — Query: hybrid semantic + FTS search

```typescript
interface SearchResult {
  id: string;
  name: string;
  category: string;
  price_usd: number;
  score: number; // merged hybrid score
  vectorScore: number;
  ftsRank: number;
}

/** Hybrid search: 70% vector similarity + 30% FTS BM25 */
async function hybridSearch(
  env: Env,
  query: string,
  topK = 10
): Promise<SearchResult[]> {
  // ── Step 1: embed the query ────────────────────────────────────────────
  const queryVector = await embed(env.AI, query);

  // ── Step 2: vector similarity search in Vectorize ─────────────────────
  const vectorResults = await env.VECTOR_INDEX.query(queryVector, {
    topK: topK * 2, // over-fetch so FTS can re-rank
    returnMetadata: true,
  });

  if (vectorResults.matches.length === 0) {
    return [];
  }

  const vectorMap = new Map<string, number>(); // id → cosine score
  for (const match of vectorResults.matches) {
    vectorMap.set(match.id, match.score ?? 0);
  }

  // ── Step 3: FTS BM25 search in D1 ─────────────────────────────────────
  const ids = [...vectorMap.keys()];
  const placeholders = ids.map(() => "?").join(",");

  // FTS bm25() returns negative values; negate for ascending relevance
  const ftsRows = await env.DB.prepare(
    `SELECT p.id, -bm25(products_fts) AS fts_rank
     FROM products_fts
     JOIN products p ON p.id = products_fts.id
     WHERE products_fts MATCH ?
       AND p.id IN (${placeholders})`
  )
    .bind(query, ...ids)
    .all<{ id: string; fts_rank: number }>();

  const ftsMap = new Map<string, number>();
  const maxFts = ftsRows.results.reduce((m, r) => Math.max(m, r.fts_rank), 1);
  for (const row of ftsRows.results) {
    ftsMap.set(row.id, row.fts_rank / maxFts); // normalise 0–1
  }

  // ── Step 4: merge scores, fetch full metadata from D1 ─────────────────
  const mergedIds = ids.slice(0, topK);
  const fetchPlaceholders = mergedIds.map(() => "?").join(",");
  const productRows = await env.DB.prepare(
    `SELECT id, name, category, price_usd FROM products WHERE id IN (${fetchPlaceholders})`
  )
    .bind(...mergedIds)
    .all<{ id: string; name: string; category: string; price_usd: number }>();

  const results: SearchResult[] = productRows.results.map((p) => {
    const vScore = vectorMap.get(p.id) ?? 0;
    const ftsRank = ftsMap.get(p.id) ?? 0;
    const hybridScore = 0.7 * vScore + 0.3 * ftsRank;

    return {
      id: p.id,
      name: p.name,
      category: p.category,
      price_usd: p.price_usd,
      score: hybridScore,
      vectorScore: vScore,
      ftsRank,
    };
  });

  return results.sort((a, b) => b.score - a.score);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/ingest") {
      const product = (await request.json()) as Product;
      await ingestProduct(env, product);
      return Response.json({ ok: true, id: product.id });
    }

    if (request.method === "GET" && url.pathname === "/search") {
      const query = url.searchParams.get("q") ?? "";
      if (!query.trim()) {
        return Response.json({ error: "Missing q param" }, { status: 400 });
      }
      const topK = Math.min(parseInt(url.searchParams.get("k") ?? "10"), 50);
      const results = await hybridSearch(env, query, topK);
      return Response.json({ query, results });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Embedding only the product name** — Short names produce sparse vectors; always concatenate name + description to capture full semantic meaning.
- **Querying Vectorize without a D1 fallback** — Vectorize may not yet have a vector for recently ingested products (eventual consistency); fall back to pure FTS for those IDs.
- **Using raw cosine scores without normalisation** — Cosine scores from Vectorize are already 0–1, but FTS BM25 values are negative and unbounded; normalise FTS scores before merging.
- **Storing full product data in Vectorize metadata** — Vectorize metadata is charged per byte and is not relational; store only the fields needed for merging and retrieve full records from D1.

---

## Gotchas

- Vectorize `query()` returns at most `topK` matches; if the catalogue is large you may need to increase `topK` on the vector step and trim after merging.
- FTS5 `MATCH` syntax differs from standard SQL `LIKE`; special characters in the query string (parentheses, quotes) must be escaped before binding.
- `@cf/baai/bge-base-en-v1.5` normalises vectors internally; no need to normalise before upserting to a cosine-metric Vectorize index.
- Vectorize upserts are eventually consistent — an upsert may not be immediately queryable; for near-real-time use cases add a short delay or use a write-through D1 flag to exclude unindexed items.

---

## Verification

```bash
# Create Vectorize index
npx wrangler vectorize create products --dimensions=768 --metric=cosine

# Run migrations
npx wrangler d1 execute catalogue --remote --file=./schema.sql

# Start dev
npx wrangler dev --remote

# Ingest a product
curl -X POST http://localhost:8787/ingest \
  -H 'Content-Type: application/json' \
  -d '{"id":"prod-1","name":"Trail Running Shoes","description":"Lightweight athletic sneakers for outdoor running","category":"footwear","price_usd":89.99}'

# Search semantically
curl 'http://localhost:8787/search?q=running+footwear&k=5'
```

---

## Related

- `workers-ai-tool-calling-d1-queries.md`
- `workers-ai-multimodal-vision-r2.md`

---

## Sources

- Cloudflare Vectorize documentation — https://developers.cloudflare.com/vectorize/
- BGE embedding model — https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- D1 FTS5 documentation — https://developers.cloudflare.com/d1/
