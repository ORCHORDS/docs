# rag-reranking

**Issue:** Re-scoring retrieved chunks to improve precision before generation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Initial retrieval returns 20-100 candidates; a reranker selects the best 3-5 for the LLM.

## Pattern / Solution
```python
from cohere import Client

co = Client(api_key)
results = co.rerank(
    query=user_query,
    documents=[chunk.text for chunk in retrieved_chunks],
    model="rerank-english-v3.0",
    top_n=5,
)
top_chunks = [retrieved_chunks[r.index] for r in results.results]

# Local reranker (no API cost)
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
scores = reranker.predict([(query, doc) for doc in docs])
top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
```

## Gotchas
- Reranking adds 100-300ms latency; run in parallel with other ops where possible
- CrossEncoder quality > bi-encoder for reranking but is slower
- Don't rerank on metadata-only results — need text content

## Related
- `rag-hybrid-search.md`
- `rag-context-compression.md`
