# llm-ab-testing

**Issue:** Comparing LLM models or prompts requires rigorous experimental design to produce valid conclusions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A team switches from one model to another and reports "it seems better" based on a handful of examples. Six weeks later, a regression is discovered that would have been caught with systematic testing. Ad-hoc LLM evaluation produces unreliable decisions.

## Pattern / Solution
Define metrics before running experiments (task success rate, user rating, latency, cost). Route a percentage of live traffic to the challenger using a feature flag. Collect enough samples for statistical significance — use power analysis (typically 1000+ per variant for 80% power at p=0.05). Use pairwise human preference ratings (A vs B) for subjective quality evaluation.

Track experiment assignments in your logging so you can slice any metric by variant later.

## Gotchas
- LLM outputs are non-deterministic — use fixed temperature and seed for offline evals, live traffic for online evals
- Novelty effect: users rate new model outputs higher initially regardless of actual quality
- Metric gaming: optimizing for automatic metrics (BLEU, ROUGE) can diverge from human preference

## Related
- llm-shadow-deployment
- ai-feature-flag-patterns
- prompt-testing-evals
- model-versioning-strategy
