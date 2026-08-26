# semantic-caching-patterns

**Issue:** Repeated or semantically similar LLM queries waste cost and latency without caching
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A customer service chatbot receives thousands of queries per day, many semantically identical ("how do I reset my password?" vs "forgot password help"). Each query incurs full LLM cost and 1-3 s latency. Exact-match caching misses the obvious duplicates.

## Pattern / Solution
Embed incoming queries and compare against a cache of prior query embeddings. If cosine similarity exceeds a threshold (typically 0.92-0.95), return the cached response. Use a vector store (Redis with vector search, Qdrant) for fast nearest-neighbor lookup. Set TTL on cache entries aligned with your content freshness requirements.

```python
def cached_llm_call(query: str, threshold=0.93):
    query_emb = embed(query)
    cached = cache.search(query_emb, top_k=1)
    if cached and cached[0].score >= threshold:
        return cached[0].response
    response = llm.complete(query)
    cache.store(query_emb, response)
    return response
```

## Gotchas
- Too-low thresholds return wrong cached answers; too-high thresholds miss obvious duplicates — calibrate on real traffic
- User-specific queries (account balance, order status) must never be cached and shared across users
- Cache invalidation: update embeddings and responses when underlying data changes

## Related
- ai-gateway-caching
- semantic-search-implementation
- llm-cost-optimization
