# ai-eval-2026

**Issue:** A team ships a model update. The team needs to know if the new version is better, worse, or the same as the old. The team reads about benchmarks, human eval, LLM-as-judge, statistical testing. The team needs the 2026 reference for AI evaluation.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 evaluation types

1. **Benchmark accuracy.** Standardized tests (MMLU, HumanEval, GSM8K, MT-Bench). Comparable across models.
2. **Human evaluation.** Annotators rate outputs. Gold standard but slow and expensive.
3. **LLM-as-judge.** Use a frontier model to grade outputs. Fast, biased but improvable.
4. **Production telemetry.** User feedback, retry rates, escalation rates. Real-world signal.
5. **Adversarial testing.** Red team, jailbreak attempts, prompt injection. Robustness.

## The 5 statistical rigor requirements (NIST AI 800-3)

1. **Distinguish benchmark accuracy from generalized accuracy.** Benchmark = performance on fixed test set; generalized = superpopulation.
2. **Confidence intervals required** for any reported metric.
3. **Generalized linear mixed models** for cross-model comparison.
4. **Multiple benchmarks** to avoid single-test gaming.
5. **Held-out evaluation** to detect training/test contamination.

## The 5 evaluation frameworks

1. **RAGAS** - RAG-specific (faithfulness, answer relevance, context relevance).
2. **DeepEval** - 20+ metrics, pytest-native.
3. **Promptfoo** - prompt regression, 500+ attack vectors, MIT.
4. **MLflow LLM Evaluation** - integrated with MLflow tracking.
5. **Inspect AI** - UK AISI / Anthropic-style structured evals.

## The 5 LLM-as-judge bias mitigations

1. **Position bias** - swap order, run twice, average.
2. **Self-enhancement bias** - judge different from candidate model family.
3. **Verbosity bias** - normalize for length, prompt for conciseness.
4. **Sycophancy bias** - hide "correct" answer from judge.
5. **Style bias** - judge on substance, not formatting.

## The 5-step evaluation pattern

1. **Define quality bar** - what does "good" mean for this use case?
2. **Build golden test set** - 100-500 representative inputs with expected outputs.
3. **Run multi-metric eval** - benchmark, LLM-as-judge, human spot-check.
4. **Statistical test** - is the new model significantly different?
5. **Production telemetry** - 2-week shadow traffic before full rollout.

## The 5 anti-patterns

1. **Single benchmark reported** - easily gamed.
2. **No confidence intervals** - "0.85 vs 0.83" without error bars is noise.
3. **LLM-as-judge without bias audit** - inheriting the judge model's biases.
4. **Train/test contamination** - benchmark items in training data.
5. **Eval as a one-time check** - no CI integration.

## Gotchas

- Some benchmarks (HumanEval) are now saturated or contaminated; check 2026 freshness.
- LLM-as-judge cost adds up at scale; sample 10-20% of production traffic.
- Human eval is gold but slow; use for spot-checking, not full coverage.
- Production telemetry has its own biases (selection bias, survivorship bias).
- Adversarial testing is separate from accuracy testing; need both.

## Source URLs (verified 2026-08-10)

- https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-3.pdf
- https://docs.ragas.io/
- https://docs.confident-ai.com/
- https://promptfoo.dev/
- https://mlflow.org/docs/latest/llm-evaluation/
- https://github.com/UKGovernmentBEIS/inspect_ai
