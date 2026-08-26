# cloudflare-vectorize-patterns

**Issue:** Using Cloudflare Vectorize for edge-native vector search
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
RAG at the edge requires a vector DB accessible from Cloudflare Workers without egress latency.

## Pattern / Solution
```typescript
// wrangler.toml
// [[vectorize]]
// binding = "VECTORIZE"
// index_name = "my-index"

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const query = await request.json() as { vector: number[] };
    const results = await env.VECTORIZE.query(query.vector, { topK: 5, returnMetadata: "all" });

    // Insert
    await env.VECTORIZE.insert([{ id: "1", values: embedding, metadata: { text: "chunk text" } }]);

    return Response.json(results);
  }
};
```

## Gotchas
- Max 200k vectors per index on free; 5M on paid
- Only cosine similarity supported; normalize embeddings before insert
- Use Workers AI for embeddings to keep all ops in Cloudflare network

## Related
- `vector-database-pinecone.md`
- `embedding-generation-patterns.md`
