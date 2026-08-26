# RAG Parent Document Retrieval Pattern

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your RAG pipeline retrieves semantically relevant chunks but the LLM's generated answers are missing critical context — the answer references a concept introduced two paragraphs before the retrieved chunk, or relies on a table header that was split into a separate chunk. Increasing chunk size degrades retrieval precision.

## Context
The parent-document retrieval pattern (also called small-to-large retrieval) stores two representations of every document section: small child chunks (128–256 tokens) for high-precision vector search, and larger parent blocks (512–1024 tokens) that preserve surrounding context for LLM generation. The vector index holds only child chunks; after retrieval, each child's parent ID is resolved and the full parent block is passed to the model. This gives you retrieval precision from small chunks and generation quality from large context windows.

## Document Preparation and Chunking Strategy

Split documents into parent blocks first, then sub-split each block into child chunks. Store the parent-to-child mapping in D1.

```typescript
// src/chunker.ts
interface ParentBlock {
  id:       string;   // e.g. "doc-42:block-3"
  docId:    string;
  blockIdx: number;
  content:  string;   // 512-1024 tokens
}

interface ChildChunk {
  id:        string;   // e.g. "doc-42:block-3:chunk-1"
  parentId:  string;
  chunkIdx:  number;
  content:   string;   // 128-256 tokens
}

function splitIntoParentBlocks(docId: string, text: string, blockSize = 800): ParentBlock[] {
  // Split on paragraph boundaries, targeting ~800 chars (~200 tokens)
  const paragraphs = text.split(/\n{2,}/);
  const blocks: ParentBlock[] = [];
  let current = "";
  let blockIdx = 0;

  for (const para of paragraphs) {
    if (current.length + para.length > blockSize && current.length > 0) {
      blocks.push({ id: `${docId}:block-${blockIdx}`, docId, blockIdx, content: current.trim() });
      blockIdx++;
      current = para;
    } else {
      current += (current ? "\n\n" : "") + para;
    }
  }
  if (current.trim()) {
    blocks.push({ id: `${docId}:block-${blockIdx}`, docId, blockIdx, content: current.trim() });
  }
  return blocks;
}

function splitIntoChildChunks(block: ParentBlock, chunkSize = 200): ChildChunk[] {
  const words   = block.content.split(/\s+/);
  const chunks: ChildChunk[] = [];
  const overlap = 20; // word overlap between adjacent child chunks
  let chunkIdx  = 0;

  for (let i = 0; i < words.length; i += chunkSize - overlap) {
    const content = words.slice(i, i + chunkSize).join(" ");
    if (content.trim()) {
      chunks.push({
        id:       `${block.id}:chunk-${chunkIdx}`,
        parentId: block.id,
        chunkIdx,
        content,
      });
      chunkIdx++;
    }
  }
  return chunks;
}

export { splitIntoParentBlocks, splitIntoChildChunks, type ParentBlock, type ChildChunk };
```

## Ingestion: Storing Parents in D1, Child Embeddings in Vectorize

```typescript
// src/ingest.ts
import { splitIntoParentBlocks, splitIntoChildChunks, type ParentBlock, type ChildChunk } from "./chunker";

interface Env {
  AI:        Ai;
  VECTORIZE: VectorizeIndex;
  DB:        D1Database;
}

async function ingestDocument(env: Env, docId: string, content: string): Promise<void> {
  const blocks = splitIntoParentBlocks(docId, content);

  // Persist parent blocks in D1
  const insertStmts = blocks.map((b) =>
    env.DB
      .prepare("INSERT OR REPLACE INTO parent_blocks (id, doc_id, block_idx, content) VALUES (?, ?, ?, ?)")
      .bind(b.id, b.docId, b.blockIdx, b.content)
  );
  await env.DB.batch(insertStmts);

  // Build child chunks and embed them
  const allChildren: ChildChunk[] = blocks.flatMap((b) => splitIntoChildChunks(b));

  for (let i = 0; i < allChildren.length; i += 100) {
    const batch  = allChildren.slice(i, i + 100);
    const result = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
      text: batch.map((c) => c.content),
    });

    await env.VECTORIZE.upsert(
      batch.map((c, j) => ({
        id:       c.id,
        values:   result.data[j],
        metadata: {
          parentId:  c.parentId,
          docId:     docId,
          chunkIdx:  c.chunkIdx,
          // Store child text for fallback display
          childText: c.content.slice(0, 200),
        },
      }))
    );
  }
}

export { ingestDocument };
```

## D1 Schema

```sql
-- Run via wrangler d1 execute
CREATE TABLE IF NOT EXISTS parent_blocks (
  id        TEXT    PRIMARY KEY,
  doc_id    TEXT    NOT NULL,
  block_idx INTEGER NOT NULL,
  content   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parent_blocks_doc ON parent_blocks (doc_id);
```

## Retrieval: Small Chunks for Search, Large Parents for Generation

```typescript
// src/retrieve.ts
interface Env {
  AI:        Ai;
  VECTORIZE: VectorizeIndex;
  DB:        D1Database;
}

interface RetrievedContext {
  parentId:     string;
  docId:        string;
  parentContent: string;
  score:        number;
}

async function retrieveParentContext(
  env: Env,
  query: string,
  topK     = 6,
  topKChild = 12
): Promise<RetrievedContext[]> {
  // 1. Embed the query
  const queryEmbedding = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [query],
  });

  // 2. Retrieve more child chunks than needed; parent deduplication will reduce count
  const results = await env.VECTORIZE.query(queryEmbedding.data[0], {
    topK: topKChild,
    returnMetadata: "all",
  });

  // 3. Deduplicate by parentId, keeping the highest child score per parent
  const parentScores = new Map<string, { score: number; docId: string }>();

  for (const match of results.matches) {
    const parentId = match.metadata?.parentId as string | undefined;
    const docId    = match.metadata?.docId    as string | undefined;
    if (!parentId || !docId) continue;

    const existing = parentScores.get(parentId);
    if (!existing || match.score > existing.score) {
      parentScores.set(parentId, { score: match.score, docId });
    }
  }

  // 4. Sort by score and take top-K unique parents
  const topParents = [...parentScores.entries()]
    .sort(([, a], [, b]) => b.score - a.score)
    .slice(0, topK);

  // 5. Fetch full parent content from D1
  if (topParents.length === 0) return [];

  const ids          = topParents.map(([id]) => id);
  const placeholders = ids.map(() => "?").join(",");
  const { results: rows } = await env.DB
    .prepare(`SELECT id, doc_id, content FROM parent_blocks WHERE id IN (${placeholders})`)
    .bind(...ids)
    .all<{ id: string; doc_id: string; content: string }>();

  const contentByParentId = new Map(rows.map((r) => [r.id, r]));

  return topParents
    .map(([parentId, { score, docId }]) => {
      const row = contentByParentId.get(parentId);
      if (!row) return null;
      return { parentId, docId, parentContent: row.content, score };
    })
    .filter((r): r is RetrievedContext => r !== null);
}

export { retrieveParentContext, type RetrievedContext };
```

## Generation with Parent Context

```typescript
// src/index.ts
import { retrieveParentContext } from "./retrieve";

interface Env {
  AI:        Ai;
  VECTORIZE: VectorizeIndex;
  DB:        D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { query } = await request.json<{ query: string }>();

    const contexts = await retrieveParentContext(env, query, 5);

    const contextText = contexts
      .map((c, i) => `[Source ${i + 1}]\n${c.parentContent}`)
      .join("\n\n---\n\n");

    const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [
        {
          role: "system",
          content: [
            "Answer the question using ONLY the provided sources.",
            "Cite sources as [Source N].",
            "If the answer is not in the sources, say so.",
          ].join(" "),
        },
        {
          role: "user",
          content: `Sources:\n\n${contextText}\n\nQuestion: ${query}`,
        },
      ],
      max_tokens: 1024,
      temperature: 0.2,
    });

    return Response.json({
      answer:   result.response,
      sources:  contexts.map((c) => ({ parentId: c.parentId, docId: c.docId, score: c.score })),
    });
  },
};
```

## Anti-patterns
- Using the same chunk size for both indexing and generation — small chunks for indexing, large parents for generation is the whole point
- Storing parent content in vector metadata — Vectorize metadata is limited to 10KB per vector; use D1 or R2 for large parent blocks
- Returning child chunk text to the LLM instead of parent content after retrieval — defeats the purpose of the pattern
- Not deduplicating by parent ID — multiple children from the same parent will flood the context window with overlapping text
- Using parent blocks larger than the model's effective context window — aim for parents that fit 5–10 of them within the 8K–32K context

## Gotchas
- Retrieving `topKChild = 12` and deduplicating to `topK = 6` parents means you may see fewer than 6 parents if multiple children share parents — tune both parameters together
- D1 `IN (?)` queries perform a full table scan unless there is an index on the `id` column; `id` as `PRIMARY KEY` has an implicit index so this is fine, but explicit `WHERE id = ?` per row with `batch()` may be faster for very small result sets
- Child chunk overlap (the `overlap` word window) slightly inflates the total number of vectors — account for this in Vectorize capacity planning
- Paragraph-boundary splitting can produce very short blocks for documents with many short paragraphs (e.g. legal bullets) — add a minimum block size floor of ~100 characters

## Verification
```bash
# Ingest a test document
curl -X POST http://localhost:8787/ingest \
  -H "Content-Type: application/json" \
  -d '{"docId":"doc-1","content":"Long article text here..."}'

# Check parent blocks stored in D1
wrangler d1 execute MY_DB --command="SELECT id, length(content) as len FROM parent_blocks LIMIT 10"

# Query and confirm parent content is returned, not child snippets
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{"query":"What does the article say about X?"}' \
  | jq '.sources, (.answer | length)'
```

## Related
- [rag-architecture-overview.md](rag-architecture-overview.md)
- [rag-chunking-strategies-embedding-models.md](rag-chunking-strategies-embedding-models.md)
- [rag-document-chunking.md](rag-document-chunking.md)
- [rag-context-compression.md](rag-context-compression.md)
- [cloudflare-vectorize-patterns.md](cloudflare-vectorize-patterns.md)

## Sources
- LangChain Parent Document Retriever concept: https://python.langchain.com/docs/how_to/parent_document_retriever/
- Cloudflare Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
