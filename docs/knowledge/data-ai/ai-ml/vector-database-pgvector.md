# vector-database-pgvector

**Issue:** Using pgvector extension for vector search in PostgreSQL
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams already using Postgres want to add vector search without a new service.

## Pattern / Solution
```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create table
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1536),
    metadata JSONB
);

-- HNSW index (better recall, slower build)
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops);

-- Query
SELECT id, content, 1 - (embedding <=> $1::vector) AS score
FROM documents
WHERE metadata->>'source' = 'blog'
ORDER BY score DESC LIMIT 5;
```

## Gotchas
- HNSW index must be built before data grows large; rebuilding is slow
- Use `halfvec` type to halve storage for embeddings >1k dims
- pgvector 0.7+ required for streaming HNSW builds

## Related
- `rag-vector-search.md`
- `vector-database-chroma.md`
