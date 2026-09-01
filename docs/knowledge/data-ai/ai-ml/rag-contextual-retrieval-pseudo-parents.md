# RAG Contextual Retrieval and Pseudo-Parents

Chunks fail retrieval for a boring reason: they are fragments. A chunk saying "the threshold is 60 days" embeds as a fact about nothing in particular — no product name, no section context, no document identity — so the query "what is the renewal window for the standard plan" may not reach it. Contextual retrieval fixes the fragment by prepending generated context to each chunk before embedding; small-to-big retrieval (pseudo-parents) fixes it differently, retrieving small precise chunks but delivering their larger parent section to the generator. Both attack fragment ambiguity with different cost profiles.

## Scope

This article covers context-enrichment strategies for chunk retrieval: contextual chunk preparation, parent-document (small-to-big) retrieval patterns, their combination, and the cost/consistency governance each requires. It applies to RAG pipeline design and rework.

Excluded: chunk-boundary mechanics (the split itself is a separate discipline), reranking, and generation-time context compression, which reduces delivered context after retrieval rather than improving what is found.

The two patterns in brief. Contextual retrieval: at ingestion, an LLM writes a short situating preamble for each chunk ("This clause is from the Master Services Agreement, section 9, governing renewal terms..."), and the enriched text is embedded. Retrieval matches the enriched representation. Small-to-big: the index holds small chunks, each pointing at its parent section; retrieval scores small chunks for precision, but the system delivers the parent to the generator for completeness. Both make fragments findable; contextual retrieval pays LLM cost at ingestion, small-to-big pays token cost at generation.

## Workflow or implementation guidance

1. **Diagnose which failure you actually have.** Compare failure cases: queries that retrieved nothing relevant (fragment ambiguity — both patterns help) versus queries that retrieved a relevant fragment too small to answer from (delivery inadequacy — small-to-big helps directly). The golden-set failure taxonomy from retrieval evaluation tells you which problem dominates before you spend ingestion or generation budget.
2. **For contextual retrieval, generate context at ingestion with a pinned, cheap model.** The preamble writer needs only modest capability — situating a chunk is far easier than answering questions. Pin the model and prompt version; store the generated context alongside the chunk; embed the combined text. Regeneration on model change is a re-ingestion event with its own cost budget.
3. **Keep the generated context short and factual.** Instruct the writer to name the document, section, and topic — not to summarize or interpret content. Long preambles dilute the chunk's own signal; interpretive preambles inject hallucinated framing that retrieval then matches. A length cap and a factual-only instruction keep enrichment aligned.
4. **For small-to-big, design the two granularities deliberately.** Index granularity: small chunks optimized for matching precision (sentences to short paragraphs). Delivery granularity: parent sections sized to the generator's context budget. The parent map (chunk → parent) is built at split time and versioned with the splitter; both granularities derive from the same structural boundaries so they stay aligned.
5. **Deduplicate at delivery, not at retrieval.** Small chunks from the same parent will all match a query about that section; delivering the parent once is the point — collapsing duplicates before generation saves context budget. Delivery dedup is by parent identity; the retrieval ranking decides which parents' best chunks represent them.
6. **Combine when both failure types are present.** Enriched small chunks (contextual + small-to-big) give precise matching over findable fragments with complete delivery. This is the most expensive configuration at ingestion; adopt it after the simpler pattern shows residual failures the other would fix.
7. **Budget the trade explicitly.** Contextual retrieval adds LLM ingestion cost per chunk (one-time per corpus version) and improves retrieval precision; small-to-big adds delivered tokens per request and improves answer completeness. For a large, stable corpus with high query volume, ingestion enrichment amortizes well; for a rapidly changing corpus with modest query volume, it may not pay.

## Controls

- **Preamble quality sampling.** Periodic human review of generated contexts for hallucinated framing, topic drift, and length compliance; a defect rate above tolerance triggers writer-prompt revision and re-ingestion planning.
- **Writer model/version pinning.** The ingestion pipeline records the writer model and prompt version per batch; regeneration decisions are explicit events with cost estimates.
- **Parent-map integrity.** Every indexed chunk resolves to exactly one deliverable parent; ingestion assertions enforce referential integrity so delivery never crashes on an orphan chunk.
- **Delivery token accounting.** Average context tokens per request tracked after adopting small-to-big; growth beyond the budget triggers parent-size review rather than quiet cost creep.
- **A/B evaluation on the golden set.** Recall@K and end-task quality compared across configurations (baseline, contextual, small-to-big, combined) with confidence intervals; the configuration choice cites this evidence.

## Validation evidence

- Configuration comparison table on the golden set: retrieval recall, precision at operating K, end-task answer quality, average delivered tokens, and ingestion cost per 1,000 chunks — the decision's evidence file.
- Preamble audit sample with defect categories and rates, showing the enrichment stayed factual over time.
- Parent-map integrity checks passing across ingestion batches, including after splitter version changes.
- Cost amortization analysis at current and projected corpus sizes and query volumes, justifying the chosen pattern's economics.

## Failure modes and correction

- **Hallucinated context dominates embedding.** The writer adds interpretive or wrong framing; retrieval now matches the hallucination as much as the content. Correction: factual-only instructions with length caps, sampling audit, and regeneration of affected batches; recall on affected classes recovers after re-ingestion.
- **Parent bloat.** Parents sized generously (whole chapters) blow the generation context budget and dilute answers. Correction: cap parent size at split time with a fallback to sibling-group delivery; token accounting catches drift.
- **Stale enrichment after content edits.** A document section changes; the enriched chunks (and their embeddings) still carry the old context. Correction: ingestion keyed on content hashes — any content change regenerates context and embedding for affected chunks; freshness checks compare index age to source age per document.
- **Dedup collapsing distinct sections.** Two parents share a boilerplate prefix; dedup by early-token similarity merges distinct sections and drops unique content. Correction: dedup by parent identity only, never by textual similarity of delivered passages.
- **Writer-model drift on regeneration.** Re-running ingestion after a writer-model upgrade rewrites all preambles; retrieval shifts subtly without any content change. Correction: writer version pinned per corpus; regeneration is deliberate, evaluated on the golden set before cutover.

## Limitations

Contextual retrieval effectiveness depends on the writer model's domain fidelity; specialized corpora may need prompt iteration before preambles are accurate. Ingestion-enrichment costs recur on every corpus version, which changes the calculus for high-churn corpora. Small-to-big increases delivered context, interacting with generator context limits and cost; its value depends on the generator's ability to use longer context effectively. Both patterns assume the golden evaluation set distinguishes retrieval from generation failures — without that, configuration comparisons conflate stages. Document formats lacking clear structure (scanned PDFs, transcripts) weaken parent-map quality and thus the small-to-big pattern's foundations.

## Canonical sources

- Anthropic documentation, Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval
- LlamaIndex documentation, Small-to-Big Retrieval: https://docs.llamaindex.ai/en/stable/examples/retrievers/auto_merging_retriever/
