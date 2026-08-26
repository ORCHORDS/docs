# pgvector: Vector Search in PostgreSQL

## Overview

pgvector is an extension for PostgreSQL that enables vector similarity search, making it possible to perform efficient similarity searches on high-dimensional data. This capability is essential for modern AI applications including recommendation systems, content-based search, and Retrieval-Augmented Generation (RAG) systems.

## HNSW vs IVFFlat Indexes

The two primary indexing methods in pgvector offer different trade-offs for vector search performance:

**HNSW (Hierarchical Navigable Small World)** provides superior query performance with O(log n) complexity but requires more memory. It's ideal for applications where fast retrieval is critical.

```sql
-- Create HNSW index
CREATE INDEX idx_vector_hnsw ON items USING hnsw (embedding vector_l2_ops);
```

**IVFFlat (Inverted File with Flat Storage)** offers better insertion performance and lower memory usage but slower queries with O(n) complexity. It's suitable for batch processing scenarios.

```sql
-- Create IVFFlat index
CREATE INDEX idx_vector_ivf ON items USING ivfflat (embedding vector_l2_ops);
```

## Embedding Storage

pgvector supports various embedding formats through the `vector` data type. Embeddings are stored as fixed-size arrays of floating-point numbers, with dimensions typically ranging from 128 to 3072.

```sql
-- Create table with vector column
CREATE TABLE items (
    id SERIAL PRIMARY KEY,
    name TEXT,
    embedding VECTOR(1536) -- 1536-dimensional embeddings
);
```

## Distance Metrics

pgvector supports multiple distance metrics for similarity calculations:

**Cosine Distance**: Best for text embeddings where direction matters more than magnitude.

```sql
-- Cosine similarity search
SELECT id, name, 1 - (embedding <=> $1) AS similarity
FROM items
ORDER BY embedding <=> $1
LIMIT 10;
```

**L2 Distance**: Most common metric for general vector similarity, measuring Euclidean distance.

```sql
-- L2 distance search
SELECT id, name, embedding <-> $1 AS distance
FROM items
ORDER BY embedding <-> $1
LIMIT 10;
```

## Hybrid Search with tsvector

Combining vector and text search creates powerful hybrid systems:

```sql
-- Hybrid search combining vector and text
SELECT i.id, i.name,
       (i.embedding <=> $1) + (ts_rank(i.search_vector, to_tsquery($2)) * 0.1) AS combined_score
FROM items i
WHERE i.search_vector @@ to_tsquery($2)
ORDER BY combined_score
LIMIT 10;
```

## RAG Patterns

pgvector excels in Retrieval-Augmented Generation workflows:

```sql
-- RAG retrieval pattern
WITH embeddings AS (
    SELECT $1::VECTOR(1536) AS query_embedding
),
similar_items AS
