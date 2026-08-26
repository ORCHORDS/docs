# Vectorize Hybrid BM25 + Dense Retrieval in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Pure dense retrieval misses exact keyword matches ("CVE-2024-1234", product SKUs, proper nouns). Pure BM25 misses semantic intent ("fix login crash" doesn't match "authentication failure bug"). Hybrid retrieval fuses both signals and consistently outperforms either alone. You need this in a Cloudflare Worker with no external search engine.

## Context

Vectorize handles dense ANN search natively. BM25 must be approximated at the edge: D1 stores a pre-tokenised inverted index, and a sparse BM25 scorer runs in Worker CPU time. Scores from both legs are fused with Reciprocal Rank Fusion (RRF) or linear interpolation. The result is a ranked list of document IDs that a final D1 fetch turns into full results. Everything runs serverless, no Redis, no Elasticsearch.

---

## 1. Architecture

```
Query string
      │
      ├──► Workers AI embed ──► Vectorize.query(topK=100) ──► dense_hits[]
      │
      └──► BM25 scorer (D1 inverted index) ──────────────────► sparse_hits[]
                    │
                    ▼
             RRF fusion: merged_hits[] (re-ranked)
                    │
                    ▼
             D1 fetch full documents for top-K merged IDs
```

---

## 2. Wrangler Bindings

```toml
[ai]
binding = "AI"

[[vectorize]]
binding = "DOCS_IDX"
index_name = "documents-hybrid"

[[d1_databases]]
binding = "DB"
database_name = "search-db"
database_id = "YOUR_D1_ID"
```

---

## 3. D1 Schema for Inverted Index

```sql
-- Documents table
CREATE TABLE IF NOT EXISTS documents (
  id         TEXT PRIMARY KEY,
  title      TEXT,
  body       TEXT,
  url        TEXT,
  indexed_at INTEGER
);

-- Inverted index: one row per (term, doc_id) pair
CREATE TABLE IF NOT EXISTS bm25_index (
  term        TEXT NOT NULL,
  doc_id      TEXT NOT NULL,
  tf          REAL NOT NULL,   -- term frequency in this doc
  PRIMARY KEY (term, doc_id)
);
CREATE INDEX IF NOT EXISTS idx_term ON bm25_index(term);

-- Per-doc statistics needed for BM25
CREATE TABLE IF NOT EXISTS doc_stats (
  doc_id    TEXT PRIMARY KEY,
  dl        INTEGER NOT NULL    -- document length (token count)
);

-- Corpus-level statistics
CREATE TABLE IF NOT EXISTS corpus_stats (
  key   TEXT PRIMARY KEY,
  value REAL NOT NULL
);
-- Rows: { key: 'N', value: <doc count> }, { key: 'avgdl', value: <avg doc len> }
```

---

## 4. Indexing Pipeline

```typescript
interface Env {
  AI: Ai;
  DOCS_IDX: VectorizeIndex;
  DB: D1Database;
}

function tokenise(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 1);
}

export async function indexDocument(
  doc: { id: string; title: string; body: string; url: string },
  env: Env
): Promise<void> {
  const text = `${doc.title} ${doc.body}`;
  const tokens = tokenise(text);

  // --- Dense index ---
  const embedResult = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [`${doc.title}\n${doc.body.slice(0, 1500)}`],
  });
  const vector = (embedResult as { data: number[][] }).data[0];

  await env.DOCS_IDX.upsert([{ id: doc.id, values: vector, metadata: { title: doc.title } }]);

  // --- Sparse index ---
  const tfMap = new Map<string, number>();
  for (const t of tokens) tfMap.set(t, (tfMap.get(t) ?? 0) + 1);

  const statements: D1PreparedStatement[] = [];

  // Upsert document metadata
  statements.push(
    env.DB.prepare(
      `INSERT INTO documents (id, title, body, url, indexed_at) VALUES (?,?,?,?,?)
       ON CONFLICT(id) DO UPDATE SET title=excluded.title, body=excluded.body, indexed_at=excluded.indexed_at`
    ).bind(doc.id, doc.title, doc.body, doc.url, Date.now())
  );

  // Upsert doc length
  statements.push(
    env.DB.prepare(
      `INSERT INTO doc_stats (doc_id, dl) VALUES (?,?)
       ON CONFLICT(doc_id) DO UPDATE SET dl=excluded.dl`
    ).bind(doc.id, tokens.length)
  );

  // Upsert term frequencies
  for (const [term, tf] of tfMap) {
    statements.push(
      env.DB.prepare(
        `INSERT INTO bm25_index (term, doc_id, tf) VALUES (?,?,?)
         ON CONFLICT(term, doc_id) DO UPDATE SET tf=excluded.tf`
      ).bind(term, doc.id, tf / tokens.length) // normalised TF
    );
  }

  // D1 batch (max 100 statements per batch)
  for (let i = 0; i < statements.length; i += 100) {
    await env.DB.batch(statements.slice(i, i + 100));
  }
}
```

---

## 5. BM25 Scorer

```typescript
const BM25_K1 = 1.5;
const BM25_B = 0.75;

async function bm25Score(
  queryTokens: string[],
  topK: number,
  env: Env
): Promise<Array<{ id: string; score: number }>> {
  const statsRow = await env.DB.prepare(
    `SELECT key, value FROM corpus_stats WHERE key IN ('N','avgdl')`
  ).all<{ key: string; value: number }>();

  const stats = Object.fromEntries(statsRow.results.map((r) => [r.key, r.value]));
  const N = stats.N ?? 1;
  const avgdl = stats.avgdl ?? 100;

  const uniqueTerms = [...new Set(queryTokens)];

  // Fetch postings for all query terms in one batch
  const placeholders = uniqueTerms.map(() => "?").join(",");
  const postings = await env.DB.prepare(
    `SELECT b.term, b.doc_id, b.tf, s.dl
     FROM bm25_index b
     JOIN doc_stats s ON b.doc_id = s.doc_id
     WHERE b.term IN (${placeholders})`
  ).bind(...uniqueTerms).all<{ term: string; doc_id: string; tf: number; dl: number }>();

  // Count docs per term for IDF
  const dfMap = new Map<string, number>();
  for (const row of postings.results) {
    dfMap.set(row.term, (dfMap.get(row.term) ?? 0) + 1);
  }

  const scoreMap = new Map<string, number>();
  for (const row of postings.results) {
    const df = dfMap.get(row.term) ?? 1;
    const idf = Math.log((N - df + 0.5) / (df + 0.5) + 1);
    const normTF =
      (row.tf * (BM25_K1 + 1)) /
      (row.tf + BM25_K1 * (1 - BM25_B + BM25_B * (row.dl / avgdl)));
    scoreMap.set(row.doc_id, (scoreMap.get(row.doc_id) ?? 0) + idf * normTF);
  }

  return [...scoreMap.entries()]
    .map(([id, score]) => ({ id, score }))
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
}
```

---

## 6. RRF Fusion and Search Handler

```typescript
function rrfFuse(
  denseHits: Array<{ id: string }>,
  sparseHits: Array<{ id: string }>,
  k = 60,
  topK = 10
): string[] {
  const scores = new Map<string, number>();
  const add = (hits: Array<{ id: string }>) => {
    hits.forEach(({ id }, rank) => {
      scores.set(id, (scores.get(id) ?? 0) + 1 / (k + rank + 1));
    });
  };
  add(denseHits);
  add(sparseHits);
  return [...scores.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, topK)
    .map(([id]) => id);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { query, topK = 10 } = (await request.json()) as {
      query: string;
      topK?: number;
    };

    const queryTokens = tokenise(query);

    // Run dense and sparse retrieval in parallel
    const [embedResult, sparseHits] = await Promise.all([
      env.AI.run("@cf/baai/bge-base-en-v1.5", { text: [query] }),
      bm25Score(queryTokens, 100, env),
    ]);

    const vector = (embedResult as { data: number[][] }).data[0];
    const denseResult = await env.DOCS_IDX.query(vector, { topK: 100, returnMetadata: "none" });
    const denseHits = denseResult.matches.map((m) => ({ id: m.id }));

    const mergedIds = rrfFuse(denseHits, sparseHits, 60, topK);

    if (mergedIds.length === 0) return Response.json({ results: [] });

    const placeholders = mergedIds.map(() => "?").join(",");
    const docs = await env.DB.prepare(
      `SELECT id, title, url FROM documents WHERE id IN (${placeholders})`
    ).bind(...mergedIds).all<{ id: string; title: string; url: string }>();

    // Preserve RRF order
    const docMap = new Map(docs.results.map((d) => [d.id, d]));
    const results = mergedIds.map((id) => docMap.get(id)).filter(Boolean);

    return Response.json({ results });
  },
};
```

---

## Anti-patterns

- **Fetching all BM25 postings into Worker memory** — cap the postings query with `LIMIT 5000`; for very large corpora, materialise BM25 scores offline.
- **Using raw TF without length normalisation** — longer documents always win without `B` normalisation; always apply the BM25 length penalty.
- **Fusing scores directly (linear)** — score scales differ between cosine (0–1) and BM25 (0–∞); use RRF instead, which only needs rank positions.
- **Re-computing `avgdl` at query time** — this requires a full table scan; materialise it in `corpus_stats` and update incrementally at index time.

---

## Gotchas

- D1 has a 1 MB response size cap per query; large postings sets (common terms like "the") can hit this. Pre-filter stop words at index time.
- `bge-base-en-v1.5` produces 768-dim vectors (vs 384 for `bge-small`); Vectorize index must be created with `dimensions=768`. Mismatch causes silent 0-score returns.
- RRF's `k=60` is a hyperparameter from the original paper. Lower values (30) weight top-ranked results more heavily; tune on a held-out query set.
- Workers CPU time limit is 30 ms (50 ms on paid plan) per request on the default tier; BM25 with >20 query terms across a large index may need offloading to a Queue.

---

## Verification

```bash
# Search for an exact SKU that dense-only would miss
curl -X POST https://your-worker.example.com \
  -H "Content-Type: application/json" \
  -d '{"query":"SKU-98712 battery replacement","topK":5}'

# Expect the exact-SKU doc in position 1 or 2
```

A/B test: compare MRR (Mean Reciprocal Rank) of hybrid vs dense-only on a sample of queries with known relevant documents. Hybrid typically gains 5–15 MRR points on keyword-heavy queries.

---

## Related

- `rag-hybrid-search.md`
- `vectorize-approximate-nearest-neighbor-tuning.md`
- `vectorize-metadata-filtering-complex-predicates.md`
- `vectorize-pre-post-filter-ann-metadata.md`
- `embedding-batching.md`

---

## Sources

- BM25 paper (Robertson & Zaragoza, 2009): https://dl.acm.org/doi/10.1561/1500000019
- RRF (Cormack et al., 2009): https://dl.acm.org/doi/10.1145/1571941.1572114
- Cloudflare Vectorize: https://developers.cloudflare.com/vectorize/
- BGE embedding models: https://huggingface.co/BAAI/bge-base-en-v1.5
