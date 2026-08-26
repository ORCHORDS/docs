# translation-quality-metrics

**Issue:** Measuring and tracking the quality of translations systematically
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Subjective quality judgments cause inconsistency between reviewers. Standardized metrics enable objective tracking and vendor SLAs.

## Pattern / Solution
MQM (Multidimensional Quality Metrics) -- ISO standard:
- Categories: Accuracy, Fluency, Terminology, Style, Locale convention
- Severity: Critical (meaning change), Major (comprehension affected), Minor (style)
- Score: `(Critical x 25 + Major x 5 + Minor x 1) / word_count`

LQA (Linguistic Quality Assurance) spot-check (10% of segments):
```
Score = (1 - weighted_error_count / word_count) x 100
Pass threshold: >= 90%
```

BLEU for MT evaluation:
```python
from sacrebleu import corpus_bleu
score = corpus_bleu(hypotheses, [references])
# > 50: high quality; 30-50: usable with light PE; < 30: heavy PE required
```

Post-edit distance: character edit distance between MT output and final PE divided by segment length.

## Gotchas
- BLEU is a corpus-level metric -- single-segment BLEU scores are meaningless
- MQM requires trained evaluators for consistent scoring
- Track metrics per language pair and vendor, not just as a one-off audit

## Related
- `machine-translation-post-editing.md`
- `mt-quality-evaluation-2026.md`
