# graphrag-knowledge-graph-retrieval

**Issue:** Vector RAG retrieves fragments that look similar to the query, which fails on questions requiring synthesis across an entire corpus ("what are the main themes in these ten thousand support tickets") or multi-hop relationships ("which supplier of our tier-2 vendors missed certifications last quarter"). GraphRAG answers these by extracting entities and relationships into a knowledge graph, clustering entities into communities, and pre-computing community summaries that give the model a map of the whole corpus. The trade is brutal indexing cost: LLM-driven entity extraction over a large corpus costs as much as or more than the queries it serves, which is why Microsoft's 2024-2025 LazyGraphRAG work — deferring LLM summarization to query time and cutting indexing cost by roughly 99% while matching quality on many benchmarks — reshaped the production calculus. Choosing between vector RAG, full GraphRAG, and lazy variants is now a cost-and-query-pattern engineering decision, not a research fashion choice.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When graphs beat vectors

1. **Global sensemaking queries.** Questions about themes, summaries, or "the corpus as a whole" need breadth that top-k similarity search cannot provide. Community-level summaries — the core GraphRAG artifact — are built exactly for this and consistently beat vector RAG on global-question benchmarks.

2. **Multi-hop relational queries.** When the answer requires joining facts across documents (entity A connects to B connects to C), graph traversal finds paths that independent chunks cannot, because the relationships live between documents, not inside any single chunk.

3. **Domain ontology value.** Corpora with rich typed entities (people, companies, drugs, regulations) reward graph extraction because the structure is real in the domain. Prose-heavy, entity-poor corpora produce sparse, noisy graphs where the pipeline cost buys little.

4. **Not a replacement for vector RAG.** Most production systems ship hybrid: vector or full-text search for point lookup questions, graph layer for synthesis and relational questions, with a router deciding. Microsoft's own comparisons show vector RAG still wins on targeted detail lookups.

## Indexing pipeline and cost

1. **Extraction is the dominant cost.** Standard GraphRAG runs LLM entity-and-relationship extraction over every text chunk, then the Leiden algorithm builds community hierarchies, then LLMs summarize each community at multiple levels. For large corpora this is thousands to millions of LLM calls at index time — budget it like a batch data pipeline, not a config toggle.

2. **Incremental updates are the hard part.** Re-extracting the whole graph per document update is uneconomical. The open-source graphrag library added incremental indexing, but community summaries drift when the underlying graph shifts; treat re-summarization cadence as a real design parameter for living corpora.

3. **Extraction quality controls the graph.** Cheap extraction models yield noisy, hallucinated entities and missed relations. Tune prompts per domain (the library supports domain adaptation of extraction prompts), sample-check extraction output against source text, and deduplicate entity variants early — graph quality caps everything downstream.

## LazyGraphRAG and cost deferral

1. **Defer LLM summarization to query time.** LazyGraphRAG (Microsoft Research, productionized in the graphrag library v2.0.0 as the NLP graph extraction mode) builds the graph with cheap NLP-based extraction plus concept embeddings, skipping LLM community summarization entirely at index time. At query time it matches concepts to communities, then performs bounded LLM summarization only over the relevant subgraph.

2. **Roughly 0.1% of GraphRAG indexing cost.** Microsoft reports LazyGraphRAG at about 0.1% of standard GraphRAG's indexing cost while matching or beating both vector RAG and full GraphRAG on their quality benchmarks for local and global query mixes. That cost structure changes who can afford graph-based retrieval at all — it moved from flagship-only to ordinary-corpus territory.

3. **Query cost shifts, total cost matters.** Lazy variants pay more per query (on-demand summarization) in exchange for near-free indexing. For low-query-volume corpora the lazy trade is almost always right; for very high query volumes on a frozen corpus, pre-computed summaries amortize better. Model your actual query-to-corpus ratio before choosing.

4. **First-class hybrid single mechanism.** A key LazyGraphRAG result is that one flexible query mechanism over the concept-graph structure outperformed the zoo of specialized local/global/vector strategies. Fewer retrieval code paths to maintain is itself an engineering win worth weighing against a few points of peak quality.

## Query patterns

1. **Local queries.** Seed with named entities, expand one to two hops, and summarize the retrieved subgraph. Use for "tell me everything about X" — graph traversal pulls in relationship context that similarity search fragments miss.

2. **Global queries.** Map-reduce over community summaries at a chosen hierarchy level, then reduce partial answers into a final synthesis. Level selection trades breadth for detail; shallow levels answer "themes," deeper levels answer "specifics per theme."

3. **DRIFT-style iterative search.** 2025 retrieval work interleaves graph walks with vector matching — start from a hybrid seed, then let each hop re-rank via embeddings. This mitigates graph sparsity and is the direction most production hybrid systems converged on.

## Production pitfalls

1. **Evaluate on your query mix, not published benchmarks.** The quality ordering of vector versus graph versus lazy flips with the ratio of lookup to synthesis queries in your traffic. Log and classify real queries first, then benchmark on that distribution.

2. **Latency budget discipline.** Global queries fan out to many LLM summarization calls; without aggressive parallelism and answer caching they blow interactive latency budgets. Reserve graph paths for background or high-value queries, or pre-compute answers for recurring global questions.

3. **Graph visualization tempts scope creep.** Entity graphs invite building a knowledge graph product on top of retrieval. Ship the retrieval win first; the product surface is a separate decision with separate costs.
