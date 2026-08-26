# similarity-threshold-tuning

**Issue:** Setting the right similarity threshold to balance recall and precision
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Too-high threshold returns no results; too-low returns irrelevant noise.

## Pattern / Solution
```python
# Calibrate using a labeled dataset
from sklearn.metrics import precision_recall_curve

scores = []
labels = []
for query, relevant_ids in test_set.items():
    results = vector_search(query, top_k=50)
    for r in results:
        scores.append(r["score"])
        labels.append(1 if r["id"] in relevant_ids else 0)

precision, recall, thresholds = precision_recall_curve(labels, scores)
# Pick threshold at F1 peak
f1 = 2 * (precision * recall) / (precision + recall + 1e-8)
optimal_threshold = thresholds[f1.argmax()]
```

## Gotchas
- Cosine similarity ranges differ by embedding model — calibrate per model
- Use 0.75 as a starting point for `text-embedding-3-large`
- Dynamic thresholding based on query type outperforms single global threshold

## Related
- `semantic-search-implementation.md`
- `rag-vector-search.md`
