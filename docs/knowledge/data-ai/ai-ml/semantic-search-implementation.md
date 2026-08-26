# semantic-search-implementation

**Issue:** Building end-to-end semantic search over a document corpus
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Keyword search misses semantically relevant documents; users expect Google-like search quality.

## Pattern / Solution
```python
class SemanticSearch:
    def __init__(self, embedder, vector_store):
        self.embedder = embedder
        self.store = vector_store

    async def search(self, query: str, top_k: int = 10, filters: dict = None) -> list[dict]:
        query_vec = await self.embedder.embed(query)
        results = await self.store.query(vector=query_vec, top_k=top_k*2, filter=filters)
        # Rerank
        reranked = reranker.rerank(query, [r["text"] for r in results], top_n=top_k)
        return [results[r.index] for r in reranked.results]
```

## Gotchas
- Query expansion (add synonyms/rewrites) improves recall by 15-30%
- Store both sparse and dense representations for hybrid search
- Relevance threshold filtering improves precision but can hide valid results

## Related
- `rag-vector-search.md`
- `rag-hybrid-search.md`
- `similarity-threshold-tuning.md`
