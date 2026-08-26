# AI evaluation scaffolding disclosure

**Issue:** Capability results are attributed to a model even though prompts, retries, tools, wrappers, graders, and recovery logic materially created the result.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Version system prompt, examples, tool schema/permissions, retrieval corpus, agent loop, retry/timeout, sampling, context, grader, post-processing, and human intervention. Report model-only and system-level results separately. Preserve failed runs and compute resource limits.

## Verification

Ablate scaffolding components; rerun with fixed budgets and held-out tasks; have an independent operator reproduce results; disclose material adaptations.

## Gotchas

Better scaffolding is a system capability, but it must not be misreported as base-model capability. Evaluator models can share biases. Tool access changes safety exposure.

## Sources

- [NIST pre-deployment evaluation overview and scaffolding disclosure](https://www.nist.gov/news-events/news/2024/12/pre-deployment-evaluation-openais-o1-model)
- [NIST AI Metrology Center](https://airc.nist.gov/metrology/)
