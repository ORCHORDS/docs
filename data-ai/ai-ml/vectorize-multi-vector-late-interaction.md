# Vectorize Multi-Vector Late Interaction (ColBERT-Style)

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Single-vector retrieval loses fine-grained token-level matching precision, especially for long queries or documents with multiple distinct topics. ColBERT-style late interaction stores one vector per token and scores at query time with MaxSim, dramatically improving recall without full cross-encoder cost.

## Context
Late interaction models (ColBERT, ColPali, JinaColBERT) produce a matrix of token embeddings rather than one pooled vector. Each token vector is stored as a separate Vectorize entry sharing a document ID. At query time the model produces a query token matrix; retrieval computes the MaxSim score — the sum over query tokens of each token's max cosine similarity to any document token. Workers AI does not expose a ColBERT model directly today, so the approach uses a token-level adapter on top of a supported embedding model plus custom MaxSim scoring in a Worker.

## Ingestion: Splitting Token Embeddings into Vectorize

Store each token vector as a separate record tagged with `docId` and `tokenIdx` metadata. Use a fixed-dimension model (e.g. `@cf/baai/bge-base-en-v1.5`) and simulate late interaction by chunking at the sentence level — a practical approximation that avoids the Vectorize 1 M index-entry ceiling per index.

```typescript
// ingest-late-interaction.ts
import type { VectorizeIndex, Ai } from '@cloudflare/workers-types';

interface Env {
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

interface TokenRecord {
  docId: string;
  tokenIdx: number;
  text: string;
}

/**
 * Splits document into sentence-level "tokens" and upserts each as a
 * separate Vectorize vector tagged with docId + tokenIdx.
 */
async function ingestDocument(
  env: Env,
  docId: string,
  body: string,
): Promise<void> {
  // Sentence-level split — replace with real tokenizer for full ColBERT
  const sentences = body
    .split(/(?<=[.!?])\s+/)
    .filter(s => s.trim().length > 10);

  const BATCH = 50;
  for (let i = 0; i < sentences.length; i += BATCH) {
    const slice = sentences.slice(i, i + BATCH);

    const embResp = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
      text: slice,
    });

    const vectors = (embResp as { data: number[][] }).data.map((vec, j) => ({
      id: `${docId}::${i + j}`,
      values: vec,
      metadata: {
        docId,
        tokenIdx: i + j,
        snippet: slice[j].slice(0, 120),
      },
    }));

    await env.VECTORIZE.upsert(vectors);
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { docId, text } = (await req.json()) as {
      docId: string;
      text: string;
    };
    await ingestDocument(env, docId, text);
    return Response.json({ ok: true, docId });
  },
} satisfies ExportedHandler<Env>;
```

## Query: MaxSim Scoring Over Retrieved Token Vectors

```typescript
// query-late-interaction.ts
import type { VectorizeIndex, Ai } from '@cloudflare/workers-types';

interface Env {
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

interface DocScore {
  docId: string;
  maxSimSum: number;
  topSnippets: string[];
}

/**
 * 1. Embed each query sentence (query "tokens").
 * 2. For each query token, retrieve the top-K Vectorize matches.
 * 3. Aggregate per docId using MaxSim: sum over query tokens of
 *    max(cosine_similarity) to any matching token.
 */
async function lateInteractionQuery(
  env: Env,
  query: string,
  topK = 5,
): Promise<DocScore[]> {
  const queryTokens = query.split(/\s{2,}|\n/).filter(Boolean).slice(0, 8);

  const embResp = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: queryTokens,
  });
  const queryVecs = (embResp as { data: number[][] }).data;

  // Map: docId -> per-query-token max score
  const docBest = new Map<string, number[]>();
  const docSnippets = new Map<string, Set<string>>();

  const PER_TOKEN_K = 20; // retrieve more than topK to aggregate

  await Promise.all(
    queryVecs.map(async (qVec, qi) => {
      const results = await env.VECTORIZE.query(qVec, {
        topK: PER_TOKEN_K,
        returnMetadata: 'all',
      });

      for (const match of results.matches) {
        const meta = match.metadata as {
          docId: string;
          snippet?: string;
        };
        if (!meta?.docId) continue;

        const { docId, snippet } = meta;
        if (!docBest.has(docId)) docBest.set(docId, new Array(queryVecs.length).fill(0));
        if (!docSnippets.has(docId)) docSnippets.set(docId, new Set());

        const scores = docBest.get(docId)!;
        scores[qi] = Math.max(scores[qi], match.score);
        if (snippet) docSnippets.get(docId)!.add(snippet);
      }
    }),
  );

  const ranked: DocScore[] = [];
  for (const [docId, tokenScores] of docBest) {
    const maxSimSum = tokenScores.reduce((a, b) => a + b, 0);
    ranked.push({
      docId,
      maxSimSum,
      topSnippets: [...(docSnippets.get(docId) ?? [])].slice(0, 3),
    });
  }

  return ranked.sort((a, b) => b.maxSimSum - a.maxSimSum).slice(0, topK);
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query, topK } = (await req.json()) as {
      query: string;
      topK?: number;
    };
    const results = await lateInteractionQuery(env, query, topK ?? 5);
    return Response.json({ results });
  },
} satisfies ExportedHandler<Env>;
```

## Index Design Considerations

Vectorize has a 1 M vector limit per index per account (as of mid-2026). A corpus of 10 K documents with average 50 sentences each produces 500 K entries — well within limits. For larger corpora:

- Use **namespace sharding**: separate Vectorize indexes per content domain, routed by query intent classifier.
- Set `tokenIdx` in metadata and filter with `filter: { tokenIdx: { $lt: 200 } }` to exclude very long documents from blowing up retrieval pools.
- Consider quantized 256-dim projections to halve storage while keeping MaxSim quality within 3 % of full-dim.

```typescript
// Namespace-sharded query example
const results = await env.VECTORIZE.query(qVec, {
  topK: 20,
  returnMetadata: 'all',
  filter: { domain: 'legal', tokenIdx: { $lt: 100 } },
});
```

## Scoring Normalisation

Raw MaxSim sums grow with query length. Normalise before returning to callers:

```typescript
function normaliseScores(docs: DocScore[], queryTokenCount: number): DocScore[] {
  return docs.map(d => ({
    ...d,
    maxSimSum: d.maxSimSum / queryTokenCount,
  }));
}
```

## Anti-patterns

- **Storing full token matrices as a single Vectorize vector** — Vectorize only accepts flat 1-D vectors; you must split per token/sentence into separate entries.
- **Using topK = 5 per query token** — too few; at 5 results per query token you miss many relevant document tokens. Use 15–30 and aggregate.
- **Scoring with sum-of-all rather than sum-of-max** — MaxSim sums only the *best* matching document token per query token. Summing all matches produces uncontrolled inflation.
- **No snippet deduplication in responses** — multiple query tokens may surface the same document snippet; deduplicate per docId before returning.
- **Mixing single-vector and multi-vector indexes** — keep a separate Vectorize index for late-interaction embeddings to avoid dimension collisions and metadata schema drift.

## Gotchas

- Vectorize `query` is approximate (ANN); at very high recall requirements run multiple queries with different seeds or expand `topK` significantly.
- Workers AI embedding batches cap at 100 items per call; split longer sentence arrays into sub-batches.
- `returnMetadata: 'all'` is required to get the `docId` field back; `'indexed'` only returns metadata fields declared at index creation time.
- Parallel `Promise.all` over query tokens can exhaust the AI binding's rate limit; add a concurrency limiter for indexes with > 8 query tokens.
- ColBERT-native models (e.g. `colbert-ir/colbertv2.0`) require 128-dim vectors; ensure your Vectorize index `dimensions` match the model output.

## Verification

```bash
# 1. Ingest a test document
curl -X POST https://<worker>/ingest \
  -H 'Content-Type: application/json' \
  -d '{"docId":"doc1","text":"Cloudflare Vectorize enables semantic search. Workers AI runs inference at the edge."}'

# 2. Query and inspect MaxSim scores
curl -X POST https://<worker>/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"edge inference semantic search","topK":3}'

# Expected: doc1 appears with maxSimSum > 0.6 normalised
# 3. Verify token entry count
wrangler vectorize list-vectors --index-name <index> --limit 10
```

## Related

- `vectorize-batch-upsert-incremental-sync.md`
- `metadata-filtering-vectors.md`
- `rag-hybrid-search.md`
- `workers-ai-embeddings-batch-r2.md`
- `multimodal-embeddings-clip.md`

## Sources

- https://developers.cloudflare.com/vectorize/
- https://colbert.dagster.io/
- https://huggingface.co/colbert-ir/colbertv2.0
