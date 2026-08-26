# RAG Chunking Strategies and Embedding Models — Production Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your RAG pipeline returns irrelevant context to the LLM. Users ask
specific questions about a 200-page technical manual and get answers
from the wrong section. Your chunks split tables in half, separate
headings from their content, and slice code blocks mid-function. The
LLM hallucinates because the retrieved chunks lack the context needed
to answer correctly. You tried increasing the number of retrieved
chunks from 3 to 10, but now the LLM gets confused by contradictory
information from unrelated sections.

## Context

RAG (Retrieval-Augmented Generation) systems split documents into
chunks, embed them into vectors, and retrieve relevant chunks at query
time to ground LLM responses. In 2026, the field has matured around
7 main chunking strategies and a clear hierarchy of embedding models.
Getting chunking and embedding right is the single biggest lever for
RAG quality — poor chunking accounts for the majority of the gap
between "works in a notebook" and "trusted in production." The
recommended starting point is 512 tokens with recursive splitting and
10-20% overlap.

## Chunking strategies

```
Strategy              Recall    Speed     Best for
─────────────────────────────────────────────────────
Fixed-size            50-65%    Fastest   Quick prototypes only
Recursive character   ~69%     Fast      Default for most RAG systems
Sliding window        65-75%    Fast      Preserving cross-boundary context
Semantic chunking     87-92%    14x slow  When retrieval precision is bottleneck
Hierarchical/late     75-85%    Moderate  Documents with cross-references
Proposition           85-90%    Slow      High-recall requirements
Document-structure    70-80%    Moderate  PDFs, HTML with clear structure
```

```python
# Recursive character splitting (recommended default)
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=64,        # ~12% overlap
    separators=["\n\n", "\n", ". ", " ", ""],
    length_function=len,
)
chunks = splitter.split_text(document_text)

# Semantic chunking (when precision matters)
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings

chunker = SemanticChunker(
    OpenAIEmbeddings(),
    breakpoint_threshold_type="percentile",
    breakpoint_threshold_amount=95,
)
chunks = chunker.split_text(document_text)
```

## Embedding models (2026)

```
Model                          Type         Strengths
──────────────────────────────────────────────────────────
text-embedding-3-large         Commercial   Best overall balance, Matryoshka dims
text-embedding-3-small         Commercial   Cost-effective high-volume
Cohere embed-english-v3.0      Commercial   100+ languages, asymmetric embedding
BGE-M3                         Open source  Multilingual workhorse, self-hosted
Qwen3-Embedding-0.6B           Open source  Best quality-per-GPU-dollar

Asymmetric embedding (Cohere):
  Embed queries with input_type="search_query"
  Embed documents with input_type="search_document"
  → 5-10% retrieval improvement over symmetric

Matryoshka embeddings (OpenAI):
  text-embedding-3-large supports variable dimensions
  → 3072 dims (full), 1536 dims (~1% quality loss), 256 dims (fast)
  → Reduce storage and search cost without re-embedding
```

## Vector search tuning (HNSW)

```
Parameter         Controls                  Typical range
─────────────────────────────────────────────────────────
M                 Max connections/node       16-64
efConstruction    Build-time candidates      100-400
efSearch          Query-time candidates      50-500

Tuning guide:
  → Start with M=16, efConstruction=200, efSearch=100
  → If recall < 0.95: increase efSearch first (cheapest knob)
  → If recall plateaus: rebuild index with higher M and efConstruction
  → For RAG, target recall >= 0.95 (reranker compensates near-misses)

Hybrid search (vector + BM25):
  → Embeddings prioritize semantic meaning over exact tokens
  → Part IDs, SKUs, policy codes need keyword/BM25 matching
  → Use reciprocal rank fusion (RRF) to combine results
```

## Anti-patterns

- **Fixed-size chunking without structure awareness** — the most
  common beginner mistake. Ignoring document layout (tables, headers,
  lists) produces noise no downstream tuning can recover.
- **Vector-only retrieval** — embeddings miss exact identifiers
  (part numbers, policy codes, error codes). Use hybrid search
  combining vector similarity with BM25 keyword matching.
- **Over-engineering early** — jumping to Graph RAG or agentic RAG
  before basic recursive chunking is tuned introduces extreme
  latency, API costs, and failure modes. Get the basics right first.
- **Recomputing embeddings on every run** — store embeddings once
  and reuse them. Recomputing wastes time and money at scale.

## Gotchas

- **Chunk size vs context window** — larger chunks preserve more
  context but reduce the number of chunks you can fit in the LLM
  context window. Balance chunk size against the number of chunks
  retrieved and the model's context limit.
- **Embedding model switching** — changing embedding models requires
  re-embedding your entire corpus. Plan for this cost when evaluating
  models. Never mix embeddings from different models in the same index.
- **Semantic chunking latency** — semantic chunking is ~14x slower
  than token-based splitting because it requires embedding each
  potential chunk boundary. Only use when retrieval precision is the
  measured bottleneck.
- **Observability gaps** — track Hit Rate and Mean Reciprocal Rank.
  If the right document lands at position #10, the reranker might
  miss it. Measure retrieval quality separately from generation quality.

## Verification

- Chunking strategy preserves document structure (tables, code, lists).
- Chunk size is tuned (default 512 tokens, 10-20% overlap).
- Embedding model is evaluated on domain-specific queries.
- Hybrid search is enabled for identifier-heavy content.
- Retrieval recall exceeds 0.95 on evaluation dataset.
- HNSW parameters are tuned for recall/latency tradeoff.

## Related

- `documentation/categories/ai-ml/rag-retrieval-augmented-generation.md`
- `documentation/categories/database/vector-database-comparison-2026.md`
- `documentation/categories/ai-ml/model-distillation-knowledge-transfer.md`

## Source URLs (verified 2026-08-16)

- RAG Chunking Strategies 2026: 8 Methods Compared with Code Examples — https://denser.ai/blog/rag-chunking-strategies/
- Best Chunking Strategies for RAG in 2026 — https://www.firecrawl.dev/blog/best-chunking-strategies-rag
- Best Embedding Models for RAG in 2026 — https://www.stackai.com/insights/best-embedding-models-for-rag-in-2026-a-comparison-guide
- 10 Common RAG Mistakes We Keep Seeing in Production — https://towardsdatascience.com/10-common-rag-mistakes-we-keep-seeing-in-production/
