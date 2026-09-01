# RAG Grounding Citation Alignment

**Issue:** Retrieval-augmented generation systems frequently hallucinate by attributing synthesized statements to wrong or fabricated source passages, eroding operator trust and creating audit risk. Engineering teams need a deterministic process for binding every emitted claim back to its retrieved passage with verifiable alignment scores, so reviewers can answer "show me where this sentence came from" without re-reading the entire vector index.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why Citation Alignment Is Distinct From Retrieval Quality

Citation alignment measures a different axis of RAG quality than top-k retrieval precision or recall. A retriever can return perfect passages and the generator can still produce sentences that paraphrase, blend, or extrapolate beyond those passages, breaking the chain of custody from claim to source. NIST AI 600-1 notes that provenance metadata is necessary for risk-tiered evaluation of generative systems, and that traceability of outputs to source artifacts is the minimum bar for moderate-impact deployments. Citation alignment is the operational expression of that traceability.

A working definition: every token-sequence that crosses the citation boundary must map to a contiguous span in a retrieved chunk whose ID is recoverable at query time. Alignment is the F-measure of those span mappings, scored per response. A response with a perfect retrieval score but poor alignment still ships unsupported facts.

## Building an Alignment Dataset

Aligners need labeled spans. The cheapest reliable source is synthetic generation: take each retrieved chunk, ask the generator to produce claims constrained to that chunk, then ask a second model to point at the supporting span. Disagreements between generator and verifier become negative training examples. A rule of thumb is 1,000 triple-labeled examples per domain for a usable aligner; smaller sets converge to trivial copying behavior.

Human-in-the-loop review is required for high-stakes domains. Spans under ten tokens tend to be unverifiable by judges because too little semantic content fits, so reviewers should reject them. Conversely, spans covering full chunks usually indicate unfaithful copying. The middle band of 20 to 80 tokens is where reviewers provide the highest-signal labels.

## Scoring Functions Worth Using

Three families of aligners consistently outperform naive token overlap. Span-level Natural Language Inference (NLI) labels each candidate span as entailment, neutral, or contradiction with respect to the response sentence; the proportion of entailed spans is the alignment score. Token-level attribution methods such as integrated gradients or attention rollout heat-map the response and select the top-k input tokens; alignment is the recall@k of those tokens against the labeled span. LLM-as-judge prompts that explicitly request supporting span IDs and reject unsupported claims give the highest agreement with human raters on long-form responses.

The correct family depends on response length. Short factual answers favor NLI. Long-form technical answers with multiple sub-claims favor LLM-as-judge with structured span outputs. Token attribution is useful as a debugging lens, not as a primary metric.

## Operationalization In CI

Citation alignment should be a gating metric in continuous integration, not a one-off benchmark. A typical pipeline runs the eval suite on every prompt-template change and every retriever change. If the alignment score drops more than two percentage points relative to the previous merge, the change fails CI. The eval set must be version-controlled alongside the prompts and retriever configuration, with frozen dataset hashes published in the model card.

Dashboards should expose per-source-document alignment rates, not just an aggregate. A single high-traffic source that frequently misaligns can dominate an aggregate score while remaining invisible. Per-document breakdowns catch cases where a chunker silently degraded boundary detection for a particular content type.

## Failure Modes And Anti-Patterns

The most common anti-pattern is evaluating citation alignment on the validation split of the QA dataset used to train the retriever, which leaks overlap between training and evaluation. Another is rewarding the generator for fabricating plausible citations, because human raters sometimes accept any well-formed citation. A third is computing alignment only on responses that include the citation marker, ignoring responses where the generator skipped citation entirely; the skip case must be scored as zero alignment.

A subtle failure mode arises when chunkers split passages mid-sentence at retrieval time: the retriever returns the half that happens to contain the keyword, and the citation points at a passage that no longer contains the full sentence the generator wrote. Document-level chunking with overlap, or sentence-aware segmentation, prevents this drift between chunking and citation.

## Canonical sources

1. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
2. https://arxiv.org/abs/2310.05480