# rag-chunking-2026

- **Issue**: "Just split by paragraphs" loses 30%+ of retrievable facts at chunk boundaries. The 2026 production default is a hybrid: **contextual retrieval** (LLM-written preamble) + **late chunking** (long-context embedder) + **hybrid search** (BM25 + vector) + **reranking**. The cost varies 10×; the lift is 35–67% in retrieval-failure reduction.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/patterns/rag-architecture-2026.md`.

## Symptom

- The retriever returns chunks that look topically relevant but the answer is wrong. The missing context was in a different section that the chunk no longer references.
- A pronoun ("the company", "its") points to a subject in a chunk that was split off 800 tokens earlier. The embedding has lost the referent.
- A table row is split mid-row; the chunk is a fragment.
- A code snippet is split mid-function; the snippet is incomplete.
- You switched from `text-embedding-3-small` to `text-embedding-3-large` and recall barely moved. Chunking is the bottleneck, not the model.

## Root cause

Three things go wrong at chunk boundaries: (1) the **chunk loses global context** (pronouns, table headers, code dependencies), (2) the **embedding model sees only the chunk**, not the document, so it embeds the local meaning, and (3) the **retriever ranks by vector similarity alone**, which underweights lexical matches that BM25 would catch.

## The eight strategies (2026 ranking)

| # | Strategy | Complexity | Cost vs fixed | Best for |
|---|---|---|---|---|
| 1 | **Recursive (LangChain RecursiveCharacterTextSplitter)** | Low | 1× | General default; mixed prose |
| 2 | **Fixed-size** | Low | 1× | Uniform structureless text |
| 3 | **Sentence-based** | Low | ~1× | Q&A; matches semantic up to ~5K tok |
| 4 | **Semantic** | Medium | ~14× slower (Chonkie benchmark: 0.33 MB/s vs 4.82 MB/s) | Topic-shifting documents |
| 5 | **Hierarchical (small-to-big / parent-child)** | Medium | Higher | Long structured docs; auto-merging retrieval |
| 6 | **Late chunking** | Medium | Higher (single embedder pass on full doc) | Long docs with cross-references |
| 7 | **Contextual Retrieval** | High | ~$1.02 / M doc tokens | High-value retrieval accuracy |
| 8 | **Agentic / LLM-based** | High | 10–50× | High-value one-time corpora |

## The 2026 default: recursive 512-token, 10–20% overlap

Use `RecursiveCharacterTextSplitter.from_tiktoken_encoder()` for token-accurate cuts. **A 512–1024 token range covers most workloads**; 512 is the most-cited default. The Firecrawl/Vecta 2026 benchmark ranked recursive 512-token first at 69% accuracy across 7 strategies and 50 academic papers (treat as directional). LlamaIndex's earlier study found 1024 tokens near peak faithfulness.

**Skip overlap as a default.** Add it only if a boundary-sensitive domain proves it helps. (Earlier "10–20% overlap" guidance is being replaced by token-accurate cuts and overlap-when-needed.)

## Semantic chunking

Embeds every sentence, computes pairwise cosine similarity between consecutive sentences, and splits where similarity drops below a threshold. Wins on prose; loses to document-aware splitters for code and Markdown. **Penalize with a minimum chunk size floor** (200–400 tokens) and merge fragments up to that — semantic chunking can produce 43-token fragments that score well on recall but hurt end-to-end accuracy.

## Late chunking (Jina AI, 2024; arXiv 2409.04701)

Inverts the order: embed the entire document with a long-context embedding model (8K+ tokens), then apply chunk boundaries and mean-pool per-chunk token embeddings. Each chunk's vector carries the document's full context for free. BEIR gains: SciFact 64.20% → 66.10% nDCG@10; NFCorpus 23.46% → 29.98%. **Effectiveness grows with document length**, which is exactly where naive chunking hurts most.

Requirements: long-context embedder. Available on jina-embeddings-v3, Voyage 3 Large, Cohere Embed 4, nomic-embed-text-v1.5.

## Contextual Retrieval (Anthropic, 2024)

For each chunk, an LLM (Claude Haiku in the original write-up) writes a 50–100 token contextual description that situates the chunk in the document ("This is from Q3 2024 10-Q; the 3% figure is quarter-over-quarter revenue"). The preamble is prepended to the chunk before embedding.

- **Contextual Embeddings alone**: 35% reduction in top-20 retrieval failures (5.7% → 3.7%).
- **Contextual Embeddings + BM25 (Contextual BM25)**: 49% reduction (5.7% → 2.9%).
- **Contextual Embeddings + Contextual BM25 + Reranker**: 67% reduction (5.7% → 1.9%).

**Preprocessing cost: ~$1.02 per million document tokens** with prompt caching (Claude). The cache is loaded once per document and re-used for every chunk in that document.

## Hierarchical (parent-child / small-to-big)

Store two granularities. Small **child** chunks (a sentence or two) are embedded and indexed. Large **parent** chunks (a paragraph or section) are stored alongside. At retrieval, search over child embeddings; return the parent chunk to the LLM. Production default in LangChain (`ParentDocumentRetriever`) and LlamaIndex. Best precision-recall balance for production.

## The decision matrix

1. **Start with recursive 512-token splits, token-accurate.** Cheap, robust baseline.
2. **Measure retrieval quality** on a representative query set (your real users' queries, not synthetic).
3. **If Markdown/HTML** — use header-based splitting first, then recursive within sections.
4. **If paginated PDFs** — try page-level chunking.
5. **If retrieval recall is low** — try semantic chunking with a 200–400 token floor.
6. **If you need both recall and large LLM context** — parent-child.
7. **If documents have heavy cross-references** (legal, scientific, multi-section reports) — late chunking.
8. **If retrieval metrics justify the cost** and you have bounded volume — Contextual Retrieval with BM25 + reranker. This is the high-water mark.
9. **If you have high-value one-time corpora** — LLM-based / agentic chunking.

## Match chunk size to query type

| Query type | Optimal size | Recommended strategy |
|---|---|---|
| Factoid lookups | 64–256 tokens | Sentence-based or small recursive |
| QA over technical docs | 200–400 tokens | Recursive, 512 default |
| Analytical / narrative | 800–1200 tokens | Hierarchical or late chunking |
| Code search | 50–150 tokens | Language-aware splitter |
| Summarization | 800–1200+ tokens | Late chunking or full-doc |

If your traffic is mixed, segment by query class rather than forcing one size on everything.

## Verification

- **RAGAS metrics on a golden dataset** of 100–200 question-answer pairs:
  - **Faithfulness ≥ 0.75** (grounding in retrieved context)
  - **Answer relevancy ≥ 0.80**
  - **Context precision ≥ 0.70**
  - **Context recall ≥ 0.80**
- **Cluster failures by pattern.** "Chunk too small" is a different fix from "wrong semantic boundary."
- **Track chunk size distribution** after splitting. If p50 ≠ your target, your splitter is misbehaving.
- **A/B each strategy on the same golden set.** Pick by your own numbers, not by benchmarks.
- **Cost per document indexed**, including any LLM preamble generation.
- **Recall@K vs nDCG@K** for the retriever; reranking helps nDCG more than recall.

## Gotchas

- **Fixed-size chunking is the wrong default in 2026.** It cuts mid-sentence, breaks tables, and strips context.
- **Semantic chunking can produce 43-token fragments.** Apply a minimum size floor.
- **Late chunking is bounded by the embedder's context window.** Past 8K tokens (Jina v2), cross-pass chunks lose shared context.
- **Contextual Retrieval cost is real** even with prompt caching. Budget for the one-time pass.
- **Pair chunking with hybrid search + reranking.** Chunking controls what is *findable*; retrieval controls what is *found*. Without hybrid + rerank, chunking alone gives partial wins.
- **Don't paste your code into a sentence splitter.** Use a language-aware splitter for code; recurse only within functions.
- **Recursion within Markdown headers** preserves semantic structure. Plain character splitting breaks it.
- **The 1.9% top-20 failure rate** (Anthropic with full stack) is achievable; 5.7% (baseline) is the cost of skipping the stack.
- **Semantic chunking's 14× slowdown is real.** Apply it only where the metrics justify it.

## Related

- `documentation/docs/policies/patterns/rag-architecture-2026.md` — the broader RAG topology
- `documentation/docs/policies/cloudflare/ai-search-2026.md` — managed RAG on Cloudflare
- `documentation/docs/policies/cloudflare/vectorize-2026.md` — the vector store
- `documentation/docs/policies/patterns/agent-eval-2026.md` — how to measure retrieval quality
- `documentation/docs/policies/patterns/prompt-caching-2026.md` — caching makes Contextual Retrieval affordable

## Source URLs (verified 2026-08-09)

- "RAG Chunking Strategies: A 2026 Retrieval Playbook" (digitalapplied) — https://www.digitalapplied.com/blog/rag-chunking-strategies-2026-retrieval-quality-playbook
- "RAG Chunking Strategies Guide (2026)" (aiworkflowlab) — https://aiworkflowlab.dev/article/rag-chunking-strategies-late-contextual-semantic-2026
- "Late Chunking vs Contextual Retrieval" (dreaming.press) — https://dreaming.press/posts/2026-06-23-late-chunking-vs-contextual-retrieval.html
- "The RAG Cookbook 2026: Late chunking (Jina)" — https://fareedkhan-dev.github.io/rag-cookbook-2026/recipes/02-chunking-and-indexing/late-chunking-jina/
- "Advanced RAG Chunking 2026" (futureagi) — https://futureagi.com/blog/advanced-chunking-techniques-for-rag/
- "Best Chunking Strategies for RAG (and LLMs) in 2026" (Firecrawl) — https://www.firecrawl.dev/blog/best-chunking-strategies-rag
- "RAG Chunking Strategies: The 2026 Benchmark Guide" (Premai) — https://www.premai.io/blog/rag-chunking-strategies-the-2026-benchmark-guide/
- Late Chunking paper (arXiv 2409.04701) — https://arxiv.org/abs/2409.04701
- Anthropic Contextual Retrieval — https://www.anthropic.com/news/contextual-retrieval
- Jina AI Late Chunking announcement — https://jina.ai/news/late-chunking-in-long-context-embedding-models/
