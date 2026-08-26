# vectorize-best-practices

**Issue:** Vectorize — vector search, RAG, embedding
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a "find similar documents" feature. You
loop through all documents and compute cosine
similarity. It works for 1k documents. It dies at
100k. You wish there were a vector DB.

## Root cause
**Vector search needs a vector DB.** Use Vectorize.

**Source:** Vectorize docs:
https://developers.cloudflare.com/vectorize/

## The "Vectorize" concept

Vectorize is CF's vector DB:
- **Edge-distributed:** Globally replicated
- **Sub-50ms latency:** At the edge
- **5M vectors / index:** Per index
- **20M vectors / index (2026):** Doubled limit
- **200k vectors / namespace:** Per namespace

The vector search is at the edge.

## The "create index" pattern

For creating an index:
```bash
npx wrangler vectorize create my-index \
  --dimensions=768 \
  --metric=cosine
```

The index is created.

## The "binding" pattern

For the binding:
```toml
[[vectorize]]
binding = "VECTOR_INDEX"
index_name = "my-index"
```

The binding is in `wrangler.toml`.

## The "insert" pattern

For inserting vectors:
```ts
// Single
await env.VECTOR_INDEX!.insert([{
  id: 'doc_1',
  values: [0.1, 0.2, ...],  // 768 dimensions
  metadata: { text: 'Hello world', sourceId: 'src_1' },
}]);

// Batch
await env.VECTOR_INDEX!.insert([
  { id: 'doc_2', values: [...], metadata: {...} },
  { id: 'doc_3', values: [...], metadata: {...} },
]);
```

The vectors are inserted.

## The "upsert" pattern

For upsert:
```ts
await env.VECTOR_INDEX!.upsert([{
  id: 'doc_1',
  values: [0.3, 0.4, ...],
  metadata: { text: 'Updated' },
}]);
```

The vector is updated or inserted.

## The "query" pattern

For querying:
```ts
const results = await env.VECTOR_INDEX!.query(queryVector, {
  topK: 10,
  filter: { sourceId: { $eq: 'src_1' } },
  returnMetadata: 'all',
});

// results: { matches: [{ id, score, metadata }] }
```

The top-K is returned.

## The "RAG pipeline" pattern

For RAG:
```ts
async function rag(query: string, env: Env): Promise<string> {
  // 1. Embed the query
  const queryEmbedding = await env.AI!.run('@cf/baai/bge-base-en-v1.5', {
    text: query,
  });

  // 2. Search Vectorize
  const docs = await env.VECTOR_INDEX!.query(queryEmbedding.data[0], {
    topK: 5,
  });

  // 3. Build the prompt
  const context = docs.matches.map(d => d.metadata.text).join('\n');
  const prompt = `Use the context to answer:\n\n${context}\n\nQ: ${query}\nA:`;

  // 4. Generate
  const response = await env.AI!.run('@cf/meta/llama-2-7b-chat-int8', {
    prompt,
  });
  return response.response;
}
```

The RAG pipeline works.

## The "chunking" pattern

For chunking:
- **Smaller (200-300 tokens):** Better precision
- **Larger (400-500 tokens):** More context
- **Overlap (10-15%):** Don't lose context

```ts
function chunk(text: string, chunkSize = 400, overlap = 40): string[] {
  const words = text.split(/\s+/);
  const chunks: string[] = [];
  for (let i = 0; i < words.length; i += chunkSize - overlap) {
    chunks.push(words.slice(i, i + chunkSize).join(' '));
  }
  return chunks;
}
```

The chunks are computed.

## The "embedding model" pattern

For embedding models:
- **bge-small-en-v1.5:** 384 dim, fast
- **bge-base-en-v1.5:** 768 dim, default
- **bge-large-en-v1.5:** 1024 dim, best quality
- **OpenAI text-embedding-3:** 1536 dim

For most apps, **bge-base-en-v1.5** is the right balance.

## The "metadata filter" pattern

For metadata filtering:
```ts
// At index creation
const index = await env.VECTOR_INDEX!.describe();
// Filter fields must be declared at creation

// At query
const results = await env.VECTOR_INDEX!.query(vector, {
  topK: 10,
  filter: {
    sourceId: { $eq: 'src_1' },
    language: { $in: ['en', 'es'] },
    createdAt: { $gt: 1700000000 },
  },
});
```

The filter is pre-declared.

## The "Vectorize + D1" pattern

For Vectorize + D1:
- **Vectorize:** Vectors
- **D1:** Metadata + source text

```ts
// At query
const results = await env.VECTOR_INDEX!.query(queryVector, { topK: 5 });

// Hydrate from D1
const docIds = results.matches.map(m => m.id);
const placeholders = docIds.map(() => '?').join(',');
const docs = await env.DB!.prepare(
  `SELECT * FROM documents WHERE id IN (${placeholders})`
).bind(...docIds).all();
```

The metadata is in D1.

## The "RAG chunking strategy" pattern

For different content:
| Content | Strategy | Size |
|---|---|---|
| **API docs** | Semantic on endpoints | 200-400 |
| **Legal** | Semantic on clauses | 500-800 |
| **Support tickets** | Small chunks | 200-300 |
| **Tech guides** | Medium with overlap | 400-500 |
| **Mixed corpus** | Route by type | varies |

**Source:** RAG best practices.

## The "Vectorize cost" pattern

For cost:
- **Storage:** $0.05/GB/mo
- **Queries:** $0.01/M (dimensions)
- **Writes:** Free (in 2026)
- **Reads:** Tiered

**Source:** Vectorize pricing.

## The "Vectorize observability" pattern

For observability:
- **Index size:** Vector count
- **Query count:** Per minute
- **Query latency:** p50, p95, p99
- **Insert count:** Per minute

The metrics are in the CF dashboard.

## The "Vectorize anti-pattern" anti-patterns

### 1. No chunking
- **Issue:** Whole docs in one vector
- **Fix:** Chunk first

### 2. Wrong model
- **Issue:** Bad retrieval
- **Fix:** bge-base-en-v1.5 (default)

### 3. No metadata
- **Issue:** Can't hydrate
- **Fix:** Store source text

### 4. No filter
- **Issue:** Searches too broad
- **Fix:** Pre-declared filter fields

### 5. No RAG
- **Issue:** LLM hallucinates
- **Fix:** RAG

### 6. No overlap
- **Issue:** Context lost at boundaries
- **Fix:** 10-15% overlap

## Verification
- **Test:** Insert works
- **Test:** Query works
- **Test:** RAG returns correct
- **Live:** Vectorize metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no chunking" anti-pattern.** Chunk first.
- **The "no metadata" anti-pattern.** Store source.
- **The "no RAG" anti-pattern.** Use RAG.

## Related
- `cloudflare/workers-best-practices.md`
- `cloudflare/ai-gateway-best-practices.md` (planned)
- `feature-cookbook-ai-ml-detail.md`
- Vectorize: https://developers.cloudflare.com/vectorize/
- RAG guide: https://developers.cloudflare.com/workers-ai/guides/tutorials/build-a-retrieval-augmented-generation-ai/
