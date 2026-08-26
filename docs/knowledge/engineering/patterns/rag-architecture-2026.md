# rag-architecture-2026

**Issue:** RAG architecture — vector DB, embeddings, chunking
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a RAG. The answers are wrong. Sometimes
the LLM hallucinates. Sometimes the source is
outdated. Sometimes the recall is bad. You wish you
had a real RAG architecture.

## Root cause
**RAG is more than a vector DB.** Use 4 areas.

**Source:** Dcrayons + ini8 Labs 2026.

## The "RAG" concept

Retrieval-Augmented Generation:
- **Ingestion:** Chunk + embed + store
- **Query:** Embed + retrieve + inject
- **Generation:** LLM uses context

The RAG is the architecture.

## The "4 areas" pattern

For RAG:
1. **Vector DB choice:** pgvector / Pinecone / Weaviate
2. **Embedding pipeline:** Model + refresh
3. **Chunking + reranking:** Strategy matters
4. **Eval suite:** Make it measurable

The 4 are the focus.

## The "vector DB choice" pattern

For selection:
- **< 5M vectors:** pgvector (default)
- **5-50M:** pgvector + pgvectorscale, Qdrant, Weaviate
- **> 50M:** Pinecone, Milvus, Weaviate
- **< 100ms p95:** Pinecone, Weaviate
- **Postgres native:** pgvector

The choice is per scale.

## The "pgvector" pattern

For pgvector:
- **Type:** Postgres extension
- **Scale:** Up to 50M vectors
- **Cost:** Free (infra only)
- **Advantage:** SQL joins
- **Watch out:** HNSW tuning complex at scale

The pgvector is OSS native.

## The "Pinecone" pattern

For Pinecone:
- **Type:** Managed SaaS
- **Scale:** Billions
- **Cost:** Per-pod
- **Latency:** 10-25ms
- **Watch out:** Vendor lock-in

The Pinecone is managed.

## The "Weaviate" pattern

For Weaviate:
- **Type:** OSS / Cloud
- **Strength:** Native hybrid (BM25 + vector)
- **ML modules:** Built-in
- **Recall:** +15-30% over pure vector

The Weaviate is hybrid.

## The "Qdrant" pattern

For Qdrant:
- **Type:** OSS / Cloud
- **Language:** Rust
- **Performance:** Fast
- **Use:** Performance-critical

The Qdrant is fast.

## The "comparison" pattern

| Dim | pgvector | Pinecone | Weaviate | Qdrant |
|---|---|---|---|---|
| Scale | ~50M | Billions | 100M+ | 100M+ |
| Hybrid | Configure | Limited | Native | Supported |
| Ops | Low (PG) | Zero | Medium | Medium |
| Cost (<5M) | Free | High | Low (self) | Low |
| Lock-in | None | High | Low | None |
| SQL joins | Yes | No | No | No |

The choice is per need.

## The "embedding model" pattern

For choice:
- **OpenAI text-embedding-3-large:** 3072 dim, default
- **Voyage AI voyage-3:** 1024 dim, cheaper
- **Cohere embed-english-v3 / multilingual:** Multilingual
- **BGE / Nomic:** Open source

The model is per need.

## The "chunking" pattern

For strategy:
- **Fixed-size:** 500 tokens + 50 overlap (baseline)
- **Semantic:** Split at paragraph/section
- **Recursive:** Highest structure first
- **PDF:** Layout-aware (Unstructured, LlamaParse)
- **HTML:** Structure-aware (heading hierarchy)
- **Slack:** Conversation-aware
- **Markdown:** Heading-based

The strategy is per source.

## The "parent-child chunking" pattern

For better:
- **Small chunks (256-512):** For retrieval precision
- **Large parent (1024+):** For LLM context
- **Approach:** Retrieve small, inject parent

The pattern is current best practice.

## The "content-hash refresh" pattern

For sync:
- **Per-chunk hash:** Content hash
- **Compare:** Live vs index hash
- **Re-embed:** Only changed
- **Avoid:** Full re-embed on edit

The refresh is selective.

## The "PII filtering" pattern

For ingestion:
- **PII detect:** Presidio + custom
- **Action:** Redact / tag / drop
- **Compliance:** GDPR + DPDP + sectoral
- **Layer:** Before embedding

The PII is filtered.

## The "metadata design" pattern

For metadata:
- **Source doc ID**
- **Source URL**
- **Last modified**
- **Author**
- **Access tier**
- **Language**
- **Content type**

The metadata is rich.

## The "filter ordering" pattern

For query:
- **Filter before:** "tenant X only" (per-tenant)
- **Filter after:** "recent docs" (lift recency)
- **Decision:** At index design

The filter is by design.

## The "reranking" pattern

For 3 stages:
1. **Vector search:** top-K = 20-100
2. **Reranker:** top-K (Cohere, BGE, Voyage)
3. **LLM context:** top-N = 5-15

The rerank is the 2nd stage.

## The "reranker benefit" pattern

For accuracy:
- **Bi-encoder:** Fast, less accurate
- **Cross-encoder:** Slower, more accurate
- **Use:** On top-K (manageable)
- **Impact:** +10-20% recall

The cross-encoder wins.

## The "eval suite" pattern

For tests:
- **Held-out set:** 50-200 questions
- **Per question:** Expected answer + sources
- **Metrics:**
  - Retrieval recall
  - Answer correctness
  - Faithfulness
  - Citation accuracy
  - Latency p50/p95
- **Regression:** Every change

The eval is the gate.

## The "regression suite" pattern

For CI:
- **Run on:** Every change
- **Block:** On regression
- **Track:** Embedding model, chunking, reranker, LLM
- **Compare:** To baseline

The regression is automated.

## The "production monitoring" pattern

For live:
- **Sample daily:** Real queries
- **Auto-graded:** LLM-as-judge
- **Human review:** Weekly sample
- **Alert:** On regression

The monitoring is continuous.

## The "cost monitoring" pattern

For cost:
- **Per query:** Embed + retrieve + LLM
- **Per month:** Budget
- **Embedding regen:** Tracked separately
- **Alert:** On overrun

The cost is tracked.

## The "latency budget" pattern

For latency:
- **Embed:** 50ms
- **Retrieve:** 50-100ms
- **Rerank:** 100-200ms
- **LLM:** 500-2000ms
- **Total:** < 3s for chat

The budget is per stage.

## The "12-step rollout" pattern

For phases:
1. Vector DB selected
2. Embedding model chosen
3. Source-type-routed chunking
4. Content-hash refresh
5. PII filter + metadata tags
6. Hybrid search tuned
7. Reranker layer
8. Eval suite (50-200 questions)
9. Production monitoring
10. Cost monitoring + budget
11. Latency dashboards
12. Compliance audit

The rollout is staged.

## The "abstract embedding model" pattern

For migration:
- **Day 1:** Abstract from DB client
- **Why:** Re-embedding touches 15 places
- **Version record:** Which model generated which
- **Migration:** Re-embed on change

The abstraction is upfront.

## The "no chunking strategy" anti-pattern

For no strategy:
- **Issue:** Random chunks, bad recall
- **Fix:** Per source-type chunking

The strategy is per source.

## The "no reranking" anti-pattern

For no rerank:
- **Issue:** Vector-only, low accuracy
- **Fix:** Cross-encoder rerank

The rerank is required.

## The "no eval" anti-pattern

For no eval:
- **Issue:** "It kind of works"
- **Fix:** 50-200 question suite

The eval is required.

## The "no PII filter" anti-pattern

For no PII:
- **Issue:** Compliance violation
- **Fix:** Presidio + rules

The filter is required.

## The "no refresh" anti-pattern

For no refresh:
- **Issue:** Outdated answers
- **Fix:** Content-hash based

The refresh is required.

## The "RAG checklist" pattern

For checklist:
- [ ] Vector DB sized
- [ ] Embedding model chosen
- [ ] Chunking per source
- [ ] Content-hash refresh
- [ ] PII filter
- [ ] Metadata design
- [ ] Hybrid search
- [ ] Reranker
- [ ] Eval suite 50-200
- [ ] Production monitoring
- [ ] Cost + budget
- [ ] Latency dashboard
- [ ] Compliance

The checklist is 13.

## Verification
- **Test:** Recall > 0.8
- **Test:** Faithfulness > 0.9
- **Test:** Latency < 3s
- **Test:** No PII in results
- **Audit:** Quarterly

## Gotchas
- **The "no chunking" anti-pattern.** Per source.
- **The "no reranking" anti-pattern.** Add cross-encoder.
- **The "no eval" anti-pattern.** Suite required.

## Related
- `patterns/data-mesh-vs-fabric.md`
- `patterns/feature-store-comparison.md`
- `patterns/ai-ml-detail.md`
- `infra/postgresql-17-18-best-practices.md`
- Dcrayons: https://dcrayons.app/insights/enterprise-rag-architecture-vector-db-embedding-pipeline
- API Scout: https://apiscout.dev/blog/rag-pipeline-pinecone-vs-weaviate-vs-pgvector-2026
- ini8 Labs: https://ini8labs.tech/blog/vector-databases-rag-enterprise-guide-2026
