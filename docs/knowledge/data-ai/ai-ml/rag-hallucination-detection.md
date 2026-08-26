# rag-hallucination-detection

**Issue:** Detecting when LLM generates facts not grounded in retrieved context
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LLMs confidently state incorrect facts that contradict or extend beyond retrieved documents.

## Pattern / Solution
```python
# NLI-based entailment check
from transformers import pipeline
nli = pipeline("text-classification", model="cross-encoder/nli-deberta-v3-small")

def is_grounded(claim: str, context: str) -> bool:
    result = nli(f"{context} [SEP] {claim}")[0]
    return result["label"] == "ENTAILMENT" and result["score"] > 0.7

# LLM-as-judge approach
judge_prompt = f"""Does the answer contain any claims not supported by the context?
Context: {context}
Answer: {answer}
Reply with only YES or NO."""
hallucinated = llm(judge_prompt).strip().upper() == "YES"
```

## Gotchas
- NLI models have their own errors — calibrate threshold per domain
- Long answers need sentence-level checking, not document-level
- False negatives (missed hallucinations) are more dangerous than false positives

## Related
- `rag-citation-grounding.md`
- `rag-evaluation-ragas.md`
- `llm-output-validation.md`
