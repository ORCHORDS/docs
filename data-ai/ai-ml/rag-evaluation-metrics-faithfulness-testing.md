# RAG Evaluation — Retrieval Metrics, Faithfulness, and Continuous Testing

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your RAG pipeline returns plausible-sounding answers that contain
fabricated facts not present in the retrieved documents. The
retrieval step fetches 10 chunks but the relevant one lands in
position 6 — the LLM ignores it (lost-in-the-middle effect) and
hallucinates instead. You have no automated way to detect this
before users do. When you change the chunking strategy or swap
the embedding model, you cannot measure whether retrieval quality
improved or degraded. Your evaluation is a manual spot-check of
20 queries by a developer who built the system.

## Context

RAG evaluation operates at three tiers: retrieval metrics measure
whether the right chunks were fetched, generation metrics measure
whether the answer is faithful to retrieved context and relevant
to the query, and end-to-end metrics compare the final answer
against ground truth. RAGAS (docs.ragas.io) established the
standard metric definitions — faithfulness, context precision,
context recall, answer relevance — now adopted across the industry.
DeepEval provides pytest-native CI/CD gating with 50+ metrics.
TruLens emphasizes OpenTelemetry-integrated production evaluation.
Nearly all modern frameworks use LLM-as-judge with chain-of-thought
prompting for reference-free scoring.

## Retrieval metrics

```
Metric              What it measures
──────────────────────────────────────────────────────────────
Recall@k            Fraction of relevant documents present
                    in the top-k retrieved

Precision@k         Fraction of top-k retrieved documents
                    that are actually relevant

MRR                 Mean Reciprocal Rank — averages 1/rank
(Mean Reciprocal    of the first relevant document; rewards
Rank)               putting the right chunk early

NDCG                Normalized Discounted Cumulative Gain —
                    accounts for graded relevance and rank
                    position, not just binary hit/miss

These metrics are independent of generation quality.
Improving retrieval is the highest-leverage fix for most
RAG failures.
```

## Generation metrics (RAGAS definitions)

```
Faithfulness / Groundedness:

  faithfulness = (claims supported by context) / (total claims)

  Process:
    1. LLM decomposes answer into atomic claims
    2. Each claim checked against retrieved context
    3. Supported claims / total claims = score

  Example:
    Answer: "The company was founded in 2010 and has 500 employees"
    Context mentions founding year but not employee count
    → faithfulness = 1/2 = 0.50

Answer Relevance (Response Relevancy):

  1. Generate hypothetical questions from the answer
  2. Measure embedding similarity back to original query
  3. Penalizes incomplete or off-topic answers

Context Relevance / Context Precision:

  Whether retrieved chunks are actually useful for answering.
  Penalizes noisy retrieval that dilutes signal.

Context Recall:

  Whether retrieved context covers everything needed.
  Usually requires a reference/ground-truth answer.
```

## End-to-end metrics

```
Answer Correctness / Factual Correctness:
  → Compares generated answer to reference answer
  → Measures semantic + factual overlap
  → Requires ground-truth test set

Semantic Similarity:
  → Embedding-level closeness to ground truth
  → Useful as a complementary signal
  → Does not catch factual errors with similar phrasing
```

## Evaluation frameworks

```
Framework     Strength                  Integration
──────────────────────────────────────────────────────────────
RAGAS         Reference implementation  Python, LangChain,
              of faithfulness/context   LlamaIndex; synthetic
              metrics; TestsetGenerator test set generation

DeepEval      Pytest-native, 50+        CI/CD gating, custom
(Confident    metrics, G-Eval           G-Eval rubrics,
AI)           (LLM-as-judge with        deterministic metrics
              custom rubric)

TruLens       OpenTelemetry-integrated  Production trace-based
              production evaluation;    evaluation; agent-
              feedback functions        specific metrics
```

## Synthetic test set generation

```python
# RAGAS TestsetGenerator — builds Q&A from your documents
from ragas.testset.generator import TestsetGenerator

generator = TestsetGenerator.with_openai()
testset = generator.generate_with_langchain_docs(
    documents,
    test_size=50,
    distributions={
        "simple": 0.4,
        "multi_context": 0.3,
        "reasoning": 0.3,
    },
)

# Produces questions requiring:
#   simple:        single chunk to answer
#   multi_context: synthesizing multiple chunks
#   reasoning:     inference beyond literal text
```

## LLM-as-judge approach

```
Nearly all modern RAG evaluation uses an LLM judge:

  Process:
    1. Present answer + context + query to judge LLM
    2. Judge uses chain-of-thought to score
    3. No ground truth needed (reference-free)

  G-Eval pattern (DeepEval):
    → Define a custom rubric (scoring criteria)
    → Judge LLM evaluates against rubric
    → More reliable than raw "rate 1-10" prompts

  Caveats (2025-2026 literature):
    → Judge bias toward verbose answers
    → Need rubric-based prompts, not open-ended scoring
    → Periodic recalibration against human labels
    → Judge model quality affects evaluation quality
```

## Continuous evaluation in production

```
Pipeline:
  1. Sample live traffic (queries + retrieved contexts + answers)
  2. Run faithfulness/relevance checks asynchronously
     (no ground truth needed for these metrics)
  3. Track metric drift over time
  4. Alert on faithfulness drops below threshold
  5. Re-run full synthetic test suite as CI gate on every
     retrieval/prompt/model change

  DeepEval: pytest integration for CI gating
  TruLens: OpenTelemetry tracing for production monitoring
  RAGAS: batch evaluation on synthetic + sampled test sets
```

## Common failure modes

```
1. Hallucination despite retrieval:
   → Retrieved passages are topically relevant but
     factually insufficient
   → Multiple chunks conflict with each other
   → Retrieval failure (not generation) is the dominant
     root cause in production RAG

2. Context window overflow:
   → Too many or too-long chunks in the prompt
   → Dilutes signal, increases cost and latency
   → Fix: reduce top-k, use reranking

3. Lost-in-the-middle effect:
   → LLMs favor information at the start and end of context
   → Correct chunk at position 6 of 10 gets ignored
   → Models can degrade >30% when correct chunk lands mid-context
   → Fix: reduce top-k (10→3-5), rerank so best chunk is
     first, or use position-aware chunk ordering
```

## Anti-patterns

- **Evaluating only with spot-checks** — manual review of 20
  queries does not catch retrieval regressions or rare failure
  modes. Build automated test suites with synthetic test sets.
- **Using only end-to-end metrics** — answer correctness alone
  does not reveal whether the problem is retrieval or generation.
  Evaluate both tiers independently.
- **Optimizing for faithfulness alone** — a perfectly faithful
  answer can be irrelevant or incomplete. Measure faithfulness
  AND answer relevance AND context recall together.
- **Stuffing maximum chunks into context** — more context does
  not mean better answers. The lost-in-the-middle effect and
  context dilution degrade quality. Use reranking and limit top-k.

## Gotchas

- **Judge model bias** — LLM judges tend to prefer longer,
  more detailed answers even when brevity is correct. Use
  rubric-based evaluation (G-Eval) to counteract this.
- **Synthetic test sets are not ground truth** — generated
  Q&A pairs need human validation of a sample to ensure quality.
  Use them for regression detection, not as sole quality measure.
- **Faithfulness ≠ correctness** — an answer can be perfectly
  faithful to the retrieved context but wrong if the source
  documents are outdated or incorrect.
- **Metric score thresholds vary by domain** — a faithfulness
  score of 0.8 may be acceptable for a knowledge base chatbot
  but unacceptable for medical or legal applications.

## Verification

- Retrieval metrics (recall@k, precision@k, MRR) tracked per query.
- Faithfulness and answer relevance evaluated on every pipeline change.
- Synthetic test set generated from source documents (50+ questions).
- LLM-as-judge configured with rubric-based evaluation.
- Continuous production sampling with async metric evaluation.
- Lost-in-the-middle effect mitigated via reranking and limited top-k.

## Related

- `documentation/categories/ai-ml/rag-chunking-embeddings-retrieval.md`
- `documentation/categories/ai-ml/llm-function-calling-tool-use.md`
- `documentation/categories/ai-ml/agent-architecture-error-recovery.md`

## Source URLs (verified 2026-08-16)

- RAGAS — Available Metrics — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- RAGAS — Testset Generation for RAG — https://docs.ragas.io/en/stable/getstarted/rag_testset_generation/
- Confident AI — RAG Evaluation Metrics — https://www.confident-ai.com/blog/rag-evaluation-metrics-answer-relevancy-faithfulness-and-more
- DeepEval — Top LLM Evaluation Frameworks Compared — https://deepeval.com/blog/top-5-llm-evaluation-frameworks
