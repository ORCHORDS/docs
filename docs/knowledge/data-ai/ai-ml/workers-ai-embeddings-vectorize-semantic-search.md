# Workers AI Embeddings + Vectorize Semantic Search

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to build a semantic search pipeline entirely on Cloudflare's stack: generate text embeddings with Workers AI, store and query them in a Vectorize index for nearest-neighbour retrieval, and re-rank the results using a BM25 score from a D1 FTS5 full-text index to produce a hybrid relevance score.

---

## Context

`@cf/baai/bge-base-en-v1.5` produces 768-dimensional L2-normalised embeddings that work well for English semantic similarity. Vectorize stores these vectors and returns approximate nearest neighbours via HNSW. Because pure vector similarity degrades on keyword-heavy queries, combining the Vectorize cosine score with a BM25 term-frequency score from D1 FTS5 yields measurably better precision. The fusion formula is a linear combination: `hybrid_score = α * cosine + (1 - α) * bm25_norm` where `α` (default 0.7) can be tuned per use-case. Documents are stored in D1 with their embeddings upserted into Vectorize; both writes happen in a single Worker request at index time.

---

## Section 1 — wrangler.toml / Config

```toml
name = "semantic-search-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[vectorize]]
binding = "VECTOR_INDEX"
index_name = "documents"

[[d1_databases]]
binding = "DB"
database_name = "documents"
database_id = "<your-d1-database-id>"

[vars]
TOP_K = "20"       # over-fetch from Vectorize before re-ranking
FINAL_TOP_K = "10" # results returned to client
ALPHA = "0.7"      # weight for vector score vs BM25
```

## Section 2 — Worker implementation

```typescript
interface Env {
  AI: Ai;
  VECTOR_INDEX: VectorizeIndex;
  DB: D1Database;
  TOP_K: string;
  FINAL_TOP_K: string;
  ALPHA: string;
}

interface Document {
  id: string;
  title: string;
  body: string;
  source_url?: string;
  created_at: string;
}

interface EmbeddingResult {
  data: number[][];
}

interface VectorizeMatch {
  id: string;
  score: number;
  metadata?: Record<string, string>;
}

// ─── Embedding helper ──────────────────────────────────────────────────────────

async function embed(ai: Ai, texts: string[]): Promise<number[][]> {
  const result = (await ai.run('@cf/baai/bge-base-en-v1.5', {
    text: texts,
  })) as EmbeddingResult;
  return result.data;
}

// ─── D1 schema helpers ─────────────────────────────────────────────────────────

async function insertDocument(db: D1Database, doc: Document): Promise<void> {
  await db
    .prepare(
      `INSERT OR REPLACE INTO documents (id, title, body, source_url, created_at)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(doc.id, doc.title, doc.body, doc.source_url ?? null, doc.created_at)
    .run();
}

async function fetchDocumentsByIds(
  db: D1Database,
  ids: string[]
): Promise<Document[]> {
  if (ids.length === 0) return [];
  const placeholders = ids.map(() => '?').join(',');
  const { results } = await db
    .prepare(`SELECT * FROM documents WHERE id IN (${placeholders})`)
    .bind(...ids)
    .all<Document>();
  return results;
}

// ─── BM25 from D1 FTS5 ────────────────────────────────────────────────────────

async function bm25Scores(
  db: D1Database,
  query: string,
  ids: string[]
): Promise<Map<string, number>> {
  if (ids.length === 0) return new Map();
  const placeholders = ids.map(() => '?').join(',');
  // FTS5 `rank` column returns a negative BM25 score; negate it for positive scores.
  const { results } = await db
    .prepare(
      `SELECT d.id, -fts.rank AS bm25
       FROM documents_fts fts
       JOIN documents d ON d.id = fts.id
       WHERE documents_fts MATCH ?
         AND d.id IN (${placeholders})
       ORDER BY rank`
    )
    .bind(query, ...ids)
    .all<{ id: string; bm25: number }>();

  const scores = new Map<string, number>();
  for (const row of results) {
    scores.set(row.id, row.bm25);
  }
  return scores;
}

// ─── Hybrid re-ranking ────────────────────────────────────────────────────────

function hybridRerank(
  vectorMatches: VectorizeMatch[],
  bm25Map: Map<string, number>,
  alpha: number,
  finalTopK: number
): (VectorizeMatch & { hybrid_score: number })[] {
  // Normalise BM25 scores to [0, 1]
  const bm25Values = [...bm25Map.values()];
  const maxBm25 = bm25Values.length > 0 ? Math.max(...bm25Values) : 1;

  const ranked = vectorMatches.map((m) => {
    const bm25Raw = bm25Map.get(m.id) ?? 0;
    const bm25Norm = maxBm25 > 0 ? bm25Raw / maxBm25 : 0;
    const hybrid_score = alpha * m.score + (1 - alpha) * bm25Norm;
    return { ...m, hybrid_score };
  });

  ranked.sort((a, b) => b.hybrid_score - a.hybrid_score);
  return ranked.slice(0, finalTopK);
}

// ─── Route handlers ───────────────────────────────────────────────────────────

async function handleIndex(request: Request, env: Env): Promise<Response> {
  const doc = await request.json<Omit<Document, 'id' | 'created_at'>>();
  if (!doc.title || !doc.body) {
    return new Response(
      JSON.stringify({ error: '`title` and `body` are required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const id = crypto.randomUUID();
  const created_at = new Date().toISOString();
  const fullDoc: Document = { ...doc, id, created_at };

  // Generate embedding for title + body concatenation
  const textToEmbed = `${doc.title}\n\n${doc.body}`;
  const [[embedding]] = await embed(env.AI, [textToEmbed]);

  // Upsert into Vectorize
  await env.VECTOR_INDEX.upsert([
    {
      id,
      values: embedding,
      metadata: { title: doc.title, created_at },
    },
  ]);

  // Insert into D1 (triggers FTS5 update via SQL trigger)
  await insertDocument(env.DB, fullDoc);

  return Response.json({ id }, { status: 201 });
}

async function handleSearch(request: Request, env: Env): Promise<Response> {
  const { query, alpha } = await request.json<{ query: string; alpha?: number }>();
  if (!query?.trim()) {
    return new Response(
      JSON.stringify({ error: '`query` is required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const topK = parseInt(env.TOP_K, 10);
  const finalTopK = parseInt(env.FINAL_TOP_K, 10);
  const alphaValue = alpha ?? parseFloat(env.ALPHA);

  // 1. Generate query embedding
  const [[queryEmbedding]] = await embed(env.AI, [query.trim()]);

  // 2. Vectorize nearest-neighbour search
  const { matches } = await env.VECTOR_INDEX.query(queryEmbedding, {
    topK,
    returnMetadata: true,
  });

  if (matches.length === 0) {
    return Response.json({ results: [] });
  }

  const matchIds = matches.map((m: VectorizeMatch) => m.id);

  // 3. BM25 scores from D1 FTS5
  const bm25Map = await bm25Scores(env.DB, query.trim(), matchIds);

  // 4. Hybrid re-rank
  const reranked = hybridRerank(matches as VectorizeMatch[], bm25Map, alphaValue, finalTopK);

  // 5. Fetch full document metadata from D1
  const docs = await fetchDocumentsByIds(env.DB, reranked.map((r) => r.id));
  const docMap = new Map(docs.map((d) => [d.id, d]));

  const results = reranked.map((r) => ({
    ...docMap.get(r.id),
    vector_score: r.score,
    hybrid_score: Math.round(r.hybrid_score * 10000) / 10000,
  }));

  return Response.json({ results, query, alpha: alphaValue });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === 'POST' && url.pathname === '/index') {
      return handleIndex(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/search') {
      return handleSearch(request, env);
    }
    return new Response('Not found', { status: 404 });
  },
};
```

## Section 3 — Vectorize index creation and D1 schema

```typescript
// ── 1. Create Vectorize index (run once in CLI) ──
// npx wrangler vectorize create documents --dimensions=768 --metric=cosine

// ── 2. D1 schema (save as schema.sql) ──
// CREATE TABLE IF NOT EXISTS documents (
//   id TEXT PRIMARY KEY,
//   title TEXT NOT NULL,
//   body TEXT NOT NULL,
//   source_url TEXT,
//   created_at TEXT NOT NULL
// );
//
// CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
//   USING fts5(id UNINDEXED, title, body, content='documents', content_rowid='rowid');
//
// CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
//   INSERT INTO documents_fts (rowid, id, title, body)
//   VALUES (new.rowid, new.id, new.title, new.body);
// END;
//
// CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
//   INSERT INTO documents_fts (documents_fts, rowid, id, title, body)
//   VALUES ('delete', old.rowid, old.id, old.title, old.body);
// END;

// ── 3. Batch index helper ──
async function batchIndex(
  ai: Ai,
  vectorIndex: VectorizeIndex,
  db: D1Database,
  docs: Omit<Document, 'id' | 'created_at'>[]
): Promise<string[]> {
  const ids: string[] = [];
  // Embed all docs in one call (max 100 texts per request)
  const texts = docs.map((d) => `${d.title}\n\n${d.body}`);
  const embeddings = await embed(ai, texts);

  const vectors = embeddings.map((values, i) => ({
    id: crypto.randomUUID(),
    values,
    metadata: { title: docs[i].title },
  }));

  await vectorIndex.upsert(vectors);

  const stmt = db.prepare(
    `INSERT OR REPLACE INTO documents (id, title, body, source_url, created_at)
     VALUES (?, ?, ?, ?, ?)`
  );
  const batch = vectors.map((v, i) =>
    stmt.bind(v.id, docs[i].title, docs[i].body, docs[i].source_url ?? null, new Date().toISOString())
  );
  await db.batch(batch);

  ids.push(...vectors.map((v) => v.id));
  return ids;
}

export { batchIndex };
```

---

## Anti-patterns

- **Embedding only the title** — Short titles lose semantic signal. Concatenate title and body (with a separator) for richer embeddings.
- **Setting `topK` equal to the final result count** — Vectorize ANN may miss relevant documents. Over-fetch by 2–3× then re-rank to compensate.
- **Skipping L2 normalisation** — `bge-base-en-v1.5` returns L2-normalised vectors; if you post-process them (e.g., slice dimensions), re-normalise before upserting.
- **Running BM25 on the full corpus instead of the vector shortlist** — D1 FTS5 over millions of rows will be slow. Always pass the Vectorize match IDs as a filter.

---

## Gotchas

- `env.VECTOR_INDEX.query()` returns `score` in [0, 1] for cosine metric (1 = identical); do not confuse with L2 distance.
- Vectorize `upsert` is eventually consistent; new vectors may not be queryable for a few seconds after write.
- D1 FTS5 `rank` is a negative float (more negative = worse match); negate it before normalising.
- The `@cf/baai/bge-base-en-v1.5` model produces a 768-dim vector; ensure the Vectorize index was created with `--dimensions=768`.
- `db.batch()` is limited to 100 statements per call; split large batches accordingly.

---

## Verification

```bash
# Provision infrastructure
npx wrangler vectorize create documents --dimensions=768 --metric=cosine
npx wrangler d1 create documents
npx wrangler d1 execute documents --file=schema.sql
npx wrangler deploy

# Index a document
curl -X POST https://semantic-search-worker.<your-subdomain>.workers.dev/index \
  -H 'Content-Type: application/json' \
  -d '{"title":"Cloudflare Workers AI","body":"Run AI models at the edge with zero infrastructure."}'

# Search
curl -X POST https://semantic-search-worker.<your-subdomain>.workers.dev/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"edge AI inference","alpha":0.7}' | jq '.results[].title'
```

---

## Related

- `workers-ai-text-classification-moderation.md`
- `workers-ai-whisper-speech-to-text.md`
- `workers-ai-translation-multilingual.md`

---

## Sources

- Workers AI BGE Embeddings — https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- Vectorize Index API — https://developers.cloudflare.com/vectorize/reference/client-api/
- D1 FTS5 — https://developers.cloudflare.com/d1/reference/full-text-search/
- Hybrid Search (BM25 + Vector) — https://www.elastic.co/blog/improving-information-retrieval-elastic-stack-hybrid
