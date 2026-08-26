# Citation Grounding for RAG Responses with Vectorize and Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your RAG chatbot returns confident-sounding answers but users cannot verify where the information came from. You need every factual claim in the LLM response to link back to the exact source document chunk, measurable via a `citation_coverage` metric.

## Context

Cloudflare Vectorize stores arbitrary metadata alongside embeddings. By embedding `{ chunk_id, source_url, section_title, text }` at ingest time and instructing the LLM to emit `[chunk_id]` markers, you can post-process the raw LLM text and replace each marker with a rendered hyperlink — without a second LLM call. `citation_coverage` (cited sentences / total sentences) gives an objective quality signal you can track over time.

Required bindings:
- `AI` — Workers AI (embedding + generation)
- `VECTORIZE` — Vectorize index (768-dim, cosine metric)

## Implementation

```typescript
import { Hono } from 'hono';

type ChunkMeta = {
  chunk_id: string;
  source_url: string;
  section_title: string;
  text: string;
};

type Env = { AI: Ai; VECTORIZE: VectorizeIndex };

const app = new Hono<{ Bindings: Env }>();

// ── Ingest ──────────────────────────────────────────────────────────────────

app.post('/ingest', async (c) => {
  const chunks: ChunkMeta[] = await c.req.json();

  const vectors = await Promise.all(
    chunks.map(async (chunk) => {
      const { data } = await c.env.AI.run('@cf/baai/bge-base-en-v1.5', {
        text: [chunk.text],
      });
      return {
        id: chunk.chunk_id,
        values: data[0],
        metadata: {
          chunk_id: chunk.chunk_id,
          source_url: chunk.source_url,
          section_title: chunk.section_title,
          text: chunk.text.slice(0, 1000), // Vectorize metadata limit: 1 KB per field.
        },
      };
    }),
  );

  const result = await c.env.VECTORIZE.upsert(vectors);
  return c.json({ inserted: result.count });
});

// ── Query + cite ─────────────────────────────────────────────────────────────

async function retrieveChunks(
  env: Env,
  question: string,
  topK = 5,
): Promise<ChunkMeta[]> {
  const { data } = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [question],
  });

  const results = await env.VECTORIZE.query(data[0], {
    topK,
    returnMetadata: true,
  });

  return (results.matches ?? []).map((m) => m.metadata as unknown as ChunkMeta);
}

function buildSystemPrompt(chunks: ChunkMeta[]): string {
  const context = chunks
    .map((c) => `[${c.chunk_id}] (${c.section_title})\n${c.text}`)
    .join('\n\n');

  return (
    'You are a helpful assistant. Answer the user question using ONLY the context below. ' +
    'After each factual claim, append the chunk_id in square brackets, e.g. [abc123]. ' +
    'If the context does not contain relevant information, say "I do not know."\n\n' +
    '=== CONTEXT ===\n' +
    context
  );
}

// Replace [chunk_id] markers with <a >section_title</a>.
function groundCitations(
  rawText: string,
  chunks: ChunkMeta[],
): { html: string; citationCoverage: number } {
  const metaMap = new Map(chunks.map((c) => [c.chunk_id, c]));

  const html = rawText.replace(/\[([a-z0-9_-]+)\]/gi, (match, id) => {
    const meta = metaMap.get(id);
    if (!meta) return match; // Unknown id — leave as-is.
    return `<a  title="${meta.section_title}">[${meta.section_title}]</a>`;
  });

  // Citation coverage: fraction of sentences that contain at least one citation.
  const sentences = rawText.split(/(?<=[.!?])\s+/).filter(Boolean);
  const cited = sentences.filter((s) => /\[[a-z0-9_-]+\]/i.test(s));
  const citationCoverage = sentences.length > 0 ? cited.length / sentences.length : 0;

  return { html, citationCoverage };
}

app.post('/ask', async (c) => {
  const { question } = await c.req.json<{ question: string }>();
  if (!question) return c.json({ error: 'question required' }, 400);

  const chunks = await retrieveChunks(c.env, question);
  if (chunks.length === 0) {
    return c.json({ answer: 'I do not know.', citations: [], citationCoverage: 0 });
  }

  const systemPrompt = buildSystemPrompt(chunks);

  const response = await c.env.AI.run('@cf/meta/llama-3-8b-instruct', {
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: question },
    ],
    max_tokens: 512,
  });

  const rawAnswer = (response as any).response as string;
  const { html, citationCoverage } = groundCitations(rawAnswer, chunks);

  // Collect unique cited chunk ids for the citations array.
  const citedIds = [...rawAnswer.matchAll(/\[([a-z0-9_-]+)\]/gi)].map((m) => m[1]);
  const citations = [...new Set(citedIds)]
    .map((id) => chunks.find((c) => c.chunk_id === id))
    .filter(Boolean) as ChunkMeta[];

  return c.json({
    answer: html,
    citations: citations.map(({ chunk_id, source_url, section_title }) => ({
      chunk_id, source_url, section_title,
    })),
    citationCoverage: Math.round(citationCoverage * 100) / 100,
    retrievedChunks: chunks.length,
  });
});

export default app;
```

## Vectorize Index Setup

```bash
# Create the index (bge-base-en-v1.5 outputs 768-dim vectors).
npx wrangler vectorize create example project-kb \
  --dimensions=768 \
  --metric=cosine

# Bind in wrangler.toml:
# [[vectorize]]
# binding = "VECTORIZE"
# index_name = "example project-kb"
```

## Citation Coverage Metric

Log `citationCoverage` per request to a D1 table for trend analysis:

```typescript
// After the /ask handler resolves, inside ctx.waitUntil:
ctx.waitUntil(
  env.DB.prepare(
    'INSERT INTO rag_metrics (ts, question_hash, coverage, cited_count, chunk_count) VALUES (?, ?, ?, ?, ?)'
  ).bind(
    Date.now(),
    await sha256(question),
    citationCoverage,
    citations.length,
    chunks.length,
  ).run()
);
```

Alert if the 7-day rolling average `coverage` drops below `0.6` — it typically signals that the Vectorize index is stale or that the system prompt citation instruction was inadvertently removed.

## Anti-patterns

- **Asking the LLM to cite in a second pass** — doubles latency and cost; bake the citation instruction into the system prompt on the first call.
- **Using chunk index positions as ids** — positions change when the document is re-chunked; always use stable `chunk_id` UUIDs.
- **Storing full chunk text in metadata only** — Vectorize metadata has a 1 KB per-field limit; store the authoritative text in D1 or R2 and use metadata for lookup keys.
- **Regex-only citation parsing without a known id set** — a hallucinated `[abc]` marker will silently not match, inflating coverage. Always cross-reference against retrieved chunk ids.

## Gotchas

- `returnMetadata: true` must be passed explicitly to `VECTORIZE.query`; the default omits metadata.
- Vectorize `upsert` is eventually consistent — allow ~10 s before querying newly inserted vectors.
- The LLM may emit `[chunk_id]` in the middle of a word (e.g., `information[a1b2c3]`). The regex handles this correctly, but check edge cases in your sentence splitter.
- `citation_coverage` is sentence-level, not claim-level; a single sentence with two facts but one citation still counts as covered.

## Verification

```bash
# Ingest two test chunks.
curl -X POST https://worker.example.com/ingest \
  -H 'Content-Type: application/json' \
  -d '[{"chunk_id":"c001","source_url":"https://docs.example.com/page1","section_title":"Overview","text":"Cloudflare Workers run at the edge."}]'

# Ask a grounded question.
curl -X POST https://worker.example.com/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "Where do Cloudflare Workers run?"}' | jq .
# Expected: answer contains <a href="https://docs.example.com/page1">...
# citationCoverage > 0
```

## Related

- `workers-ai-text-to-speech-audio-streaming-r2.md` — Workers AI pipeline patterns
- `llm-token-streaming-backpressure-workers.md` — streaming LLM output
- `ai-agent-memory-persistence-durable-objects.md` — multi-turn agent memory

## Sources

- [Vectorize — Query with metadata](https://developers.cloudflare.com/vectorize/reference/client-api/#query-vectors)
- [Workers AI — Text embedding models](https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/)
- [RAG architecture on Cloudflare](https://developers.cloudflare.com/workers-ai/tutorials/build-a-retrieval-augmented-generation-ai/)
