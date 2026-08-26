# metadata-filtering-vectors

**Issue:** Filtering vector search results by metadata to narrow result scope
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without metadata pre-filtering, ANN search returns results from irrelevant document sets.

## Pattern / Solution
```python
# Pinecone metadata filter
results = index.query(
    vector=query_vec,
    top_k=5,
    filter={
        "department": {"$eq": "engineering"},
        "date": {"$gte": "2025-01-01"},
        "doc_type": {"$in": ["guide", "runbook"]},
    },
    include_metadata=True,
)

# pgvector metadata filter
SELECT * FROM docs
WHERE metadata @> '{"department": "engineering"}'
  AND (embedding <=> $1) < 0.3
ORDER BY embedding <=> $1 LIMIT 5;
```

## Gotchas
- Heavy metadata filtering reduces ANN index efficiency — can fall back to brute force
- Index metadata fields used in filters at index creation (Pinecone requires this)
- Combine metadata filtering with tenant isolation for multi-tenant RAG

## Related
- `vector-database-pinecone.md`
- `rag-vector-search.md`
