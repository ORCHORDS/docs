# Workers AI Reranking Search Results

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Vectorize nearest-neighbor search returns approximate matches ranked by cosine similarity. Bi-encoder embeddings are fast but coarse — the top-10 candidates often include off-topic results that scored highly due to vocabulary overlap. A reranker model re-scores each (query, document) pair with a cross-encoder, dramatically improving ranking quality at the cost of one additional model call. This article covers `@cf/baai/bge-reranker-base`, combining Vectorize with reranking, D1 metadata enrichment, and latency budget management.

---

## Context

**Bi-encoder (Vectorize)**: Embeds query and documents independently; cosine similarity is a proxy for relevance. Fast O(1) ANN lookup. Loses nuance — "not good" and "good" have similar embeddings.

**Cross-encoder (reranker)**: Jointly encodes (query, document) pair and outputs a scalar relevance score. Much more accurate but O(n) — you must run it on every candidate. Therefore: fetch a large candidate set from Vectorize (e.g. top-50), rerank with the cross-encoder, return top-5 to the user.

`@cf/baai/bge-reranker-base` is a BAAI cross-encoder fine-tuned for retrieval tasks. Input: `{ query: string, contexts: { text: string }[] }`. Output: `{ response: { index: number, score: number }[] }` sorted by descending score.

---

## Solution

```typescript
// src/index.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AI:        Ai;
  VECTORIZE: VectorizeIndex;
  DB:        D1Database;
}

// ── Types ──────────────────────────────────────────────────────────────────

interface SearchDocument {
  id:      string;
  title:   string;
  body:    string;
  url?:    string;
  score?:  number; // cosine similarity from Vectorize
  rerank_score?: number;
}

interface VectorizeMatch {
  id:       string;
  score:    number;
  metadata?: Record<string, string | number | boolean>;
}

interface RerankerOutput {
  response: Array<{ index: number; score: number }>;
}

// ── Step 1: Embed the query ───────────────────────────────────────────────

async function embedQuery(
  query: string,
  env: Env
): Promise<number[]> {
  const result = await env.AI.run(
    '@cf/baai/bge-base-en-v1.5',
    { text: [query] }
  );
  // Returns { data: number[][] }
  const output = result as unknown as { data: number[][] };
  if (!output.data?.[0]) throw new Error('Embedding returned empty vector');
  return output.data[0];
}

// ── Step 2: Vectorize ANN search ──────────────────────────────────────────

async function vectorSearch(
  queryVector: number[],
  topK: number,
  env: Env
): Promise<VectorizeMatch[]> {
  const results = await env.VECTORIZE.query(queryVector, {
    topK,
    returnMetadata: 'all',
  });
  return (results.matches ?? []) as VectorizeMatch[];
}

// ── Step 3: D1 metadata enrichment ───────────────────────────────────────
// Vectorize stores minimal metadata inline. Full document text lives in D1.

async function enrichFromD1(
  ids: string[],
  env: Env
): Promise<Map<string, SearchDocument>> {
  if (ids.length === 0) return new Map();

  // D1 does not support array-bind natively; use a parameterised IN clause.
  const placeholders = ids.map(() => '?').join(', ');
  const { results } = await env.DB
    .prepare(
      `SELECT id, title, body, url FROM documents WHERE id IN (${placeholders})`
    )
    .bind(...ids)
    .all<SearchDocument>();

  const map = new Map<string, SearchDocument>();
  for (const doc of results) map.set(doc.id, doc);
  return map;
}

// ── Step 4: Reranking ─────────────────────────────────────────────────────

async function rerank(
  query: string,
  candidates: SearchDocument[],
  env: Env
): Promise<SearchDocument[]> {
  if (candidates.length === 0) return [];

  // bge-reranker-base input: query + list of context texts.
  const contexts = candidates.map((doc) => ({
    text: `${doc.title}\n${doc.body}`.slice(0, 512), // token budget guard
  }));

  const output = await env.AI.run(
    '@cf/baai/bge-reranker-base',
    { query, contexts }
  );

  const reranked = output as unknown as RerankerOutput;

  // The model returns scores indexed to the original candidates array.
  const scored = reranked.response.map(({ index, score }) => ({
    ...candidates[index],
    rerank_score: score,
  }));

  // Sort descending by rerank score.
  return scored.sort((a, b) => (b.rerank_score ?? 0) - (a.rerank_score ?? 0));
}

// ── Step 5: Latency budget management ────────────────────────────────────
// Track cumulative elapsed time and abort/truncate if we are running late.

class LatencyBudget {
  private start: number;
  private budgetMs: number;

  constructor(budgetMs: number) {
    this.start    = Date.now();
    this.budgetMs = budgetMs;
  }

  elapsed(): number  { return Date.now() - this.start; }
  remaining(): number { return this.budgetMs - this.elapsed(); }
  exceeded(): boolean { return this.elapsed() > this.budgetMs; }

  checkpoint(label: string): void {
    console.log(`[latency] ${label}: ${this.elapsed()} ms (${this.remaining()} ms remaining)`);
  }
}

// ── Full pipeline ─────────────────────────────────────────────────────────

interface SearchOptions {
  query:          string;
  vectorTopK?:    number; // candidates from Vectorize (default 50)
  finalTopK?:     number; // results after reranking (default 5)
  budgetMs?:      number; // total latency budget in ms (default 2000)
  minRerankScore?: number; // filter results below this threshold
}

interface SearchResponse {
  results:     SearchDocument[];
  latency_ms:  number;
  vector_candidates: number;
  rerank_applied: boolean;
  budget_exceeded: boolean;
}

async function search(
  options: SearchOptions,
  env: Env
): Promise<SearchResponse> {
  const {
    query,
    vectorTopK    = 50,
    finalTopK     = 5,
    budgetMs      = 2000,
    minRerankScore = 0,
  } = options;

  const budget = new LatencyBudget(budgetMs);

  // 1. Embed.
  const queryVector = await embedQuery(query, env);
  budget.checkpoint('embed');

  if (budget.exceeded()) {
    // Gracefully degrade: return empty results if embedding alone exceeded budget.
    return {
      results: [],
      latency_ms: budget.elapsed(),
      vector_candidates: 0,
      rerank_applied: false,
      budget_exceeded: true,
    };
  }

  // 2. Vector search.
  const matches = await vectorSearch(queryVector, vectorTopK, env);
  budget.checkpoint('vectorize');

  if (matches.length === 0) {
    return {
      results: [],
      latency_ms: budget.elapsed(),
      vector_candidates: 0,
      rerank_applied: false,
      budget_exceeded: false,
    };
  }

  // 3. Enrich from D1.
  const ids = matches.map((m) => m.id);
  const docMap = await enrichFromD1(ids, env);
  budget.checkpoint('d1-enrich');

  // Merge Vectorize score into the doc objects.
  const candidates: SearchDocument[] = matches
    .filter((m) => docMap.has(m.id))
    .map((m) => ({ ...docMap.get(m.id)!, score: m.score }));

  // 4. Rerank — only if budget allows.
  let reranked: SearchDocument[];
  let rerankApplied = false;

  if (budget.remaining() > 300) { // need at least 300 ms for reranker
    reranked = await rerank(query, candidates, env);
    rerankApplied = true;
    budget.checkpoint('rerank');
  } else {
    // Fallback: return Vectorize cosine-similarity order.
    reranked = candidates.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  }

  // 5. Filter and truncate.
  const final = reranked
    .filter((d) => (d.rerank_score ?? d.score ?? 0) >= minRerankScore)
    .slice(0, finalTopK);

  return {
    results:            final,
    latency_ms:         budget.elapsed(),
    vector_candidates:  candidates.length,
    rerank_applied:     rerankApplied,
    budget_exceeded:    budget.exceeded(),
  };
}

// ── Document indexing helper ──────────────────────────────────────────────
// Embed and upsert a document into both Vectorize and D1.

async function indexDocument(
  doc: { id: string; title: string; body: string; url?: string },
  env: Env
): Promise<void> {
  const text = `${doc.title}\n${doc.body}`;
  const embResult = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [text],
  });
  const vector = (embResult as unknown as { data: number[][] }).data[0];

  // Upsert into Vectorize.
  await env.VECTORIZE.upsert([
    {
      id:       doc.id,
      values:   vector,
      metadata: { title: doc.title, url: doc.url ?? '' },
    },
  ]);

  // Upsert into D1 for full-text retrieval.
  await env.DB
    .prepare(`
      INSERT INTO documents (id, title, body, url)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET title=excluded.title, body=excluded.body, url=excluded.url
    `)
    .bind(doc.id, doc.title, doc.body, doc.url ?? null)
    .run();
}

// ── Request handler ───────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /index — index a document.
    if (request.method === 'POST' && url.pathname === '/index') {
      const doc = await request.json<{
        id: string; title: string; body: string; url?: string;
      }>();
      await indexDocument(doc, env);
      return Response.json({ ok: true, id: doc.id });
    }

    // POST /search — search with reranking.
    if (request.method === 'POST' && url.pathname === '/search') {
      const body = await request.json<{
        query:           string;
        vector_top_k?:   number;
        final_top_k?:    number;
        budget_ms?:      number;
        min_score?:      number;
      }>();

      if (!body.query) {
        return Response.json({ error: 'query is required' }, { status: 400 });
      }

      const result = await search(
        {
          query:          body.query,
          vectorTopK:     body.vector_top_k,
          finalTopK:      body.final_top_k,
          budgetMs:       body.budget_ms,
          minRerankScore: body.min_score,
        },
        env
      );

      return Response.json(result);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### wrangler.toml additions

```toml
[[vectorize]]
binding = "VECTORIZE"
index_name = "orchords-search"

[[d1_databases]]
binding  = "DB"
database_name = "orchords-db"
database_id   = "<your-d1-db-id>"
```

---

## Implementation Details

**Candidate set size (`vectorTopK`)**: Fetch more than you need — 50 candidates for a top-5 final result is a safe default. The reranker improves precision; the larger the candidate pool, the higher the recall ceiling. Diminishing returns beyond ~100.

**Token budget guard**: `doc.body.slice(0, 512)` prevents the reranker from receiving documents longer than its context window. For long documents, use the first 512 characters (introduction/summary), or chunk the document at index time and rerank chunks separately.

**Latency budget**: A 2-second budget is appropriate for interactive search. The embed + vectorize steps typically take 150–300 ms combined. The reranker on 50 candidates takes 200–600 ms. D1 enrichment takes 10–50 ms. If the reranker budget is tight, reduce `vectorTopK` to 20.

**Score thresholding**: `minRerankScore` defaults to 0 (pass everything). A value of 0.5 filters out clearly irrelevant results. Calibrate on your data by logging rerank scores for known-good and known-bad queries.

**Cross-encoder vs bi-encoder tradeoff summary**:

| Property | Bi-encoder (Vectorize) | Cross-encoder (reranker) |
|---|---|---|
| Query time | O(1) ANN | O(n) per candidate |
| Accuracy | Good | Better |
| Handles negation | Poorly | Well |
| Use case | Candidate retrieval | Final ranking |

---

## Anti-patterns

- **Running the reranker on the full corpus**: The reranker is O(n). Run it only on ANN candidates (top-50 max).
- **Using the reranker without a Vectorize pre-filter**: Without ANN pre-filtering, reranking is too slow. Always use the two-stage pattern.
- **Sending full document bodies to the reranker**: Pass only the first 512 characters. Long inputs exceed the model's context window and degrade scores.
- **Ignoring latency budget**: Without budget enforcement, a slow Vectorize or D1 query leaves no time for reranking and the request times out entirely.
- **Skipping D1 enrichment and relying on Vectorize metadata**: Vectorize metadata has a size limit (~1 KB per vector). Store full document content in D1.

---

## Gotchas

- `bge-reranker-base` output `response` array is sorted by descending score already, but the `index` field refers to the original `contexts` array position — re-map carefully.
- Vectorize `query()` returns `matches` not `results`. Destructure accordingly: `results.matches ?? []`.
- D1 `IN (?)` with a single placeholder will not bind an array — build the placeholder string dynamically: `ids.map(() => '?').join(', ')`.
- `returnMetadata: 'all'` on Vectorize adds latency; use `returnMetadata: 'indexed'` if you only need a subset of metadata fields.
- Workers AI model cold starts can add 500 ms–2 s on the first request after inactivity. Warm-up pings or keeping a light request flowing mitigate this.

---

## Verification

```bash
# Index a test document
curl -s -X POST http://localhost:8787/index \
  -H 'Content-Type: application/json' \
  -d '{"id":"doc-1","title":"Cloudflare Workers AI","body":"Workers AI lets you run machine learning models on the Cloudflare network without managing infrastructure.","url":"https://developers.cloudflare.com/workers-ai/"}' | jq .

# Search with reranking
curl -s -X POST http://localhost:8787/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"how to run ML models on Cloudflare","vector_top_k":20,"final_top_k":3}' | jq '{ results: [.results[] | {title, rerank_score}], latency_ms, rerank_applied }'

# Verify latency budget enforcement
curl -s -X POST http://localhost:8787/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"test","budget_ms":100}' | jq .budget_exceeded
```

---

## Related

- `documentation/categories/ai-ml/workers-ai-function-calling-tool-use.md` — use search results as tool output
- `documentation/categories/ai-ml/workers-ai-prompt-caching-kv.md` — cache reranked results
- Cloudflare Vectorize docs: https://developers.cloudflare.com/vectorize/
- BAAI/bge-reranker model: https://developers.cloudflare.com/workers-ai/models/bge-reranker-base/

---

## Sources

- Cloudflare Vectorize documentation (2025)
- BAAI BGE Reranker technical report
- "Improving Retrieval with Cross-Encoders" — Sentence-Transformers docs
