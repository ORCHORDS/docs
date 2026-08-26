# RAG Document Pipeline with Chunking and Vectorize

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need an LLM to answer questions about your own documents — internal wikis, product manuals, support tickets — without fine-tuning. A RAG (Retrieval-Augmented Generation) pipeline chunks documents into 512-token segments, embeds them with Workers AI, stores vectors in Cloudflare Vectorize, and at query time retrieves the most relevant chunks to pass as context to the LLM.

---

## Context

Document text is split into overlapping 512-token windows (64-token overlap) so that sentences straddling a chunk boundary are captured by at least one chunk. Each chunk is embedded with `@cf/baai/bge-large-en-v1.5` (1024-dimensional output) and upserted to a Vectorize index keyed by a deterministic `sha256(docId + chunkIndex)` ID. A D1 table stores chunk metadata — source URL, document ID, chunk index, raw text — enabling the query endpoint to hydrate retrieved vector IDs back into readable context. The query endpoint embeds the user question, calls `vectorize.query` for top-5 nearest neighbours, fetches their metadata from D1, concatenates them as a context block, and calls `@cf/meta/llama-3.1-8b-instruct` with that context injected into the system prompt.

---

## Section 1 — Wrangler Config and Vectorize Index

```toml
# wrangler.toml
name = "rag-pipeline"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[ai]
binding = "AI"

[[vectorize]]
binding = "CHUNKS"
index_name = "doc-chunks"

[[d1_databases]]
binding = "DB"
database_name = "rag-meta"
database_id = "<your-d1-id>"
```

```bash
# Create the Vectorize index (1024-dim, cosine similarity)
npx wrangler vectorize create doc-chunks \
  --dimensions=1024 \
  --metric=cosine
```

---

## Section 2 — Chunker, Embedder, and Ingestor

```typescript
// src/chunker.ts
export interface Chunk {
  docId: string;
  chunkIndex: number;
  text: string;
  id: string; // hex sha256 of `${docId}:${chunkIndex}`
}

const CHUNK_TOKENS = 512;
const OVERLAP_TOKENS = 64;
// Approximate: 1 token ≈ 4 characters for English prose
const CHARS_PER_TOKEN = 4;

const CHUNK_CHARS = CHUNK_TOKENS * CHARS_PER_TOKEN;
const OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN;
const STEP_CHARS = CHUNK_CHARS - OVERLAP_CHARS;

export function chunkText(docId: string, text: string): Chunk[] {
  const chunks: Chunk[] = [];
  let start = 0;
  let chunkIndex = 0;

  while (start < text.length) {
    const end = Math.min(start + CHUNK_CHARS, text.length);
    // Prefer a sentence or paragraph boundary near the end
    let boundary = end;
    if (end < text.length) {
      const slice = text.slice(start, end);
      const lastPara = slice.lastIndexOf("\n\n");
      const lastSentence = slice.lastIndexOf(". ");
      const best = Math.max(lastPara, lastSentence);
      if (best > OVERLAP_CHARS) boundary = start + best + 1;
    }

    const chunkText = text.slice(start, boundary).trim();
    if (chunkText) {
      const rawId = `${docId}:${chunkIndex}`;
      // Deterministic hex ID via Web Crypto subtle
      chunks.push({ docId, chunkIndex, text: chunkText, id: rawId });
      chunkIndex++;
    }

    start += STEP_CHARS;
    if (start >= boundary && boundary < text.length) start = boundary;
  }

  return chunks;
}

// src/ingest.ts
import { chunkText, type Chunk } from "./chunker";
import type { Env } from "./index";

const EMBED_MODEL = "@cf/baai/bge-large-en-v1.5";
const BATCH_SIZE = 100; // Vectorize upsert limit per call

export async function ingestDocument(
  docId: string,
  sourceUrl: string,
  text: string,
  env: Env
): Promise<{ chunksIngested: number }> {
  const chunks = chunkText(docId, text);

  // Embed all chunks (Workers AI can handle up to 100 texts per call)
  const texts = chunks.map((c) => c.text);
  const embeddingBatches: number[][][] = [];

  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const batch = texts.slice(i, i + BATCH_SIZE);
    const response = (await env.AI.run(EMBED_MODEL, { text: batch })) as {
      data: number[][];
    };
    embeddingBatches.push(response.data);
  }

  const embeddings = embeddingBatches.flat();

  // Upsert to Vectorize in batches
  for (let i = 0; i < chunks.length; i += BATCH_SIZE) {
    const batch = chunks.slice(i, i + BATCH_SIZE);
    const vectors = batch.map((chunk, j) => ({
      id: chunk.id,
      values: embeddings[i + j],
      metadata: { docId: chunk.docId, chunkIndex: chunk.chunkIndex },
    }));
    await env.CHUNKS.upsert(vectors);
  }

  // Persist metadata in D1
  const stmt = env.DB.prepare(
    `INSERT OR REPLACE INTO chunks (id, doc_id, chunk_index, source_url, text)
     VALUES (?, ?, ?, ?, ?)`
  );
  const inserts = chunks.map((c) =>
    stmt.bind(c.id, c.docId, c.chunkIndex, sourceUrl, c.text)
  );
  // D1 batch supports up to 1000 statements
  for (let i = 0; i < inserts.length; i += 1000) {
    await env.DB.batch(inserts.slice(i, i + 1000));
  }

  return { chunksIngested: chunks.length };
}
```

---

## Section 3 — Query Endpoint

```typescript
// src/query.ts
import type { Env } from "./index";

const EMBED_MODEL = "@cf/baai/bge-large-en-v1.5";
const LLM_MODEL = "@cf/meta/llama-3.1-8b-instruct";
const TOP_K = 5;

export async function ragQuery(
  question: string,
  env: Env
): Promise<{ answer: string; sources: string[] }> {
  // 1. Embed the question
  const embedResponse = (await env.AI.run(EMBED_MODEL, {
    text: [question],
  })) as { data: number[][] };
  const questionVector = embedResponse.data[0];

  // 2. Retrieve top-K chunks from Vectorize
  const queryResult = await env.CHUNKS.query(questionVector, {
    topK: TOP_K,
    returnMetadata: true,
  });

  const chunkIds = queryResult.matches.map((m) => m.id);
  if (chunkIds.length === 0) {
    return { answer: "No relevant context found.", sources: [] };
  }

  // 3. Hydrate chunk text from D1
  const placeholders = chunkIds.map(() => "?").join(", ");
  const { results } = await env.DB.prepare(
    `SELECT id, source_url, text FROM chunks WHERE id IN (${placeholders})`
  )
    .bind(...chunkIds)
    .all<{ id: string; source_url: string; text: string }>();

  // Preserve retrieval order
  const idToRow = new Map(results.map((r) => [r.id, r]));
  const orderedChunks = chunkIds
    .map((id) => idToRow.get(id))
    .filter(Boolean) as { id: string; source_url: string; text: string }[];

  const context = orderedChunks
    .map((c, i) => `[${i + 1}] ${c.text}`)
    .join("\n\n---\n\n");

  // 4. Generate answer with LLM
  const llmResponse = (await env.AI.run(LLM_MODEL, {
    messages: [
      {
        role: "system",
        content:
          `You are a helpful assistant. Answer the question using ONLY the provided context.\n\n` +
          `Context:\n${context}`,
      },
      { role: "user", content: question },
    ],
  })) as { response: string };

  const sources = [...new Set(orderedChunks.map((c) => c.source_url))];

  return { answer: llmResponse.response, sources };
}

// src/index.ts
import { ingestDocument } from "./ingest";
import { ragQuery } from "./query";

export interface Env {
  AI: Ai;
  CHUNKS: VectorizeIndex;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/ingest") {
      const { docId, sourceUrl, text } = await request.json<{
        docId: string;
        sourceUrl: string;
        text: string;
      }>();
      const result = await ingestDocument(docId, sourceUrl, text, env);
      return Response.json(result);
    }

    if (request.method === "POST" && url.pathname === "/query") {
      const { question } = await request.json<{ question: string }>();
      const result = await ragQuery(question, env);
      return Response.json(result);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Chunking by fixed character count without overlap** — sentences split at hard boundaries lose context; the overlap window ensures no important sentence is only partially represented.
- **Upserting more than 100 vectors in a single `vectorize.upsert` call** — the API enforces this limit; batch client-side before upserting.
- **Passing the entire document as a single embedding** — BGE-large has a 512-token input limit; exceeding it silently truncates the input and degrades recall quality.
- **Fetching chunk text from Vectorize metadata instead of D1** — Vectorize metadata is limited to 10 KB per vector and is not designed for full-text retrieval; store text in D1 and retrieve by ID.

---

## Gotchas

- `vectorize.query` returns matches with scores; cosine similarity scores range from -1 to 1, but BGE models typically produce scores between 0.7–0.99 for genuinely relevant chunks.
- Vectorize index creation can take up to 60 seconds; queries before the index is ready return empty results without an error.
- `env.DB.batch()` accepts up to 1000 prepared statements per call — split larger ingests into multiple batches.
- The D1 `INSERT OR REPLACE` pattern on `id` (the chunk's deterministic ID) makes re-ingestion of updated documents idempotent.

---

## Verification

```bash
# Create D1 table
npx wrangler d1 execute rag-meta --command \
  "CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, doc_id TEXT, chunk_index INTEGER, source_url TEXT, text TEXT)"

# Create Vectorize index
npx wrangler vectorize create doc-chunks --dimensions=1024 --metric=cosine

# Deploy
npx wrangler deploy

# Ingest a document
curl -sX POST https://rag-pipeline.<account>.workers.dev/ingest \
  -H 'Content-Type: application/json' \
  -d '{"docId":"doc-001","sourceUrl":"https://example.com/manual.pdf","text":"Workers AI provides serverless GPU inference..."}' | jq .

# Query it
curl -sX POST https://rag-pipeline.<account>.workers.dev/query \
  -H 'Content-Type: application/json' \
  -d '{"question": "What does Workers AI provide?"}' | jq .answer
```

---

## Related

- `workers-ai-tool-calling-function-dispatch.md`
- `workers-ai-streaming-text-readable-stream.md`

---

## Sources

- Cloudflare Vectorize getting started — https://developers.cloudflare.com/vectorize/get-started/
- BGE-large-en-v1.5 model card — https://developers.cloudflare.com/workers-ai/models/bge-large-en-v1.5/
- Cloudflare RAG tutorial — https://developers.cloudflare.com/workers-ai/tutorials/build-a-retrieval-augmented-generation-ai/
