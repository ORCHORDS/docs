# Vector Database Comparison 2026

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You are building a RAG pipeline or AI agent and need to store and query vector
embeddings. pgvector works for your prototype, but you are unsure whether to
stay with it or migrate to a purpose-built vector database as you scale beyond
millions of vectors.

## Context

Vector databases store high-dimensional embeddings and support approximate
nearest neighbor (ANN) search. The 2026 landscape splits into two camps:
purpose-built vector databases (Pinecone, Qdrant, Weaviate, Milvus, Chroma)
and vector extensions on existing databases (pgvector, SQLite-vec). The right
choice depends on scale, operational preferences, and query patterns.

## Comparison

| Database | Type | Scale sweet spot | Hybrid search | License | Hosting |
|---|---|---|---|---|---|
| pgvector | Postgres extension | < 100M vectors | BM25 via pg_search | PostgreSQL | Self-hosted / managed PG |
| Pinecone | Managed SaaS | Any (serverless) | Built-in (2026) | Proprietary | Fully managed |
| Qdrant | Dedicated engine | 10M–1B+ vectors | Sparse + dense native | Apache 2.0 | Self-hosted / cloud |
| Weaviate | Dedicated engine | 10M–500M vectors | BM25 + vector + filters | BSD-3 | Self-hosted / cloud |
| Milvus | Dedicated engine | 1B+ vectors | Sparse + dense | Apache 2.0 | Self-hosted / Zilliz cloud |
| Chroma | Embedded / server | < 10M vectors | Metadata filters | Apache 2.0 | Embedded / cloud |

## When to choose which

- **pgvector** — already on Postgres, < 100M vectors, want one database to
  manage. Iterative index scans (2026) improved filtered search. Default
  choice for most RAG workloads.
- **Pinecone** — zero-ops managed search at any scale. Built-in inference
  (embeddings + reranking). Best for teams without infra engineers.
- **Qdrant** — best open-source performance. Rust-based, ~10-25% faster than
  Weaviate/Milvus on common workloads. Native sparse vector (SPLADE) and
  ColBERT multi-vector support. Generous free tier.
- **Weaviate** — strongest hybrid search (vector + BM25 + metadata filters)
  with GraphQL API. Modular vectorizers built in. Best DX for hybrid queries.
- **Milvus** — billions of vectors at lower cost. GPU-accelerated indexing.
  Requires engineering resources to operate.
- **Chroma** — simplest DX for prototyping and small-scale embedding stores.
  Python-first, embeddable. Not for production scale beyond ~10M vectors.

## Performance benchmarks (2026, 10M vectors, 768 dimensions)

| Metric | pgvector | Qdrant | Weaviate | Milvus | Pinecone |
|---|---|---|---|---|---|
| p99 latency (ms) | ~25 | ~12 | ~16 | ~18 | ~15 |
| Recall@10 (HNSW) | 0.95 | 0.98 | 0.97 | 0.97 | 0.98 |
| Index build time | Slow (hours) | Fast | Medium | Fast (GPU) | Managed |
| Filtered search | Iterative scan | Native | Native | Native | Native |

## Anti-patterns

- **Premature migration from pgvector** — if your dataset is under 10M
  vectors and you are already on Postgres, the operational cost of a second
  database is rarely worth the latency improvement.
- **Ignoring hybrid search** — pure vector similarity misses keyword matches.
  Combine BM25 + vector for production RAG.
- **Storing raw text in the vector DB** — vector databases are not document
  stores. Store text in your primary DB; store embeddings + chunk IDs in the
  vector DB.
- **One giant collection** — partition by tenant, document type, or time
  window for better query performance and access control.

## Gotchas

- **Embedding model lock-in** — changing your embedding model invalidates all
  stored vectors. Plan for re-indexing.
- **Dimensionality affects everything** — higher dimensions (1536, 3072)
  increase storage, memory, and query cost. Use matryoshka embeddings or
  quantization to reduce dimensions.
- **pgvector HNSW build is CPU-bound and slow** — plan maintenance windows
  for index rebuilds on large tables.
- **Pinecone vendor lock-in** — no self-hosted option, no data export API for
  raw vectors (export metadata only). Plan your exit strategy.
- **Milvus operational complexity** — requires etcd, MinIO/S3, and multiple
  services. Use Milvus Lite for development.

## Verification

- Benchmark with your actual embeddings, not synthetic data.
- Test recall at your target latency SLO, not just recall@k in isolation.
- Verify filtered search performance (metadata filters + vector similarity).
- Load test concurrent query throughput at your expected QPS.

## Related

- `documentation/categories/database/pgvector-vector-search.md`
- `documentation/categories/ai-ml/vector-embeddings-model-selection.md`
- `documentation/categories/ai-ml/vector-index-ann-algorithms.md`
- `documentation/categories/patterns/agent-context-engineering-2026.md`

## Source URLs (verified 2026-08-16)

- Best vector databases 2026 comparison — https://www.firecrawl.dev/blog/best-vector-databases
- Vector databases for AI agents 2026 — https://www.digitalapplied.com/blog/vector-databases-for-ai-agents-pinecone-qdrant-2026
- Top 15 vector databases 2026 — https://medium.com/@pratik-rupareliya/top-15-vector-databases-in-2026-a-production-decision-guide-from-100-enterprise-deployments-dd58a04f51a5
- Best vector databases 2026 — https://encore.dev/articles/best-vector-databases
- Qdrant vs Pinecone vs Weaviate vs Milvus — https://dev.to/darshit_01/the-best-vector-database-in-2026-qdrant-vs-pinecone-vs-weaviate-vs-milvus-vs-pgvector-3147
