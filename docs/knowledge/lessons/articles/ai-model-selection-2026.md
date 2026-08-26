# ai-model-selection-2026

**Issue:** Every request hits GPT-5 or Claude Opus because "we want the best quality." Bill is 10x what it needs to be. Half the requests are classification, extraction, or routing — tasks a $0.04/1M model handles at 95% accuracy.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Defaulting to a single frontier model is the most expensive mistake in LLM systems. The same prompt that costs $0.69 on Opus 4.6 costs $0.003 on Gemini 2.5 Flash and runs in 1.1s instead of 4.1s. For tasks where quality is within noise, the cost and latency difference is 100x.

## Root cause

There is no "best model." There are task tiers, and each tier has a different optimum. The selection problem is per-task, not per-organization. A model that wins SWE-bench Verified at 80% is overkill for "extract invoice number from email body."

The five selection axes:

1. **Quality** (pass rate, rubric score, eval set accuracy)
2. **Cost** (input $/1M, output $/1M, cache hit rate)
3. **Latency** (TTFT, throughput tokens/sec, p99)
4. **Context window** (input size, max output tokens)
5. **Reliability** (refusal rate, error rate, schema compliance)

Different workloads weight these differently. Real-time chat weighs latency; batch enrichment weighs cost; legal review weighs quality.

## The 2026 selection matrix

| Tier | Use case | Models (2026) | Input $/1M | Output $/1M | TTFT |
|---|---|---|---|---|---|
| Frontier reasoning | Multi-step planning, complex refactor | Claude Opus 4.6, GPT-5.2 | $5-15 | $25-75 | 500ms-2s |
| Frontier balanced | Production reasoning + tool use | Claude Sonnet 4.6, GPT-5.4, Gemini 3.1 Pro | $1-4 | $4-15 | 300ms-1s |
| Mid-range | Most production traffic | Claude Haiku 4.5, GPT-5.4 Mini, Gemini 2.5 Pro | $0.40-1.25 | $1.60-10 | 200-500ms |
| Budget | Classification, extraction, batch | Gemini 2.5 Flash, DeepSeek V3.2, GPT-5 Nano | $0.05-0.50 | $0.40-3 | 150-300ms |
| Ultra-fast | Sub-100ms, high-throughput RAG | Gemini 2.0 Flash, Llama 4 Scout (Groq) | $0.04-0.10 | $0.14-1 | <100ms |
| Local free | Air-gapped, private data | Llama 4 Scout, Qwen 3.5 35B, GPT-oss-20b | $0 | $0 | 300-600ms (H100) |

The Anthropic-published benchmark on 38 real tasks (March 2026) shows the spread: Claude Sonnet 4.6 hits 100% pass rate at $0.20/run and 4.6s median. Gemini 2.5 Flash hits 97.1% at $0.003/run and 1.1s median. Same workload, 67x cost difference, 4x latency difference.

## The five-step selection process

For any new use case:

1. **Eliminate non-starters.** If the task is health-data processing on PHI, eliminate any model that doesn't support your data residency. If the task is sub-200ms interactive, eliminate any model with TTFT > 150ms.
2. **Classify the task by intelligence tier.** Extraction and routing are tier 1 (budget models). Multi-step tool use is tier 3 (frontier). Coding and planning are tier 4 (frontier+).
3. **Read the right benchmarks.** SWE-bench Verified for code. GPQA Diamond for science. AIME 2025/2026 for math. MMLU-Pro for general knowledge. HLE for frontier reasoning. Don't use a single benchmark; weight the suite.
4. **Shortlist 3-5 models, run your own eval.** A model that scores 80% on a public benchmark might score 65% on your eval set, because your distribution is different. Build the golden set; run the candidates.
5. **Design a routing strategy, not a single model.** Cheap default + confidence-gated escalation. Per-tier defaults with overrides for known hard cases.

A team that ships step 5 saves 40-70% on routed workloads, with no measurable quality loss on the eval set.

## The routing architecture

```python
def route(prompt, task_type, confidence_threshold=0.85):
    if task_type in ("extraction", "classification", "routing"):
        return cheap_model  # Gemini Flash, GPT-5 Nano
    if task_type in ("summarization", "simple_qa"):
        return mid_model    # Haiku 4.5, GPT-5.4 Mini
    if task_type in ("tool_use", "code", "planning"):
        return frontier     # Sonnet 4.6, GPT-5.2
    # escalation path: cheap first, expensive on low confidence
    draft = cheap_model.generate(prompt)
    if confidence(draft) > confidence_threshold:
        return draft
    return frontier.generate(prompt)
```

The cheap-first path is the routing default. The expensive model is the escalation. Track the escalation rate per task type. If escalation is over 30% for a task, the cheap model is the wrong default for that task; either re-classify or raise the threshold.

## The cost-quality frontier in numbers

From the 38-task benchmark (March 2026):

| Model | Pass rate | Cost/run | Median time |
|---|---|---|---|
| Claude Sonnet 4.6 | 100% | $0.20 | 4.6s |
| Claude Opus 4.6 | 100% | $0.69 | 4.1s |
| GPT-5.2-codex | 97% | $0.16 | 4.6s |
| GPT-oss-20b (local) | 97% | $0.00 | 4.1s |
| Gemini 2.5 Flash | 92% | $0.003 | 1.1s |
| Claude Haiku 4.5 | 97% | $0.04 | 2.2s |
| GPT-5-Nano | 92% | $0.03 | 11.1s |

The cost-quality frontier at "≥95% pass rate" includes Sonnet 4.6 ($0.20), Haiku 4.5 ($0.04), and GPT-oss-20b (free). Opus 4.6 buys you nothing on this set versus Sonnet 4.6. Below 95%, Gemini 2.5 Flash dominates cost.

## The self-hosting threshold

Self-hosting makes sense when:

- Volume justifies the GPU cost (typically > 50M tokens/month for the same task)
- Data residency requires it (HIPAA, GDPR, air-gapped)
- Latency is constrained and edge inference is the only path

For most teams, the break-even on self-hosting is far above their current volume. A managed Gemini Flash at $0.003/run is hard to beat on cost until you're processing millions of runs per month. Self-hosting also brings ops cost: GPU provisioning, KV-cache management, quantisation, version upgrades. The rule: self-host only at volume or compliance, not for ideological reasons.

## Verification

The tell that model selection is working:

- Per-task model assignment is documented; engineers don't have to think about which model to call
- The cost dashboard shows work distributed across 3+ model tiers, not 100% on a frontier model
- Routing escalation rate is tracked and tuned per task
- A change in upstream model pricing triggers an eval re-run, not a panic

The tell it isn't:

- One model handles everything; cost is whatever the frontier charges
- Latency is unpredictable because the same prompt sometimes hits a fast model, sometimes a slow one
- Nobody knows what the current escalation rate is

## Gotchas

- **Don't use public benchmarks as your sole selector.** A model that wins SWE-bench can fail at your specific task because your distribution is different. Always run on your own eval set.
- **Cost is not just per-token.** Cached input tokens, output tokens, and the input:output ratio matter. A model with lower $/1M but a 5:1 output-to-input ratio can cost more than a higher-priced model with a 1:5 ratio.
- **Latency has two numbers.** TTFT (time to first token) and throughput (tokens/sec) trade off. Real-time chat cares about TTFT; batch cares about throughput.
- **Self-hosting has hidden costs.** GPU hours, electricity, MLOps, version upgrades. The "free" inference is only free at scale.
- **The frontier is a moving target.** Re-evaluate quarterly. The model that won last quarter is mid-tier this quarter.

## Related

- `patterns/agent-routing-2026.md` — the routing implementation
- `lessons/ai-cost-finops-2026.md` — the cost discipline
- `patterns/prompt-caching-2026.md` — caching changes the cost model

## Source URLs (verified 2026-08-10)

- https://iternal.ai/llm-selection-guide
- https://ianlpaterson.com/blog/llm-benchmark-2026-38-actual-tasks-15-models-for-2-29/
- https://techbytes.app/posts/2026-llm-selection-matrix-workload-matching/
- https://www.salttechno.ai/datasets/llm-model-comparison-2026/
- https://ranksaga.com/blog/llm-benchmark-wars-2025-2026/
- https://www.vellum.ai/llm-leaderboard
