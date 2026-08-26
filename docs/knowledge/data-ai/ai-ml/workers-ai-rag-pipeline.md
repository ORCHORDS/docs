# Workers AI — Full RAG Pipeline with Vectorize and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to let users query a private knowledge base (product docs, legal contracts, internal wikis) using natural language and receive accurate, grounded answers — without fine-tuning a model. Retrieval-Augmented Generation (RAG) keeps the knowledge base outside the model, so it can be updated instantly and answers can be traced to source documents.

---

## Context

Cloudflare's stack provides all RAG primitives natively:

| RAG stage | Cloudflare primitive |
|---|---|
| Embed text chunks | Workers AI `@cf/baai/bge-base-en-v1.5` |
| Store / query vectors | Vectorize index (ANN) |
| Keyword fallback | D1 (SQLite full-text search) |
| LLM generation | Workers AI `@cf/meta/llama-3.1-8b-instruct` |
| Document metadata | D1 table |

All compute runs inside the Worker; no external HTTP calls required.

---

## Solution

```typescript
import { z } from 'zod';

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  DB: D1Database;
}

// ── Types ────────────────────────────────────────────────────────────────────

interface Chunk {
  id: string;       // "doc:{docId}:chunk:{n}"
  docId: string;
  text: string;
  position: number; // chunk index within document
}

interface RetrievedChunk extends Chunk {
  score: number;
  source: string;   // document title or URL
}

// ── 1. Document ingestion ────────────────────────────────────────────────────

const CHUNK_SIZE = 400;   // tokens ~= chars / 4; 400 ≈ 1600 chars
const CHUNK_OVERLAP = 80; // 20 % overlap to avoid boundary misses

function splitIntoChunks(text: string): string[] {
  const words = text.split(/\s+/);
  const chunks: string[] = [];
  let start = 0;

  while (start < words.length) {
    const end = Math.min(start + CHUNK_SIZE, words.length);
    chunks.push(words.slice(start, end).join(' '));
    start += CHUNK_SIZE - CHUNK_OVERLAP;
  }
  return chunks;
}

async function ingestDocument(
  env: Env,
  docId: string,
  title: string,
  content: string,
): Promise<void> {
  const chunks = splitIntoChunks(content);

  // Embed all chunks in one batch (max 100 per call)
  const BATCH = 100;
  const allEmbeddings: number[][] = [];

  for (let i = 0; i < chunks.length; i += BATCH) {
    const batch = chunks.slice(i, i + BATCH);
    const result = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
      text: batch,
    });
    allEmbeddings.push(...(result as { data: number[][] }).data);
  }

  // Build Vectorize records
  const vectors: VectorizeVector[] = chunks.map((text, idx) => ({
    id: `doc:${docId}:chunk:${idx}`,
    values: allEmbeddings[idx],
    metadata: { docId, position: idx, textPreview: text.slice(0, 120) },
  }));

  // Upsert to Vectorize (max 1000 per upsert)
  for (let i = 0; i < vectors.length; i += 1000) {
    await env.VECTORIZE.upsert(vectors.slice(i, i + 1000));
  }

  // Store full text in D1 for keyword fallback and citation display
  await env.DB.batch(
    chunks.map((text, idx) =>
      env.DB.prepare(
        `INSERT OR REPLACE INTO chunks (id, doc_id, position, text)
         VALUES (?, ?, ?, ?)`,
      ).bind(`doc:${docId}:chunk:${idx}`, docId, idx, text),
    ),
  );

  await env.DB.prepare(
    `INSERT OR REPLACE INTO documents (id, title, chunk_count)
     VALUES (?, ?, ?)`,
  ).bind(docId, title, chunks.length).run();

  console.log(`Ingested doc ${docId}: ${chunks.length} chunks`);
}

// ── 2. Hybrid retrieval ──────────────────────────────────────────────────────

async function retrieveChunks(
  env: Env,
  query: string,
  topK: number = 5,
): Promise<RetrievedChunk[]> {
  // Embed the query
  const embResult = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [query],
  });
  const queryVec = (embResult as { data: number[][] }).data[0];

  // ANN search in Vectorize
  const vectorResults = await env.VECTORIZE.query(queryVec, {
    topK,
    returnMetadata: 'all',
  });

  const chunkIds = vectorResults.matches.map((m) => m.id);

  // Fetch full chunk text from D1
  const placeholders = chunkIds.map(() => '?').join(',');
  const rows = await env.DB.prepare(
    `SELECT c.id, c.doc_id, c.position, c.text, d.title
     FROM chunks c
     JOIN documents d ON d.id = c.doc_id
     WHERE c.id IN (${placeholders})`,
  )
    .bind(...chunkIds)
    .all<{ id: string; doc_id: string; position: number; text: string; title: string }>();

  const rowMap = new Map(rows.results.map((r) => [r.id, r]));

  const semanticChunks: RetrievedChunk[] = vectorResults.matches
    .filter((m) => rowMap.has(m.id))
    .map((m) => {
      const row = rowMap.get(m.id)!;
      return {
        id: row.id,
        docId: row.doc_id,
        text: row.text,
        position: row.position,
        score: m.score,
        source: row.title,
      };
    });

  // D1 keyword fallback when vector results are sparse (score < 0.5)
  const needsFallback = semanticChunks.filter((c) => c.score < 0.5).length > topK / 2;
  if (needsFallback) {
    const ftsRows = await env.DB.prepare(
      `SELECT c.id, c.doc_id, c.position, c.text, d.title
       FROM chunks c
       JOIN documents d ON d.id = c.doc_id
       WHERE c.text LIKE ? LIMIT ?`,
    )
      .bind(`%${query.split(' ').slice(0, 3).join('%')}%`, topK)
      .all<{ id: string; doc_id: string; position: number; text: string; title: string }>();

    for (const row of ftsRows.results) {
      if (!semanticChunks.find((c) => c.id === row.id)) {
        semanticChunks.push({
          id: row.id,
          docId: row.doc_id,
          text: row.text,
          position: row.position,
          score: 0.4, // keyword match baseline score
          source: row.title,
        });
      }
    }
  }

  // Deduplicate and sort by score descending
  return semanticChunks
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
}

// ── 3. Context window management ─────────────────────────────────────────────

const MAX_CONTEXT_CHARS = 6000; // safe budget for llama-3.1-8b 8k context

function buildContext(chunks: RetrievedChunk[]): string {
  const parts: string[] = [];
  let total = 0;

  for (const chunk of chunks) {
    const entry = `[Source: ${chunk.source}]\n${chunk.text}\n`;
    if (total + entry.length > MAX_CONTEXT_CHARS) break;
    parts.push(entry);
    total += entry.length;
  }

  return parts.join('\n---\n');
}

// ── 4. LLM generation with context ───────────────────────────────────────────

async function generateAnswer(
  env: Env,
  query: string,
  chunks: RetrievedChunk[],
): Promise<{ answer: string; citations: string[] }> {
  const context = buildContext(chunks);
  const citations = [...new Set(chunks.map((c) => c.source))];

  const messages: RoleScopedChatInput[] = [
    {
      role: 'system',
      content:
        'You are a helpful assistant. Answer the user question using ONLY the provided context. ' +
        'If the context does not contain enough information, say so. Do not invent facts. ' +
        'Be concise.',
    },
    {
      role: 'user',
      content: `Context:\n${context}\n\nQuestion: ${query}`,
    },
  ];

  const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages,
    max_tokens: 512,
    temperature: 0.3,
  });

  const answer = (result as { response: string }).response.trim();
  return { answer, citations };
}

// ── 5. Worker routing ────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /ingest — ingest a document
    if (url.pathname === '/ingest' && request.method === 'POST') {
      const body = await request.json<{ docId: string; title: string; content: string }>();
      await ingestDocument(env, body.docId, body.title, body.content);
      return Response.json({ ok: true });
    }

    // POST /query — answer a user question
    if (url.pathname === '/query' && request.method === 'POST') {
      const body = await request.json<{ query: string; topK?: number }>();
      const chunks = await retrieveChunks(env, body.query, body.topK ?? 5);

      if (chunks.length === 0) {
        return Response.json({ ok: true, answer: 'No relevant documents found.', citations: [] });
      }

      const { answer, citations } = await generateAnswer(env, body.query, chunks);
      return Response.json({ ok: true, answer, citations });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**Chunking strategy** — Overlap-aware word splitting (400 words, 80 word overlap) avoids losing context at paragraph boundaries. For structured docs (markdown headers), split on `\n## ` first, then word-chunk each section.

**Embedding model** — `@cf/baai/bge-base-en-v1.5` produces 768-dimensional vectors. Create the Vectorize index with `dimensions: 768` and `metric: cosine`. The model processes up to 512 tokens per text; chunks exceeding this are silently truncated, so stay within ~400 words.

**Vectorize upsert batching** — The API limit is 1000 vectors per `upsert` call. The loop handles arbitrarily large documents.

**Hybrid retrieval** — When ANN scores are low (query terms absent from training distribution), keyword LIKE fallback in D1 prevents silent no-results. A full FTS5 virtual table (`CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content=chunks)`) gives better precision for exact-match queries.

**Context budget** — 8k-context llama-3.1-8b leaves ~6000 chars after system prompt and question overhead. The `buildContext` function hard-stops at this budget to avoid truncation at the model level.

**Citations** — Unique source titles are returned alongside the answer for UI display or audit. In production, store document URLs in the `documents` table and return those instead of titles.

---

## Anti-patterns

- **Embedding the whole document as one vector** — Retrieval precision collapses; single-vector similarity conflates all topics in the document.
- **Skipping D1 metadata storage** — Vectorize metadata is limited (1024 bytes). Store full text in D1; store only a short preview in Vectorize metadata.
- **Passing all retrieved chunks to the LLM without a token budget check** — Models silently truncate over-limit context, dropping the most relevant material.
- **Re-embedding on every query without caching** — Query embedding is cheap (~1ms, ~$0.000001) but cache it in Workers KV if the same query recurs frequently.
- **Indexing without `CHUNK_OVERLAP`** — Questions about content at a chunk boundary get zero relevant results.

---

## Gotchas

- Vectorize ANN is eventually consistent after upsert; newly ingested chunks may not appear in query results for up to 60 seconds.
- `returnMetadata: 'all'` is required to read custom metadata in query results; the default returns no metadata.
- D1 has a 1 MB row size limit; very large chunks (> 100 KB) must be further split or stored in R2 with a D1 pointer.
- The embedding model is case-sensitive to whitespace normalization. Run `.trim().replace(/\s+/g, ' ')` on text before embedding.
- Workers AI billing for embeddings: charged per token on both ingestion and query paths.

---

## Verification

```bash
# Create Vectorize index
npx wrangler vectorize create kb-index --dimensions=768 --metric=cosine

# Create D1 database
npx wrangler d1 create rag-db

# Apply schema
npx wrangler d1 execute rag-db --file=schema.sql

# Deploy
npx wrangler deploy

# Ingest a document
curl -X POST https://your-worker.workers.dev/ingest \
  -H 'Content-Type: application/json' \
  -d '{"docId":"doc1","title":"Refund Policy","content":"Customers may request a refund within 30 days..."}'

# Query
curl -X POST https://your-worker.workers.dev/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"How long do I have to request a refund?"}'
# Expected: { ok: true, answer: "Customers may request a refund within 30 days.", citations: ["Refund Policy"] }
```

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  chunk_count INTEGER NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(id),
  position INTEGER NOT NULL,
  text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
```

---

## Related

- `documentation/docs/policies/ai-ml/workers-embeddings-vectorize.md` — embeddings and Vectorize fundamentals
- `documentation/docs/policies/ai-ml/workers-ai-structured-output.md` — structured extraction from retrieved content
- `documentation/docs/policies/ai-ml/workers-ai-prompt-caching-kv.md` — KV caching for repeated queries
- [Cloudflare Vectorize documentation](https://developers.cloudflare.com/vectorize/)
- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)

---

## Sources

- Cloudflare Vectorize API reference, August 2026
- Cloudflare Workers AI embedding models documentation
- Cloudflare D1 SQL reference
- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", 2020
- Internal example.com RAG service, production since 2025-Q4
