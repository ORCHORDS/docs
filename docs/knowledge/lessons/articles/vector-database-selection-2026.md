# vector-database-selection-2026

**Issue:** A team starts a RAG project. They pick Pinecone by default. Six months later, the bill is $15k/month, queries take 200ms p99, and they can't get a hybrid search to work right. They didn't pick by workload.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Vector database choice is workload-dependent, not provider-dependent. The 2026 default is pgvector for <5M vectors, Qdrant for 10-100M, Pinecone for zero-ops scale, Milvus for >1B. Picking wrong costs $50k-$500k/year.

## Root cause

5 different deployment shapes exist: pgvector (Postgres extension), Pinecone (managed SaaS), Qdrant (open-source dedicated), Weaviate (open-source + managed), Milvus (open-source + Zilliz managed). The 2026 default depends on 5 workload questions.

## The 5-question decision framework

| Question | Answer drives choice |
|---|---|
| 1. How many vectors at 12-month projection? | scale |
| 2. Self-hosted or managed? | ops capacity |
| 3. How important is hybrid search (BM25 + vector)? | retrieval quality |
| 4. Vendor independence / data residency? | compliance |
| 5. What's already running? | integration cost |

Apply in order. Question 1 typically shortlists to 1-2 options.

## The 5-shape comparison

| Shape | Self-host? | Open source? | Scale | Best for |
|---|---|---|---|---|
| pgvector | required (Postgres) | yes (Postgres) | <100M vectors | teams already on Postgres, transactional consistency |
| Pinecone | no (managed only) | no | billions | zero-ops, multi-tenant SaaS, fast 8-week ship |
| Qdrant | yes (Rust, Docker) | yes (Apache 2.0) | hundreds of millions | production RAG above 10M, hybrid search, payload filtering |
| Weaviate | yes | yes (BSD-3) | hundreds of millions | multi-modal, GraphQL, modules for embedding/reranking |
| Milvus | yes | yes (Apache 2.0) | 10B+ | extreme scale, GPU acceleration, dedicated platform team |

## The scale-based recommendation

The 2026 production RAG cost-realistic recommendation.

| Vectors | Recommendation | Why | Cost (5M vec, 100 QPS) |
|---|---|---|---|
| <2M | pgvector | zero new infra, transactional | $250-400/month (existing Postgres) |
| 1-10M | Qdrant Cloud or Pinecone Serverless | cost vs ops trade-off | Qdrant $350-600, Pinecone $500-900 |
| 10-100M | Qdrant Cloud | best price-performance | $2,400-3,000/month |
| 100M-1B | Weaviate Cloud or Qdrant | choice by feature need | $4,000-8,000/month |
| >1B | Milvus / Zilliz or Pinecone | extreme scale | $10k+/month |

The numbers are from the 2026 LeanOps production RAG audits and the 2026 learnersink analysis.

## The pgvector 2026 sweet spot

pgvector is the 2026 default for RAG under 10M vectors.

- 1536-dim embeddings, 10M vectors fit on a single db.r6g.xlarge
- p95 latency <60ms with HNSW indexes
- 90% of the performance of dedicated vector DBs
- Same Postgres: ACID, joins, transactions
- Free (you already have Postgres)

Move off pgvector when you hit one of three real ceilings:
- More than 10-20M vectors
- Sustained QPS above ~500
- A genuine need for advanced hybrid ranking that Postgres full-text-search cannot express

## The Qdrant sweet spot

Qdrant is the 2026 default for production RAG above 10M vectors.

- Rust core: memory-efficient, fast
- Native hybrid search (BM25 + dense)
- Payload filtering with rich query DSL
- Self-hostable (Docker, k8s) or Qdrant Cloud (managed)
- Apache 2.0 license
- Sub-5ms p50 latency at 1M vectors
- 5-15ms p50 at 10M vectors (float32)
- 10-25ms p50 at 100M vectors (with int8 quantization)

## The Pinecone trade-off

Pinecone is the 2026 default for "I need it in production in 8 weeks."

- Serverless GA, 10x price reduction for small workloads
- Zero ops, fully managed
- Strong multi-tenancy
- Cost grows non-linearly at very large scale
- Vendor lock-in (no self-host option)
- Serverless v3 has native hybrid search

Pinecone wins on time-to-market, loses on cost at scale and vendor lock-in.

## The 5 anti-patterns

1. **Picking Pinecone by default.** For <10M vectors, pgvector is cheaper and operationally simpler.
2. **Picking pgvector above 20M vectors.** Performance and operational complexity degrade.
3. **No hybrid search when domain demands it.** Pure vector search misses keyword-specific recall (product names, IDs, error codes). Use hybrid.
4. **No quantization at scale.** int8 quantization cuts memory 4x with <1% recall loss. Use at >50M vectors.
5. **Ignoring the team's ops capacity.** Self-hosted Qdrant is cheaper than Qdrant Cloud, but the platform engineering overhead makes total cost higher at small scale.

## The migration pattern

Most teams start with pgvector, then migrate as scale grows.

1. **Start with pgvector** (months 1-12). Zero new infra. Add pgvectorscale for >5M vectors.
2. **Move to Qdrant** (months 12-24). When you hit 10-20M vectors or need hybrid search beyond what pgvector offers.
3. **Move to Weaviate or Milvus** (year 2+). When you need multi-modal, advanced modules, or >100M vectors.

The migration cost is real (re-indexing, application changes). Plan for it, don't repeat work.

## The benchmark discipline

Before picking, run a 4-metric benchmark on your data.

| Metric | What it measures | Target |
|---|---|---|
| p50 latency | typical case | <50ms for interactive |
| p99 latency | worst case | <200ms for interactive |
| recall@10 | retrieval quality | >=0.95 (the production minimum) |
| Indexing throughput | bulk load | matches ingest rate |

A recall@10 below 0.95 is statistically guaranteed to miss relevant chunks. Don't ship below that.

## Verification

The tell that vector DB choice is right for the workload:

- The 5-question framework was applied; the choice is documented
- The scale is at the 12-month projection, not today
- A benchmark on real data showed p50/p99/recall@10 within target
- The cost at 12-month projection is within budget
- A migration path exists if scale changes

The tell it isn't:

- "Pinecone is the default" without workload analysis
- The cost is unexamined
- No benchmark was run
- The team is on Milvus for 1M vectors (overkill)
- The team is on pgvector for 100M vectors (under-powered)

## Gotchas

- **Quantization is essential at scale.** int8 or float16 cuts memory 2-4x with <1% recall loss. Don't ship at 100M without it.
- **Hybrid search matters more than you think.** For product catalogs, documentation, support tickets, hybrid (BM25 + vector) consistently beats pure vector by 5-15% recall@10.
- **Embedding model choice drives DB choice.** Larger embedding dimensions (3072 for text-embedding-3-large) require more memory; smaller (384 for all-MiniLM) fit more vectors per dollar.
- **Re-indexing is expensive.** Plan a maintenance window; offline re-indexing is faster than online.
- **The benchmark is the contract.** Don't pick based on blog posts. Benchmark on your data.

## Related

- `lessons/ai-rag-patterns-2026.md` — the system using the vector DB
- `lessons/llm-evaluation-frameworks-2026.md` — measuring retrieval quality
- `worktree/monorepo-pnpm-turborepo-2026.md` — deploying the choice at scale
- `deploy/` — production deployment patterns

## Source URLs (verified 2026-08-10)

- https://topreviewed.ai/blog/vector-database-comparison-2026-pinecone-vs-qdrant-vs-pgvector-vs-weaviate-at-scale
- https://encore.dev/articles/best-vector-databases
- https://www.pccvdi.com/insights/vector-databases-compared-2026
- https://www.learnersink.com/blog/vector-databases-comparison-2026
- https://myengineeringpath.dev/tools/vector-db-comparison/
- https://leanopstech.com/blog/pinecone-vs-qdrant-vs-weaviate-vs-pgvector-2026/
- https://github.com/pgvector/pgvector
- https://qdrant.tech/
- https://docs.pinecone.io/
- https://milvus.io/
