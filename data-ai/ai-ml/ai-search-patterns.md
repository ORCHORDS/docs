# ai-search-patterns

**Issue:** Traditional keyword search misses semantic matches; naive vector search lacks precision on exact terms
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A knowledge base search using only vector similarity returns tangentially related documents. Users searching for exact product codes or proper nouns get semantically similar but factually wrong results. Keyword search alone misses paraphrased queries.

## Pattern / Solution
Implement hybrid search: combine BM25 keyword search and vector similarity search, then fuse results with Reciprocal Rank Fusion (RRF). Use query expansion (generate 3-5 query variants with LLM) to improve recall. Add a reranking step (Cohere Rerank, cross-encoder) to improve precision after retrieval.

```
query -> [BM25 results] + [vector search results]
      -> RRF merge
      -> cross-encoder rerank top-20
      -> return top-5
```

## Gotchas
- RRF parameter k=60 works well as default but should be tuned on your specific corpus
- Query expansion increases latency and cost — only apply when recall is the priority
- Exact-match fields (IDs, SKUs, serial numbers) should bypass vector search entirely

## Related
- rag-hybrid-search
- rag-reranking
- semantic-search-implementation
- semantic-caching-patterns
