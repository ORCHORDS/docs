# RAG Pipeline with Vectorize + D1 + Workers AI

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You want to answer natural-language questions about a private document corpus without sending the entire corpus to the LLM on every request. You need semantic retrieval that surfaces the most relevant passages, injects them as context, and grounds the model's answer in your actual data.

## Context

Retrieval-Augmented Generation (RAG) decouples the knowledge store from the model. The pipeline has two phases:

1. **Ingestion** — chunk documents, embed each chunk, store vectors in Vectorize, store metadata/text in D1.
2. **Query** — embed the user question, find the top-k nearest chunks in Vectorize, fetch their text from D1, inject into the LLM prompt.

All three Cloudflare primitives (Workers AI, Vectorize, D1) are available in the same Worker, making the round-trip fast and free of egress costs.

## Solution

### 1. D1 schema for document metadata

```sql
-- migrations/0001_rag.sql
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  source_url  TEXT,
  title       TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS chunks (
  id          TEXT PRIMARY KEY,  -- used as Vectorize vector ID
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content     TEXT NOT NULL,
  token_count INTEGER,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
```

### 2. Document chunking strategy

```typescript
// src/lib/chunker.ts
export interface Chunk {
  id: string;       // chunk ID used in both D1 and Vectorize
  documentId: string;
  index: number;
  content: string;
}

/**
 * Splits text into overlapping chunks.
 * @param text       Full document text
 * @param documentId Parent document ID
 * @param maxChars   Target chunk size in characters (default 800)
 * @param overlap    Overlap in characters between chunks (default 200)
 */
export function chunkDocument(
  text: string,
  documentId: string,
  maxChars = 800,
  overlap = 200,
): Chunk[] {
  const chunks: Chunk[] = [];
  let start = 0;
  let index = 0;

  while (start < text.length) {
    const end = Math.min(start + maxChars, text.length);
    const content = text.slice(start, end).trim();

    if (content.length > 0) {
      chunks.push({
        id: `${documentId}_${index}`,
        documentId,
        index,
        content,
      });
      index++;
    }

    if (end >= text.length) break;
    start = end - overlap;
  }

  return chunks;
}
```

### 3. Embedding generation and Vectorize upsert

```typescript
// src/lib/ingest.ts
import type { Ai, Vectorize, D1Database } from '@cloudflare/workers-types';
import { chunkDocument, type Chunk } from './chunker';
import crypto from 'node:crypto';

export interface IngestOptions {
  title: string;
  sourceUrl?: string;
  text: string;
}

export async function ingestDocument(
  ai: Ai,
  vectorize: Vectorize,
  db: D1Database,
  options: IngestOptions,
): Promise<{ documentId: string; chunkCount: number }> {
  const documentId = crypto.randomUUID();

  // 1. Write document metadata to D1
  await db
    .prepare('INSERT INTO documents (id, source_url, title) VALUES (?, ?, ?)')
    .bind(documentId, options.sourceUrl ?? null, options.title)
    .run();

  // 2. Chunk the document
  const chunks = chunkDocument(options.text, documentId);

  // 3. Embed in batches of 100 (Workers AI limit per call)
  const BATCH = 100;
  for (let i = 0; i < chunks.length; i += BATCH) {
    const batch: Chunk[] = chunks.slice(i, i + BATCH);

    const embedResponse = await ai.run('@cf/baai/bge-base-en-v1.5', {
      text: batch.map((c) => c.content),
    });

    const vectors = (embedResponse as { data: number[][] }).data;

    // 4. Upsert vectors into Vectorize
    await vectorize.upsert(
      batch.map((chunk, j) => ({
        id: chunk.id,
        values: vectors[j],
        metadata: {
          documentId: chunk.documentId,
          chunkIndex: chunk.index,
        },
      })),
    );

    // 5. Write chunk text to D1
    const stmt = db.prepare(
      'INSERT INTO chunks (id, document_id, chunk_index, content, token_count) VALUES (?, ?, ?, ?, ?)',
    );
    await db.batch(
      batch.map((chunk) =>
        stmt.bind(
          chunk.id,
          chunk.documentId,
          chunk.index,
          chunk.content,
          Math.ceil(chunk.content.length / 4), // rough token estimate
        ),
      ),
    );
  }

  return { documentId, chunkCount: chunks.length };
}
```

### 4. Query: similarity search + context injection

```typescript
// src/lib/query.ts
import type { Ai, Vectorize, D1Database } from '@cloudflare/workers-types';

const TOP_K = 5;
const MIN_SCORE = 0.7;

export async function ragQuery(
  ai: Ai,
  vectorize: Vectorize,
  db: D1Database,
  userQuestion: string,
): Promise<string> {
  // 1. Embed the user question
  const embedResponse = await ai.run('@cf/baai/bge-base-en-v1.5', {
    text: [userQuestion],
  });
  const queryVector = (embedResponse as { data: number[][] }).data[0];

  // 2. Similarity search in Vectorize
  const searchResult = await vectorize.query(queryVector, {
    topK: TOP_K,
    returnMetadata: 'all',
  });

  const relevantIds = searchResult.matches
    .filter((m) => m.score >= MIN_SCORE)
    .map((m) => m.id);

  if (relevantIds.length === 0) {
    return 'I could not find relevant information to answer your question.';
  }

  // 3. Fetch chunk text from D1
  const placeholders = relevantIds.map(() => '?').join(',');
  const { results } = await db
    .prepare(`SELECT content FROM chunks WHERE id IN (${placeholders}) ORDER BY chunk_index`)
    .bind(...relevantIds)
    .all<{ content: string }>();

  const context = results.map((r) => r.content).join('\n\n---\n\n');

  // 4. Inject context into LLM prompt
  const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content: [
          'You are a helpful assistant. Answer the user question using ONLY the provided context.',
          'If the context does not contain enough information, say so explicitly.',
          'Do not make up facts.',
          '',
          '## Context',
          context,
        ].join('\n'),
      },
      { role: 'user', content: userQuestion },
    ],
    max_tokens: 1024,
    temperature: 0.2,
  });

  return (response as { response?: string }).response ?? '';
}
```

### 5. Worker entry point

```typescript
// src/index.ts
import { ingestDocument } from './lib/ingest';
import { ragQuery } from './lib/query';

export interface Env {
  AI: Ai;
  VECTORIZE: Vectorize;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /ingest  — add a document
    if (request.method === 'POST' && url.pathname === '/ingest') {
      const body = await request.json<{ title: string; text: string; sourceUrl?: string }>();
      const result = await ingestDocument(env.AI, env.VECTORIZE, env.DB, body);
      return Response.json(result);
    }

    // POST /query  — ask a question
    if (request.method === 'POST' && url.pathname === '/query') {
      const { question } = await request.json<{ question: string }>();
      const answer = await ragQuery(env.AI, env.VECTORIZE, env.DB, question);
      return Response.json({ answer });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### 6. wrangler.jsonc bindings

```jsonc
{
  "name": "rag-worker",
  "main": "src/index.ts",
  "compatibility_date": "2025-09-01",
  "ai": { "binding": "AI" },
  "vectorize": [
    {
      "binding": "VECTORIZE",
      "index_name": "rag-index",
      "dimensions": 768,
      "metric": "cosine"
    }
  ],
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "rag-db",
      "database_id": "<your-d1-id>"
    }
  ]
}
```

## Implementation Details

### Chunking parameters

| Parameter | Recommended | Rationale |
|---|---|---|
| `maxChars` | 800 | Fits comfortably in bge-base-en-v1.5 512-token window |
| `overlap` | 200 | Prevents context loss at chunk boundaries |
| `TOP_K` | 5 | Balances recall vs. prompt token cost |
| `MIN_SCORE` | 0.7 | cosine ≥ 0.7 is semantically relevant |

### Vectorize index creation

```bash
npx wrangler vectorize create rag-index --dimensions=768 --metric=cosine
```

Dimension 768 matches `@cf/baai/bge-base-en-v1.5` output. Do not mix embedding models on the same index.

### D1 setup

```bash
npx wrangler d1 create rag-db
npx wrangler d1 execute rag-db --file=migrations/0001_rag.sql
```

## Anti-patterns

- **Full-document embedding**: embedding entire documents instead of chunks loses granularity; the model retrieves whole novels when a paragraph was wanted.
- **No overlap between chunks**: sentences at chunk boundaries are semantically orphaned — always overlap by 20-25% of chunk size.
- **Re-embedding the same query model mismatch**: query and document embeddings must come from the identical model. Switching models requires re-ingesting all documents.
- **Injecting all chunks regardless of score**: low-score chunks add noise and waste token budget; always apply a minimum similarity threshold.
- **Storing vectors only (no D1)**: Vectorize metadata has a size limit; store the chunk text in D1 and keep only IDs and small metadata in Vectorize.

## Gotchas

- Vectorize `query` returns matches in score-descending order, but D1 `WHERE id IN (...)` does not preserve that order — reorder results after fetching if ranking matters.
- `@cf/baai/bge-base-en-v1.5` expects plain text; strip HTML and markdown before embedding.
- Workers AI has per-request token limits — batch embedding calls to max 100 texts per call.
- D1 `batch()` is limited to 100 statements per call; chunk your D1 inserts accordingly.
- Vectorize index writes are eventually consistent; a freshly upserted vector may not appear in queries for a few seconds.

## Verification

```bash
# Ingest a document
curl -X POST https://rag-worker.<account>.workers.dev/ingest \
  -H 'Content-Type: application/json' \
  -d '{"title":"Cloudflare Workers Overview","text":"Workers is a serverless execution environment..."}'
# => {"documentId":"...","chunkCount":1}

# Query
curl -X POST https://rag-worker.<account>.workers.dev/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is Cloudflare Workers?"}'
# => {"answer":"Workers is a serverless execution environment..."}
```

## Related

- `workers-ai-structured-output-json.md` — extracting structured data before ingestion
- `workers-ai-image-classification-r2.md` — enriching ingested assets with AI labels
- Vectorize documentation: https://developers.cloudflare.com/vectorize/
- D1 documentation: https://developers.cloudflare.com/d1/

## Sources

- Cloudflare Workers AI — Embeddings: https://developers.cloudflare.com/workers-ai/models/text-embeddings/
- Cloudflare Vectorize — Getting Started: https://developers.cloudflare.com/vectorize/get-started/
- BAAI/bge-base-en-v1.5 model card
