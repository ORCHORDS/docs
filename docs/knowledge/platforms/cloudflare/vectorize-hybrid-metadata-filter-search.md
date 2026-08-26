# Vectorize: Hybrid Metadata Filter + Vector Search

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A RAG pipeline using Cloudflare Vectorize returns semantically similar results from the wrong tenant or document category because pure KNN search ignores access scope and content taxonomy.

## Context
Vectorize supports pre-filter metadata constraints on `query()` calls, allowing you to combine approximate nearest-neighbor (ANN) vector similarity with strict equality or range filters on indexed metadata fields. This enables multi-tenant retrieval where each tenant's embeddings are stored in a single index but never mixed in query results, as well as category-scoped search without maintaining separate per-category indexes. Metadata filtering happens before the ANN scan, so it reduces the candidate set and can improve both speed and precision.

## Index Creation with Metadata Indexes

Declare metadata indexes at creation time; they cannot be added after the index is created without rebuilding it.

```typescript
// scripts/create-index.ts
async function createVectorizeIndex(
  accountId: string,
  apiToken: string
): Promise<void> {
  const body = {
    name: "docs-index",
    config: {
      dimensions: 1536,          // text-embedding-3-small
      metric: "cosine",
    },
    metadata_indexes: {
      indexed: [
        { property_name: "tenantId", index_type: "string" },
        { property_name: "category", index_type: "string" },
        { property_name: "publishedAt", index_type: "number" },
        { property_name: "language", index_type: "string" },
      ],
    },
  };

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/vectorize/v2/indexes`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiToken}`,
      },
      body: JSON.stringify(body),
    }
  );

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Failed to create index: ${err}`);
  }
  console.log("Index created:", await resp.json());
}
```

## Inserting Vectors with Tenant and Category Metadata

Always set metadata at upsert time. Unindexed fields are stored but cannot be used in filters.

```typescript
// lib/ingest.ts
export interface Env {
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

interface Document {
  id: string;
  tenantId: string;
  category: string;
  language: string;
  publishedAt: number; // Unix timestamp
  content: string;
}

export async function ingestDocuments(
  env: Env,
  docs: Document[]
): Promise<void> {
  // Generate embeddings in batches of 100 (Workers AI limit)
  const BATCH = 100;
  for (let i = 0; i < docs.length; i += BATCH) {
    const slice = docs.slice(i, i + BATCH);

    const embeddings = await env.AI.run("@cf/baai/bge-large-en-v1.5", {
      text: slice.map((d) => d.content),
    });

    const vectors: VectorizeVector[] = slice.map((doc, idx) => ({
      id: doc.id,
      values: (embeddings as { data: number[][] }).data[idx],
      metadata: {
        tenantId: doc.tenantId,
        category: doc.category,
        language: doc.language,
        publishedAt: doc.publishedAt,
        // Non-indexed fields: stored but not filterable
        title: doc.content.slice(0, 80),
      },
    }));

    await env.VECTORIZE.upsert(vectors);
  }
}
```

## Querying with Compound Metadata Filters

Pass a `filter` object alongside the query vector to enforce hard constraints before KNN scoring.

```typescript
// lib/search.ts
export interface SearchOptions {
  tenantId: string;
  category?: string;
  language?: string;
  publishedAfter?: number;
  topK?: number;
}

export interface SearchResult {
  id: string;
  score: number;
  metadata: Record<string, string | number | boolean>;
}

export async function hybridSearch(
  env: Env,
  queryText: string,
  opts: SearchOptions
): Promise<SearchResult[]> {
  // Embed the query
  const embedding = await env.AI.run("@cf/baai/bge-large-en-v1.5", {
    text: [queryText],
  });
  const queryVector = (embedding as { data: number[][] }).data[0];

  // Build compound filter — tenantId is always required
  const filter: VectorizeVectorMetadataFilter = {
    $and: [
      { tenantId: { $eq: opts.tenantId } },
    ],
  };

  if (opts.category) {
    (filter.$and as VectorizeVectorMetadataFilter[]).push({
      category: { $eq: opts.category },
    });
  }

  if (opts.language) {
    (filter.$and as VectorizeVectorMetadataFilter[]).push({
      language: { $eq: opts.language },
    });
  }

  if (opts.publishedAfter !== undefined) {
    (filter.$and as VectorizeVectorMetadataFilter[]).push({
      publishedAt: { $gt: opts.publishedAfter },
    });
  }

  const results = await env.VECTORIZE.query(queryVector, {
    topK: opts.topK ?? 10,
    filter,
    returnMetadata: "all",
    returnValues: false,
  });

  return results.matches.map((m) => ({
    id: m.id,
    score: m.score,
    metadata: m.metadata ?? {},
  }));
}
```

## Integrating with Workers AI for Full RAG

Chain the filtered search into a generative response using the retrieved document IDs to fetch full text from D1.

```typescript
// worker.ts
export interface Env {
  VECTORIZE: VectorizeIndex;
  AI: Ai;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { query, tenantId, category } = await request.json<{
      query: string;
      tenantId: string;
      category?: string;
    }>();

    // 1. Hybrid vector + metadata search
    const matches = await hybridSearch(env, query, { tenantId, category, topK: 5 });
    if (matches.length === 0) {
      return Response.json({ answer: "No relevant documents found." });
    }

    // 2. Fetch full document content from D1 using matched IDs
    const placeholders = matches.map(() => "?").join(", ");
    const { results: docs } = await env.DB.prepare(
      `SELECT id, content FROM documents WHERE id IN (${placeholders}) AND tenant_id = ?`
    )
      .bind(...matches.map((m) => m.id), tenantId)
      .all<{ id: string; content: string }>();

    const context = docs.map((d) => d.content).join("\n\n---\n\n");

    // 3. Generate answer
    const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [
        {
          role: "system",
          content: "Answer based only on the provided context. Be concise.",
        },
        {
          role: "user",
          content: `Context:\n${context}\n\nQuestion: ${query}`,
        },
      ],
    });

    return Response.json({
      answer: (response as { response: string }).response,
      sources: matches.map((m) => ({ id: m.id, score: m.score })),
    });
  },
};

// Re-export helpers (in a real project these live in separate modules)
async function hybridSearch(env: Env, queryText: string, opts: SearchOptions): Promise<SearchResult[]> {
  const embedding = await env.AI.run("@cf/baai/bge-large-en-v1.5", { text: [queryText] });
  const queryVector = (embedding as { data: number[][] }).data[0];

  const filter: VectorizeVectorMetadataFilter = {
    $and: [{ tenantId: { $eq: opts.tenantId } }],
  };
  if (opts.category) {
    (filter.$and as VectorizeVectorMetadataFilter[]).push({ category: { $eq: opts.category } });
  }

  const results = await env.VECTORIZE.query(queryVector, {
    topK: opts.topK ?? 10,
    filter,
    returnMetadata: "all",
    returnValues: false,
  });

  return results.matches.map((m) => ({ id: m.id, score: m.score, metadata: m.metadata ?? {} }));
}

interface SearchOptions { tenantId: string; category?: string; topK?: number; }
interface SearchResult { id: string; score: number; metadata: Record<string, string | number | boolean>; }
```

## Anti-patterns
- Using a separate Vectorize index per tenant — exceeds index quotas quickly and multiplies maintenance overhead; use metadata filters instead
- Filtering on non-indexed metadata fields — unindexed fields are ignored silently; the query runs as if no filter was set
- Relying solely on cosine similarity for access control — always enforce `tenantId` in the metadata filter; similarity scores alone cannot isolate tenants
- Passing `returnValues: true` when you only need IDs and scores — returning full 1536-float vectors multiplies response size

## Gotchas
- Metadata indexes must be defined at index creation; you cannot add them later without re-creating the index and re-upserting all vectors
- Vectorize string metadata comparisons are case-sensitive: `"Tech"` and `"tech"` are different values
- The `$and` filter operator requires an array of filter objects; wrapping a single condition in `$and` is valid but unnecessary
- `publishedAt` must be stored as a JavaScript `number` (not string ISO date) for `$gt` / `$lt` range filters to work correctly
- `topK` is applied after metadata filtering, so if the filtered candidate set is smaller than `topK`, you receive fewer results without error

## Verification
1. Upsert 1000 vectors with two different `tenantId` values
2. Query with `tenantId: "tenant-A"` and confirm all returned matches have `metadata.tenantId === "tenant-A"`
3. Add a `category` filter and confirm results exclude documents from other categories
4. Query with `publishedAfter: <timestamp>` and verify all `metadata.publishedAt` values exceed the threshold
5. Attempt to filter on a field not in `metadata_indexes.indexed` and confirm the filter has no effect (results are not scoped)

## Related
- `vectorize-best-practices.md`
- `vectorize-2026.md`
- `workers-ai-edge-inference.md`
- `ai-search-2026.md`
- `d1-best-practices.md`

## Sources
- https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- https://developers.cloudflare.com/vectorize/get-started/
- https://developers.cloudflare.com/workers-ai/models/bge-large-en-v1.5/
