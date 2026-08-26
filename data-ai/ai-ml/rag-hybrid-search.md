# rag-hybrid-search

**Issue:** Combining vector search with BM25 keyword search for better recall
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pure vector search misses exact keyword matches; pure BM25 misses semantic relevance.

## Pattern / Solution
```python
# Reciprocal Rank Fusion
def rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))

vector_results = vector_search(query, top_k=20)
bm25_results = bm25_search(query, top_k=20)
fused = rrf([vector_results, bm25_results])
```
Weaviate and Qdrant have native hybrid search with configurable alpha (0=BM25, 1=vector).

## Gotchas
- Alpha=0.5 is a reasonable default; tune per domain
- BM25 requires a separate inverted index (Elasticsearch, Weaviate BM25)
- Hybrid search adds latency — only use when recall matters more than speed

## Related
- `rag-vector-search.md`
- `rag-reranking.md`
