# vector-database-pinecone

**Issue:** Using Pinecone as a managed vector database for production RAG
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Self-hosted vector DBs add operational burden; Pinecone offers serverless managed ANN search.

## Pattern / Solution
```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="YOUR_KEY")
pc.create_index(name="rag-index", dimension=1536, metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"))
index = pc.Index("rag-index")

# Upsert
index.upsert(vectors=[{"id": "doc1", "values": embedding, "metadata": {"text": chunk, "source": url}}])

# Query
results = index.query(vector=query_vec, top_k=5, include_metadata=True)
```

## Gotchas
- Free tier has 100k vector limit — plan capacity early
- Metadata filtering runs before ANN search; define filter keys at index creation
- Serverless cold starts add ~200ms on first query after idle period

## Related
- `rag-vector-search.md`
- `embedding-generation-patterns.md`
