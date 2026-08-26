# Workers AI Reranker: Cross-Encoder Passage Scoring for RAG

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your RAG pipeline retrieves the top-K passages from Vectorize using bi-encoder (embedding) similarity, but the final LLM answer still contains hallucinations or misses the most relevant document. Bi-encoders produce embeddings independently for query and document, trading cross-attention for speed. The result is that semantically-adjacent documents score similarly even when one is a far better answer — a problem cross-encoder rerankers solve by scoring query-passage pairs jointly.

This article covers wiring Workers AI's `@cf/cross-encoder/ms-marco-MiniLM-L-6-v2` (and compatible models) into a two-stage RAG pipeline: retrieve a large candidate set with Vectorize, then rerank with the cross-encoder, then pass only the top-N reranked passages to the LLM context window.

## Context

Workers AI hosts cross-encoder models in the same runtime as text generation and embedding models, meaning reranking runs at the Cloudflare edge with no external HTTP hop. Cross-encoders accept a query-passage pair and return a relevance score — the model performs full self-attention across both inputs, catching exact-match signals and fine-grained co-reference that bi-encoders miss.

The computational cost is O(K) inference calls per query (one per candidate passage), making cross-encoders impractical for large-scale first-stage retrieval but very effective as a second-stage filter over a candidate set of 20–100 passages. The Workers AI billing model counts each cross-encoder inference as a separate AI request.

## Stage 1: Bi-Encoder Retrieval from Vectorize

Retrieve a wide candidate set (top-50 to top-100) from Vectorize. The wider the initial recall, the more material the reranker has to work with:

```typescript
// types.ts
export interface Passage {
  id: string;
  text: string;
  metadata: Record<string, string>;
  biEncoderScore: number;
  rerankerScore?: number;
}

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  DB: D1Database;
}
```

```typescript
// retrieve.ts
import { Env, Passage } from "./types";

export async function retrieveCandidates(
  query: string,
  env: Env,
  topK = 50
): Promise<Passage[]> {
  // Embed the query with a bi-encoder
  const embedResponse = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [query],
  });

  const queryVector = embedResponse.data[0];

  const vectorResults = await env.VECTORIZE.query(queryVector, {
    topK,
    returnMetadata: "all",
  });

  // Hydrate passage text from D1 (stored during ingestion)
  const ids = vectorResults.matches.map((m) => m.id);
  const placeholders = ids.map(() => "?").join(",");
  const rows = await env.DB.prepare(
    `SELECT id, text, metadata FROM passages WHERE id IN (${placeholders})`
  )
    .bind(...ids)
    .all<{ id: string; text: string; metadata: string }>();

  const textMap = new Map(
    rows.results.map((r) => [r.id, { text: r.text, metadata: JSON.parse(r.metadata) }])
  );

  return vectorResults.matches
    .filter((m) => textMap.has(m.id))
    .map((m) => ({
      id: m.id,
      text: textMap.get(m.id)!.text,
      metadata: textMap.get(m.id)!.metadata,
      biEncoderScore: m.score,
    }));
}
```

## Stage 2: Cross-Encoder Reranking

Run the cross-encoder over each query-passage pair. Workers AI accepts batch inputs for cross-encoders, reducing round-trips:

```typescript
// rerank.ts
import { Env, Passage } from "./types";

/**
 * Rerank candidates using a cross-encoder model.
 * Workers AI ms-marco cross-encoders return logits (un-bounded);
 * apply sigmoid to get a probability-style score in [0, 1].
 */
export async function rerankPassages(
  query: string,
  candidates: Passage[],
  env: Env,
  topN = 5
): Promise<Passage[]> {
  if (candidates.length === 0) return [];

  // The cross-encoder model accepts an array of [query, passage] pairs
  const inputs = candidates.map((p) => ({
    query,
    passage: p.text,
  }));

  // Workers AI cross-encoder: returns an array of score objects
  const scoreResponse = await env.AI.run(
    "@cf/cross-encoder/ms-marco-MiniLM-L-6-v2",
    { inputs }
  );

  // Attach scores and sort descending
  const scored = candidates.map((passage, i) => ({
    ...passage,
    rerankerScore: sigmoid(scoreResponse[i].score),
  }));

  scored.sort((a, b) => (b.rerankerScore ?? 0) - (a.rerankerScore ?? 0));

  return scored.slice(0, topN);
}

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}
```

## Stage 3: LLM Generation with Reranked Context

Pass only the top-N reranked passages to the LLM, ordered by relevance score:

```typescript
// generate.ts
import { Env, Passage } from "./types";

export async function generateAnswer(
  query: string,
  passages: Passage[],
  env: Env
): Promise<string> {
  // Build context block ordered by reranker score (highest first)
  const context = passages
    .map((p, idx) => `[${idx + 1}] ${p.text}`)
    .join("\n\n");

  const messages: RoleScopedChatInput[] = [
    {
      role: "system",
      content:
        "You are a precise question-answering assistant. Answer using only the provided context. " +
        "If the context does not contain sufficient information, say so explicitly.",
    },
    {
      role: "user",
      content: `Context:\n${context}\n\nQuestion: ${query}`,
    },
  ];

  const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages,
    max_tokens: 512,
  });

  return response.response ?? "";
}
```

## Full Pipeline: Wiring It Together

```typescript
// worker.ts
import { Env } from "./types";
import { retrieveCandidates } from "./retrieve";
import { rerankPassages } from "./rerank";
import { generateAnswer } from "./generate";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { query } = await request.json<{ query: string }>();

    if (!query?.trim()) {
      return new Response(JSON.stringify({ error: "query is required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Stage 1: Retrieve top-50 candidates via bi-encoder + Vectorize
    const candidates = await retrieveCandidates(query, env, 50);

    if (candidates.length === 0) {
      return Response.json({ answer: "No relevant documents found.", passages: [] });
    }

    // Stage 2: Cross-encoder reranks to top-5
    const topPassages = await rerankPassages(query, candidates, env, 5);

    // Stage 3: LLM generates answer from reranked context
    const answer = await generateAnswer(query, topPassages, env);

    return Response.json({
      answer,
      passages: topPassages.map((p) => ({
        id: p.id,
        text: p.text.slice(0, 200) + "…",
        biEncoderScore: p.biEncoderScore,
        rerankerScore: p.rerankerScore,
      })),
    });
  },
};
```

## Measuring Reranker Lift

Log both bi-encoder and reranker scores to D1 to build an offline evaluation set:

```typescript
// observability.ts
interface RerankerEvent {
  query: string;
  candidateCount: number;
  topBiEncoderScore: number;
  topRerankerScore: number;
  rerankerPromotedIds: string[]; // IDs that moved into top-5 from positions 6–50
  durationMs: number;
}

async function logRerankerEvent(
  env: Env,
  event: RerankerEvent
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO reranker_events
     (query_hash, candidate_count, top_bi_score, top_reranker_score,
      promoted_count, duration_ms, created_at)
     VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
  )
    .bind(
      hashString(event.query),
      event.candidateCount,
      event.topBiEncoderScore,
      event.topRerankerScore,
      event.rerankerPromotedIds.length,
      event.durationMs
    )
    .run();
}

function hashString(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return h.toString(16);
}
```

A high `promoted_count` (IDs that jumped from rank 6–50 into the final top-5) demonstrates that the reranker is discovering signal the bi-encoder missed.

## Anti-patterns

- Reranking the full Vectorize result set at K=1000 — cross-encoder inference is O(K); limit candidates to 50–100 maximum
- Skipping the bi-encoder stage and running cross-encoder on the entire corpus — economically infeasible; cross-encoders require a candidate set
- Using cross-encoder scores as similarity thresholds without calibration — raw logits are model-specific; always apply sigmoid or softmax before threshold comparisons
- Passing reranked passages to the LLM in arbitrary order — always sort by descending reranker score; LLM attention is position-sensitive
- Not storing passage text in D1/R2 alongside vector IDs — Vectorize metadata has a size limit; full text must live in a separate store
- Reranking at request time for latency-sensitive paths without a cache — reranker adds 100–300 ms per 50 candidates

## Gotchas

- Workers AI cross-encoder models expect the input as `{ inputs: [{ query, passage }] }`, not the same shape as text-generation models. Check the model card for the exact schema.
- The ms-marco cross-encoder is trained on web search passage pairs. For domain-specific corpora (legal, medical, code), a fine-tuned or domain-matched model will outperform it substantially.
- Workers AI imposes a maximum batch size per AI run. If you have more than ~100 candidates, split into multiple batches of 50 and merge results.
- Cross-encoder scores are not comparable across different queries — you cannot cache a "good" threshold score value globally.
- The `@cf/cross-encoder/ms-marco-MiniLM-L-6-v2` model identifier may change as Workers AI updates its model catalogue; pin to a versioned alias when available.

## Verification

```typescript
// Reranker integration test: the more-specific passage should outscore the generic one
async function testRerankerOrdering(env: Env): Promise<void> {
  const query = "What is the capital of France?";

  const candidates = [
    {
      id: "generic",
      text: "France is a country in Western Europe known for its culture and cuisine.",
      metadata: {},
      biEncoderScore: 0.82,
    },
    {
      id: "specific",
      text: "Paris is the capital and most populous city of France.",
      metadata: {},
      biEncoderScore: 0.79, // bi-encoder ranked this LOWER
    },
  ];

  const reranked = await rerankPassages(query, candidates, env, 2);

  console.assert(
    reranked[0].id === "specific",
    `Reranker should promote the specific passage. Got: ${reranked[0].id}`
  );
  console.log(
    `Reranker test passed. Scores: specific=${reranked.find(p=>p.id==='specific')?.rerankerScore?.toFixed(3)}, ` +
    `generic=${reranked.find(p=>p.id==='generic')?.rerankerScore?.toFixed(3)}`
  );
}
```

## Related

- `rag-reranking.md` — general reranking concepts and BM25 hybrid approaches
- `vectorize-dot-product-vs-cosine-similarity.md` — bi-encoder metric selection
- `rag-architecture-overview.md` — two-stage retrieval pipeline design
- `workers-ai-pipeline-chaining-multi-model.md` — chaining multiple Workers AI model calls

## Sources

- Nogueira, R. & Cho, K. "Passage Re-ranking with BERT." arXiv:1901.04085, 2019
- Cloudflare Workers AI model catalogue: https://developers.cloudflare.com/workers-ai/models/
- MS MARCO dataset and cross-encoder benchmarks: https://microsoft.github.io/msmarco/
