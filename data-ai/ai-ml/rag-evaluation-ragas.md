# rag-evaluation-ragas

**Issue:** Evaluating RAG pipeline quality with the RAGAS framework
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without systematic evaluation, RAG quality improvements are anecdotal.

## Pattern / Solution
```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_recall, context_precision
from datasets import Dataset

data = {
    "question": [q],
    "answer": [generated_answer],
    "contexts": [[chunk1, chunk2]],
    "ground_truth": [expected_answer],
}
ds = Dataset.from_dict(data)
result = evaluate(ds, metrics=[faithfulness, answer_relevancy, context_recall, context_precision])
print(result)  # scores 0-1 for each metric
```

## Gotchas
- RAGAS uses LLM-as-judge internally — costs scale with eval dataset size
- `faithfulness` detects hallucination; `context_recall` detects retrieval gaps
- Build a golden QA dataset from real user queries, not synthetic ones

## Related
- `rag-hallucination-detection.md`
- `prompt-testing-evals.md`
