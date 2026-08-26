# RAG Pipeline — Cloudflare Vectorize + D1 Metadata Filtering

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project needs AI-assisted features that are grounded in platform-specific knowledge: community rules, banned keyword lists, trending content summaries, and per-community moderator FAQs. A generic LLM answers incorrectly or hallucinates platform policies. A retrieval-augmented generation (RAG) pipeline anchors answers to example project's own D1 data, returning only chunks that match the requesting community's context.

## Context

Cloudflare Vectorize is a globally distributed vector database available to Workers. D1 stores chunk metadata (community ID, content type, creation timestamp, author role) alongside full chunk text. At query time the Worker embeds the user query, searches Vectorize with a metadata filter scoped to the relevant community, fetches full chunk text from D1 using the returned vector IDs, then constructs a grounded prompt for Workers AI. This keeps the RAG pipeline fully within Cloudflare's network — no external vector DB, no egress fees.

---

## 1. Architecture Overview

```
 User query (mobile / desktop)
         │
         ▼
 ┌─────────────────┐
 │  Worker: rag.ts │
 │  1. Embed query │──► Vectorize: query(embedding, filter)
 │  2. Filter      │◄── top-K vector IDs + scores
 │  3. Fetch D1    │──► D1: SELECT text WHERE id IN (ids)
 │  4. Build ctx   │
 │  5. AI.run()    │──► Workers AI: grounded completion
 └─────────────────┘
```

Vectorize holds embeddings; D1 holds the actual text plus metadata. The separation avoids storing large text blobs in Vectorize's metadata field (capped at 10 KB per vector).

---

## 2. Embedding Model Selection

```
Embedding models available in Workers AI (mid-2026):
┌─────────────────────────────────────┬──────┬────────┬──────────────┐
│ Model                               │ Dims │ Tokens │ Use case     │
├─────────────────────────────────────┼──────┼────────┼──────────────┤
│ @cf/baai/bge-small-en-v1.5          │  384 │    512 │ Mobile-first │
│ @cf/baai/bge-base-en-v1.5           │  768 │    512 │ Balanced     │
│ @cf/baai/bge-large-en-v1.5          │ 1024 │    512 │ Max quality  │
│ @cf/baai/bge-m3                     │ 1024 │   8192 │ Multilingual │
└─────────────────────────────────────┴──────┴────────┴──────────────┘
```

example project recommendation: use `bge-base-en-v1.5` (768-d). It balances recall quality with Vectorize index size. `bge-small-en-v1.5` is acceptable for communities where latency matters most and content is primarily short posts. Avoid `bge-large-en-v1.5` unless community FAQs are long-form (> 500 tokens per chunk) — the cost premium rarely improves retrieval for short social content.

```typescript
// src/lib/embed.ts
export async function embedText(
  text: string,
  env: Env
): Promise<number[]> {
  const result = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [text],
  });
  // result.data is number[][]
  return result.data[0];
}
```

---

## 3. Chunk Size Strategy

Chunk size affects both recall and context window usage. For example project's mixed content:

```
Content type         Recommended chunk   Overlap    Rationale
─────────────────────────────────────────────────────────────────
Community rules      200-300 tokens      0          Self-contained rules
Moderator FAQs       150-200 tokens      20 tokens  Q&A pairs
Post examples        100-150 tokens      0          Each post standalone
Trending topics      50-80 tokens        0          Single-sentence summaries
Ban keyword context  30-50 tokens        0          Keyword + rationale
```

Overlap prevents a rule from being cut mid-sentence. Implement chunking at ingestion time:

```typescript
// src/lib/chunk.ts
export function chunkText(
  text: string,
  maxTokensEstimate = 200,
  overlapTokens = 20
): string[] {
  // Approximate: 1 token ≈ 4 chars for English
  const maxChars = maxTokensEstimate * 4;
  const overlapChars = overlapTokens * 4;
  const chunks: string[] = [];
  let start = 0;

  while (start < text.length) {
    const end = Math.min(start + maxChars, text.length);
    // Prefer to break at sentence boundary
    const slice = text.slice(start, end);
    const lastPeriod = slice.lastIndexOf('. ');
    const breakAt = lastPeriod > maxChars * 0.6 ? lastPeriod + 1 : slice.length;

    chunks.push(slice.slice(0, breakAt).trim());
    start += breakAt - overlapChars;
  }

  return chunks.filter(c => c.length > 20);
}
```

---

## 4. D1 Schema and Vectorize Index Setup

```sql
-- migrations/0005_rag_chunks.sql
CREATE TABLE rag_chunks (
  id          TEXT PRIMARY KEY,          -- UUID, matches Vectorize vector ID
  community_id TEXT NOT NULL,
  content_type TEXT NOT NULL,            -- 'rule' | 'faq' | 'example' | 'topic'
  text        TEXT NOT NULL,
  author_role TEXT NOT NULL DEFAULT 'system', -- 'system' | 'moderator'
  created_at  INTEGER NOT NULL,
  token_count INTEGER,
  FOREIGN KEY (community_id) REFERENCES communities(id)
);

CREATE INDEX idx_chunks_community ON rag_chunks(community_id, content_type);
```

```bash
# Create Vectorize index (run once via wrangler CLI)
wrangler vectorize create example project-rag-index \
  --dimensions=768 \
  --metric=cosine
```

```toml
# wrangler.toml
[[vectorize]]
binding = "VECTORIZE"
index_name = "example project-rag-index"

[[d1_databases]]
binding = "DB"
database_name = "example project-production"
database_id = "..."
```

---

## 5. Ingestion Pipeline

```typescript
// src/workers/rag-ingest.ts — called by scheduled Worker or admin endpoint
export async function ingestChunks(
  communityId: string,
  contentType: string,
  rawText: string,
  authorRole: string,
  env: Env
): Promise<void> {
  const chunks = chunkText(rawText);

  for (const chunk of chunks) {
    const id = crypto.randomUUID();
    const embedding = await embedText(chunk, env);

    // Insert text into D1
    await env.DB.prepare(
      `INSERT INTO rag_chunks (id, community_id, content_type, text, author_role, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(id, communityId, contentType, chunk, authorRole, Date.now()).run();

    // Insert embedding into Vectorize with metadata for filtering
    await env.VECTORIZE.insert([
      {
        id,
        values: embedding,
        metadata: {
          community_id: communityId,
          content_type: contentType,
          author_role: authorRole,
        },
      },
    ]);
  }
}
```

---

## 6. Query Pipeline with Metadata Filter

Vectorize supports metadata filters using MongoDB-style operators. Filter to the community before similarity search to prevent information leakage across communities.

```typescript
// src/workers/rag-query.ts
const TOP_K = 5;

export async function ragQuery(
  userQuery: string,
  communityId: string,
  contentTypes: string[],
  env: Env
): Promise<string> {
  // 1. Embed the query
  const queryEmbedding = await embedText(userQuery, env);

  // 2. Search Vectorize with metadata filter
  const results = await env.VECTORIZE.query(queryEmbedding, {
    topK: TOP_K,
    filter: {
      community_id: { $eq: communityId },
      content_type: { $in: contentTypes },
    },
    returnMetadata: 'none', // text lives in D1
  });

  if (results.matches.length === 0) {
    return 'No relevant context found.';
  }

  // 3. Fetch full text from D1 using returned IDs
  const ids = results.matches.map(m => m.id);
  const placeholders = ids.map(() => '?').join(', ');
  const { results: rows } = await env.DB.prepare(
    `SELECT id, text, content_type FROM rag_chunks WHERE id IN (${placeholders})`
  ).bind(...ids).all<{ id: string; text: string; content_type: string }>();

  // 4. Sort by Vectorize score (D1 returns in arbitrary order)
  const scoreMap = new Map(results.matches.map(m => [m.id, m.score]));
  const ranked = rows
    .sort((a, b) => (scoreMap.get(b.id) ?? 0) - (scoreMap.get(a.id) ?? 0));

  // 5. Build grounded context block
  const context = ranked
    .map((r, i) => `[${i + 1}] (${r.content_type}): ${r.text}`)
    .join('\n\n');

  // 6. Generate grounded response
  const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content: `You are example project's community assistant. Answer ONLY using the provided context. If the answer is not in the context, say "I don't have that information."`,
      },
      {
        role: 'user',
        content: `Context:\n${context}\n\nQuestion: ${userQuery}`,
      },
    ],
    max_tokens: 300,
  });

  return (response as { response: string }).response;
}
```

---

## 7. Mobile Context Window Limits

Mobile sessions get fewer retrieved chunks to keep the assembled prompt short and response latency low:

```typescript
function getMobileTopK(isMobile: boolean): number {
  return isMobile ? 3 : 5;
}

function buildContextPrompt(
  chunks: Array<{ text: string; content_type: string }>,
  isMobile: boolean
): string {
  const limit = isMobile ? 3 : 5;
  const maxCharsPerChunk = isMobile ? 300 : 600;

  return chunks
    .slice(0, limit)
    .map((c, i) => {
      const trimmed = c.text.slice(0, maxCharsPerChunk);
      return `[${i + 1}] ${trimmed}`;
    })
    .join('\n\n');
}
```

Total context budget for mobile: ~600 tokens (3 × 200). Desktop: ~1 200 tokens (5 × 240). Both fit within the 8 192-token context of `llama-3.1-8b-instruct`.

---

## Anti-Patterns

- **Storing full text in Vectorize metadata** — metadata is capped at 10 KB per vector; large text breaks upserts silently or truncates.
- **No metadata filter** — querying across all communities leaks content between anonymous communities.
- **Chunk size > 512 tokens** — exceeds the embedding model's token limit; text beyond 512 tokens is silently truncated, producing embeddings that misrepresent the chunk.
- **Re-embedding on every query** — the query embedding is generated per request, which is fine. Never cache query embeddings client-side (prompt drift); only chunk embeddings are stable.
- **Returning all top-K results to mobile** — 5 × 600-char chunks make the assembled prompt exceed 3 000 tokens; mobile AI latency doubles.

## Gotchas

- Vectorize `query()` returns matches **unsorted** when `returnMetadata` is `'none'`; re-sort by `score` in JavaScript after fetching text from D1.
- Vectorize metadata filters require the filter key to be **indexed** at index creation time. Use `--metadata-config` to declare filterable fields, or filters silently return zero results.
- D1 `IN` clauses are limited to **100 parameters** in a single prepared statement. If `topK` ever exceeds 100, batch the D1 lookups.
- `bge-base-en-v1.5` input is **text: string[]** (array), not a plain string. Passing a plain string returns `data: []`.
- Vectorize index updates are **eventually consistent** — freshly ingested vectors may not appear in query results for up to 60 seconds.

## Verification

```bash
# 1. Ingest a test chunk
curl -X POST https://api.example.com/admin/rag/ingest \
  -H 'Authorization: Bearer $ADMIN_TOKEN' \
  -d '{"communityId":"test-123","contentType":"rule","text":"No doxxing allowed."}'

# 2. Query after ~60s propagation delay
curl -X POST https://api.example.com/ai/rag \
  -H 'Content-Type: application/json' \
  -d '{"query":"Can I share someone'\''s address?","communityId":"test-123"}'

# Expected: grounded response citing the no-doxxing rule

# 3. Verify cross-community isolation
curl -X POST https://api.example.com/ai/rag \
  -H 'Content-Type: application/json' \
  -d '{"query":"Can I share someone'\''s address?","communityId":"other-456"}'

# Expected: "I don't have that information." (no chunks from test-123 leaked)
```

## Related

- `cloudflare-vectorize-patterns.md` — Vectorize index management
- `embedding-generation-patterns.md` — batch embedding at ingestion
- `rag-chunking-strategies-embedding-models.md` — advanced chunking
- `metadata-filtering-vectors.md` — filter syntax reference
- `vector-embeddings-d1-vectorize-search.md` — full-text hybrid search

## Sources

- Cloudflare Vectorize docs: developers.cloudflare.com/vectorize
- Cloudflare D1 docs: developers.cloudflare.com/d1
- BGE model card: huggingface.co/BAAI/bge-base-en-v1.5
- Cloudflare Workers AI models: developers.cloudflare.com/workers-ai/models
