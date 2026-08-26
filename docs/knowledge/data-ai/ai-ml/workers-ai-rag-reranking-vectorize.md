# RAG with Reranking: Vectorize + BGE Reranker + D1 Quality Metrics

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Basic RAG retrieves the top-K nearest vectors by cosine similarity, but embedding distance is a noisy proxy for relevance — especially when queries are short and documents are long. Adding a cross-encoder reranker (`@cf/baai/bge-reranker-base`) scores each (query, chunk) pair directly and re-orders them, dramatically improving the quality of context fed to the LLM. D1 tracks hit-rate and score distributions so you can measure improvement.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Bindings: `AI`, `VECTORIZE` (Vectorize index), `DB` (D1)
- Embedding model: `@cf/baai/bge-base-en-v1.5` (768 dimensions)
- Reranker model: `@cf/baai/bge-reranker-base`
- LLM: `@cf/meta/llama-3.1-8b-instruct`
- Pattern: embed query → Vectorize top-20 → rerank → top-5 to LLM → D1 metrics

---

## Section 1: Wrangler Configuration

```toml
# wrangler.toml
name = "rag-rerank"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[vectorize]]
binding = "VECTORIZE"
index_name = "docs-index"

[[d1_databases]]
binding = "DB"
database_name = "rag_metrics"
database_id = "<your-d1-id>"
```

## Section 2: D1 Schema for Retrieval Quality Metrics

```sql
-- migrations/001_rag_metrics.sql
CREATE TABLE IF NOT EXISTS retrieval_events (
  id              TEXT PRIMARY KEY,
  query           TEXT NOT NULL,
  top_vector_ids  TEXT NOT NULL,  -- JSON array of top-20 IDs
  reranked_ids    TEXT NOT NULL,  -- JSON array of top-5 IDs after rerank
  top_rerank_score REAL,          -- highest reranker score in this request
  rerank_improved INTEGER NOT NULL DEFAULT 0, -- 1 if order changed vs raw cosine
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

```bash
npx wrangler d1 execute rag_metrics --remote --file migrations/001_rag_metrics.sql
```

## Section 3: Vectorize Index Bootstrap

```bash
# Create the index (768 dims for bge-base-en-v1.5, cosine metric)
npx wrangler vectorize create docs-index \
  --dimensions 768 \
  --metric cosine

# Upsert some document chunks (one-time or via ingestion worker)
npx wrangler vectorize insert docs-index --file chunks.ndjson
# chunks.ndjson format (one JSON per line):
# {"id":"doc1-chunk0","values":[...768 floats...],"metadata":{"text":"...","source":"doc1.pdf"}}
```

## Section 4: Embedding, Retrieval, and Reranking

```typescript
// src/rag.ts
import { Ai, VectorizeIndex, D1Database } from '@cloudflare/workers-types';

interface VectorMatch {
  id: string;
  score: number;
  metadata?: { text?: string; source?: string };
}

interface RerankerResult {
  index: number;
  score: number;
}

export async function ragWithRerank(
  ai: Ai,
  vectorize: VectorizeIndex,
  db: D1Database,
  query: string
): Promise<string> {
  // 1. Embed the query
  const embedResult = await (ai as any).run('@cf/baai/bge-base-en-v1.5', {
    text: [query],
  });
  const queryVector: number[] = embedResult.data[0];

  // 2. Vectorize top-20 retrieval
  const vectorResults = await vectorize.query(queryVector, {
    topK: 20,
    returnMetadata: true,
  });
  const matches: VectorMatch[] = vectorResults.matches ?? [];

  if (matches.length === 0) {
    return 'I could not find any relevant documents for your query.';
  }

  const chunks = matches.map((m) => ({
    id: m.id,
    text: (m.metadata?.text as string) ?? '',
    cosinScore: m.score,
  }));

  // 3. Rerank with bge-reranker-base
  const rerankInput = {
    query,
    contexts: chunks.map((c) => c.text),
  };
  const rerankResult = await (ai as any).run('@cf/baai/bge-reranker-base', rerankInput);
  const scores: RerankerResult[] = rerankResult.response ?? [];

  // 4. Sort by reranker score descending, take top-5
  const ranked = scores
    .map((s) => ({ ...chunks[s.index], rerankScore: s.score }))
    .sort((a, b) => b.rerankScore - a.rerankScore)
    .slice(0, 5);

  // 5. Track whether reranking changed the order vs raw cosine
  const originalTop5Ids = chunks.slice(0, 5).map((c) => c.id);
  const rerankedTop5Ids = ranked.map((c) => c.id);
  const reorderOccurred = originalTop5Ids.join(',') !== rerankedTop5Ids.join(',');

  // 6. Write metrics to D1 (non-blocking)
  const eventId = crypto.randomUUID();
  db.prepare(
    `INSERT INTO retrieval_events
       (id, query, top_vector_ids, reranked_ids, top_rerank_score, rerank_improved)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(
      eventId,
      query,
      JSON.stringify(matches.map((m) => m.id)),
      JSON.stringify(rerankedTop5Ids),
      ranked[0]?.rerankScore ?? 0,
      reorderOccurred ? 1 : 0
    )
    .run()
    .catch((err: Error) => console.error('[metrics] D1 write failed:', err.message));

  // 7. Build LLM context from top-5 reranked chunks
  const context = ranked
    .map((c, i) => `[${i + 1}] (source: ${c.id})\n${c.text}`)
    .join('\n\n---\n\n');

  // 8. Generate answer
  const llmResult = await (ai as any).run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content:
          'You are a helpful assistant. Answer the question using ONLY the provided context. ' +
          'If the context does not contain the answer, say so.',
      },
      {
        role: 'user',
        content: `Context:\n${context}\n\nQuestion: ${query}`,
      },
    ],
    max_tokens: 768,
    temperature: 0.3,
  });

  return (llmResult as { response?: string }).response ?? 'No answer generated.';
}
```

## Section 5: Worker Entry Point

```typescript
// src/index.ts
import { ragWithRerank } from './rag';

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST { "query": "..." }', { status: 405 });
    const { query } = await request.json<{ query: string }>();
    if (!query?.trim()) return new Response('Missing query', { status: 400 });

    const answer = await ragWithRerank(env.AI, env.VECTORIZE, env.DB, query);
    return Response.json({ answer });
  },
};
```

## Section 6: Querying Metrics

```sql
-- Rerank improvement rate over last 7 days
SELECT
  DATE(created_at) AS day,
  COUNT(*) AS total_queries,
  SUM(rerank_improved) AS reordered,
  ROUND(100.0 * SUM(rerank_improved) / COUNT(*), 1) AS improvement_pct,
  ROUND(AVG(top_rerank_score), 4) AS avg_top_score
FROM retrieval_events
WHERE created_at >= datetime('now', '-7 days')
GROUP BY day
ORDER BY day DESC;
```

## Anti-patterns

- Do NOT rerank fewer than 10 candidates — the reranker's value comes from re-ordering a diverse pool; ranking 3 items adds latency for no gain.
- Do NOT use the reranker model for initial retrieval — it is a cross-encoder and requires O(N) forward passes; use it only to re-score a pre-filtered candidate set.
- Do NOT block the response on the D1 metrics write — use fire-and-forget (`.run().catch(...)`) so a D1 failure never breaks the RAG answer.
- Do NOT skip `returnMetadata: true` in Vectorize — without it you get vectors back but no `text` field to feed the reranker.
- Do NOT store full document text in Vectorize metadata if it exceeds 10 KB; store the chunk ID and look up text from D1 or R2.

## Gotchas

- `@cf/baai/bge-reranker-base` input format is `{ query: string, contexts: string[] }` — not the same as the embedder.
- Reranker scores are raw logits (can be negative); sort descending, do not threshold at 0.
- Vectorize `topK` max is 20 on standard indexes; requesting more silently returns 20.
- Workers AI `returnMetadata: true` in Vectorize returns metadata as a `Record<string, unknown>` — cast carefully.
- `bge-base-en-v1.5` produces 768-dim vectors; ensure your index was created with `--dimensions 768`.

## Verification

```bash
npx wrangler deploy

curl -X POST https://rag-rerank.<subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"query": "What is the return policy for electronics?"}'

# Check metrics
npx wrangler d1 execute rag_metrics --remote --command \
  "SELECT rerank_improved, COUNT(*) FROM retrieval_events GROUP BY rerank_improved;"
```

## Related

- `documentation/docs/policies/ai-ml/workers-ai-json-mode-structured-output.md`
- `documentation/docs/policies/ai-ml/workers-ai-function-calling-multi-step.md`
- `documentation/docs/policies/ai-ml/workers-ai-prompt-caching-kv-cost-reduction.md`

## Sources

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/workers-ai/models/bge-reranker-base/
- https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
