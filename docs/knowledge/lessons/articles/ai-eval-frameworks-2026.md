# ai-eval-frameworks-2026

**Issue:** A team builds an LLM application. They want to evaluate retrieval, generation, agent behavior, safety, and bias. There are 20+ open-source frameworks. Picking wrong wastes months.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The 2026 LLM eval framework landscape has consolidated around 3-4 core tools. Picking wrong is expensive; the gap between "spike" and "CI-gated production" is 2-6 months.

## Root cause

Three concerns get conflated: model evaluation (MMLU, HumanEval), system evaluation (RAGAS, DeepEval, Promptfoo), and production monitoring (Langfuse, Arize). Each tool lives in one slot.

## The 3 framework roles (revisited)

| Role | Tool | Use case |
|---|---|---|
| RAGAS | RAG-specific metrics (faithfulness, context precision, context recall) | teams building RAG pipelines |
| DeepEval | broad metric library, pytest-style | CI/CD quality gates, regression tests |
| Promptfoo | CLI + YAML + 500+ attack vectors | prompt regression, red-teaming |
| MLflow LLM Evaluate | eval logged alongside MLflow experiments | teams on MLflow |
| LangSmith | eval + tracing + production debugging | teams in LangChain ecosystem |

The 2026 default: RAGAS for RAG, DeepEval for CI gates, Promptfoo for prompt regression and red-teaming.

## The 14 DeepEval metrics

DeepEval 0.5+ ships 14+ metrics across 6 categories.

1. **Correctness** — G-Eval, hallucination, answer relevancy
2. **RAG** — context precision, context recall, faithfulness
3. **Safety** — bias, toxicity
4. **Agent** — task completion, tool correctness
5. **Conversational** — knowledge retention, conversational relevancy
6. **Custom** — G-Eval rubric, DAG metric, custom LLM judge

For 90%+ of teams, DeepEval + pytest + RAGAS covers the surface.

## The 6 RAGAS metrics (revisited)

RAGAS 1.x (2026) is the RAG evaluation standard.

1. **Faithfulness** — atomic claim decomposition; is the answer grounded in retrieved context?
2. **Context precision** — is the retrieved context relevant?
3. **Context recall** — did retrieval find the right documents?
4. **Answer relevancy** — does the answer address the question?
5. **Answer correctness** — does it match ground truth?
6. **Answer similarity** — semantic similarity to ground truth (embedding-based)

For RAG, start with RAGAS. Pair with DeepEval for bias/toxicity outside RAG context.

## The 5 Promptfoo patterns

Promptfoo (MIT, ~50K stars) is the CLI-first prompt regression tool.

1. **Prompt A/B testing** — YAML config + multiple prompts; measure which performs better
2. **Model comparison** — same prompt across OpenAI, Anthropic, Bedrock
3. **Assertion-based testing** — contains, equals, regex, is-json, llm-rubric
4. **Red-teaming** — 500+ attack vectors; jailbreak, PII, prompt injection
5. **CI integration** — exit code in CI; gates the merge

The 2026 default for prompt iteration: Promptfoo.

## The MLflow integration pattern

MLflow integrates DeepEval + RAGAS + Arize Phoenix as scorers.

```python
import mlflow
from mlflow.genai.scorers import (
    deepeval_scorer, ragas_scorer, phoenix_scorer
)

# Use third-party metrics through the same API
mlflow.genai.evaluate(
    data=eval_dataset,
    scorers=[
        deepeval_scorer("hallucination"),
        ragas_scorer("faithfulness"),
        phoenix_scorer("relevance")
    ]
)
```

50+ metrics from third-party frameworks through one API. For teams on MLflow, this is the consolidation layer.

## The 5-step selection pattern

1. **What's the use case?** RAG → RAGAS; agent → DeepEval; prompt → Promptfoo; MLops → MLflow
2. **What's the integration style?** Python lib (RAGAS, DeepEval) vs CLI (Promptfoo) vs platform (LangSmith)
3. **What metrics are needed?** RAG-specific vs general vs safety
4. **What's the team skill?** Python-first (DeepEval) vs YAML-first (Promptfoo) vs notebook (MLflow)
5. **What's the budget?** Free OSS vs commercial (LangSmith, Arize, Future AGI)

A practical 2026 default: RAGAS + DeepEval + Promptfoo, all open source, with optional MLflow if the team is on it.

## The 5 best practices

1. **Eval the system, not just the model.** MMLU on the base model is irrelevant; RAGAS on your pipeline is the truth.
2. **One golden set, multiple metrics.** A labeled golden set is the asset. Evaluate it with multiple metrics.
3. **LLM-as-judge needs bias audit.** Position-swap, multi-judge panel, self-preference check. See `lessons/llm-evaluation-frameworks-2026.md`.
4. **Eval in CI, not as a quarterly report.** If the team has to remember to run it, they won't.
5. **Combine automated + human spot-check.** Metrics miss fluent hallucinations; humans catch them.

## The 5 anti-patterns

1. **One LLM judge scoring everything.** Self-preference bias; use a panel of 3+ from different families.
2. **No golden set.** Eval without labels is just vibes. Build the golden set.
3. **Eval that's a separate report.** Must be in CI, gating the merge.
4. **Position-blind judge.** Run position-swap detection; if the winner flips >5%, you have bias.
5. **Eval that takes longer than 10 seconds.** Long eval is skipped. Budget CI time.

## The framework comparison (2026 mid-year)

| Framework | Stars | License | CI speed | Coverage | Best for |
|---|---|---|---|---|---|
| Promptfoo | ~50K | MIT | seconds | 500+ assertions, red-team | prompt regression |
| DeepEval | ~30K | Apache 2.0 | seconds | 20+ metrics | CI gates, regression |
| RAGAS | ~15K | Apache 2.0 | seconds | dozen RAG | RAG-specific eval |
| Future AGI | proprietary | Apache 2.0 SDK | seconds | 50+ | unified eval + observability |
| Arize Phoenix | ~10K | Elastic 2.0 | seconds | 10+ | tracing + eval |
| MLflow Evaluate | ~20K | Apache 2.0 | minutes | dozen | MLflow-integrated eval |
| LangSmith | commercial | commercial | seconds | full | LangChain teams |
| Inspect AI | ~5K | MIT | seconds | 20+ | agent capability eval |

The CI-gating ones (Promptfoo, DeepEval) take seconds. The platform ones (LangSmith, Arize) take minutes but offer more.

## The 2026 production stack

A 2026 production LLM eval stack.

```
Source code commit
  → CI runs Promptfoo (prompt regression, <30s)
  → CI runs DeepEval (golden set, <2min)
  → CI runs RAGAS (RAG-specific, <2min)
  → Total: <5min CI gate
  → Human spot-check weekly
  → Production monitoring via Langfuse or Arize
```

5 minutes for the CI gate. A drop in any metric blocks the merge.

## The eval-driven development protocol

1. **Every PR that changes prompt, model, or RAG logic must update the golden set and metrics**
2. **The PR description includes the eval diff** (which scores changed, by how much)
3. **The CI runs the same eval; a regression blocks the merge**
4. **Eval scores are tracked over time** in MLflow or Weights & Biases
5. **Monthly review** of the golden set, the metrics, the bias

The PR is the eval; the code is the diff in eval scores.

## Verification

The tell that LLM eval is real:

- A named framework (RAGAS, DeepEval, Promptfoo) is in the release checklist
- CI runs eval on every prompt/model change
- The golden set is version-controlled
- Judge models are different from system-under-test models
- Bias audit (position-swap) is part of the eval suite
- A regression blocks the merge

The tell it isn't:

- "We tested it manually" with no recorded prompts
- A single LLM judge (e.g., GPT-4 judging GPT-4)
- No metric thresholds defined
- Eval is a quarterly report someone writes
- Production regressions go undetected

## Gotchas

- **The golden set is the asset.** Without it, eval is not reproducible. Version-control the golden set.
- **Position bias is measurable.** Run position-swap detection; if the winner flips >5%, you have a problem.
- **Self-preference is real.** GPT-4 judges prefer GPT-4 outputs. Use a different-family judge.
- **LLM-as-judge is approximate.** Treat it as a signal, not a measurement. Human spot-check is the truth.
- **RAGAS is RAG-specific.** For chatbots, use DeepEval or Promptfoo.

## Related

- `lessons/llm-evaluation-frameworks-2026.md` — deeper on RAGAS/DeepEval/Promptfoo
- `lessons/eval-driven-development-2026.md` — eval in CI
- `lessons/ai-safety-benchmarks-2026.md` — model-level safety benchmarks
- `lessons/ai-rag-patterns-2026.md` — the system being evaluated

## Source URLs (verified 2026-08-10)

- https://machinelearningmastery.com/llm-evaluation-frameworks-compared-how-to-actually-measure-what-your-model-does/
- https://docs.ragas.io/ — RAGAS docs
- https://docs.confident-ai.com/ — DeepEval docs
- https://promptfoo.dev/docs/intro/ — Promptfoo
- https://mlflow.org/blog/third-party-scorers/ — MLflow + DeepEval + RAGAS + Phoenix
- https://mlflow.org/top-5-agent-evaluation-frameworks/
- https://deepeval.com/blog/llm-as-a-judge
- https://futureagi.com/blog/best-open-source-eval-frameworks-2026/
- https://github.com/UKGovernmentBEIS/inspect_ai — Inspect AI
- https://docs.arize.com/phoenix — Arize Phoenix
