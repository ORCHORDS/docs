# rag-vector-search

**Issue:** Implementing efficient vector similarity search for RAG
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Brute-force vector search doesn't scale beyond tens of thousands of documents.

## Pattern / Solution
```python
# Pinecone ANN search
import pinecone
index = pinecone.Index("my-index")
results = index.query(vector=query_embedding, top_k=5, include_metadata=True)

# pgvector (Postgres)
# CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
from sqlalchemy import text
rows = db.execute(text(
    "SELECT id, content, 1 - (embedding <=> :vec) AS score FROM embeddings ORDER BY score DESC LIMIT 5"
), {"vec": str(query_vector)})
```

## Gotchas
- ANN indexes (HNSW, IVF) trade recall for speed — tune `ef_search`/`nprobe`
- Always filter by metadata before vector search when possible (reduces search space)
- Re-index when document count doubles from initial index build

## Related
- `rag-hybrid-search.md`
- `vector-database-pgvector.md`
