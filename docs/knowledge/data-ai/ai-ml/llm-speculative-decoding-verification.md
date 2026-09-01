# LLM Speculative Decoding Verification

Speculative decoding attacks the memory-bandwidth bottleneck of autoregressive decoding: instead of generating one token per forward pass, a cheap draft model proposes several tokens and the target model verifies them all in a single pass. Accepted tokens come at draft-model cost; the first rejected token tells the target model what the correct token was, so output distribution is provably identical to the target model alone. The mechanism is elegant — and its performance is dominated by one empirical number: the acceptance rate. When drafts are bad, speculation makes everything slower.

## Scope

This article covers the operational decision to deploy speculative decoding: how the draft/verify loop works, what determines acceptance rate, how to measure the real speedup, and the controls that keep a speculative setup from quietly degrading. It addresses operators of self-hosted LLM inference considering or running speculation.

Excluded: training draft models (draft-model selection and distillation is model development), multi-token prediction architectures built into the target model, and hardware-specific kernel scheduling, which is engine territory.

The distribution-preservation property deserves emphasis: with standard rejection sampling, speculative decoding's output is mathematically equivalent to the target model's — not approximately similar. That makes it a pure performance optimization, separable from quality evaluation, provided the implementation is correct and the verification actually runs on every batch.

## Workflow or implementation guidance

1. **Estimate acceptance rate before anything else.** Speedup ≈ (tokens per verified batch) / (draft cost + verify cost), and tokens per batch is governed by how often the draft agrees with the target. Measure draft/target agreement on representative traffic with the candidate draft model. Short, formulaic outputs accept well; open-ended creative or reasoning-heavy generation accepts poorly. If measured agreement is low, stop here — no configuration fixes a mismatched draft.
2. **Choose draft length deliberately.** Longer drafts raise the ceiling (more tokens per verify) but each extra drafted token beyond the typical acceptance point is wasted work. Derive the setting from the acceptance-length distribution, not from intuition: if acceptance collapses after two tokens, drafting five wastes three forward passes of draft compute on most requests.
3. **Account for the verification batch shape.** Verification processes drafted positions in parallel — one forward pass covering all draft tokens — so its cost is sublinear in draft length but not free. Realized speedup must be benchmarked end to end at production batch shapes; microbenchmarks at batch size one routinely overstate gains by wide margins.
4. **Segment traffic.** Apply speculation where it pays: classification, extraction, structured output, and short completions accept well. Apply it cautiously to long-form generation, where acceptance drops and per-request latency variance rises. Per-route or per-model speculation configuration is better than a global default.
5. **Benchmark honestly.** Compare speculative versus non-speculative on identical traces: inter-token latency, end-to-end latency, throughput at matched offered load, and — importantly — latency variance. Speculation adds a second source of variance (acceptance fluctuates per request), which shows in p99 even when p50 improves.
6. **Re-validate on model changes.** The draft is tuned to a target. Upgrading the target model without re-measuring acceptance can silently invert the speedup into a slowdown. Pair every target-model promotion with an acceptance-rate check in the rollout gate.

## Controls

- **Acceptance-rate telemetry.** Mean and distribution of accepted tokens per verification step, segmented by route and traffic class; a downward trend is the early signal of draft/target mismatch (usually after a target update).
- **Speedup regression gate.** Automated benchmark comparing speculative and non-speculative latency/throughput on a fixed trace, run on every engine or target-model change; material regression blocks promotion.
- **Variance monitoring.** p95/p99 latency watched specifically; speculation that improves mean while blowing tails needs reconfiguration or route scoping.
- **Kill switch.** Speculation toggleable per route without redeploying the model; disabling it must be a low-risk operational action exercised in drills.
- **Equivalence spot-checks.** Periodic sampling comparing speculative and non-speculative outputs on identical seeds/inputs for a small traffic slice, confirming the implementation preserves the target distribution in practice, not just in theory.

## Validation evidence

- Acceptance-length distribution on production-representative traces, per route, with the draft and target versions recorded.
- End-to-end benchmarks at production batch shapes: speculative versus non-speculative inter-token latency, end-to-end latency percentiles, and throughput, with hardware and engine versions cited.
- Variance analysis showing p95/p99 impact, since tail effects are the common hidden cost.
- Change-history evidence: acceptance and speedup re-measured after each target or engine update, demonstrating the gate operated rather than was documented.

## Failure modes and correction

- **Inverted speedup.** Low acceptance plus verification overhead makes everything slower, and because the model still produces correct output, nothing alerts. Correction: acceptance telemetry and the speedup regression gate; if speedup drops below break-even, the kill switch narrows or disables speculation.
- **Post-update mismatch.** A target-model fine-tune shifts its distribution; the old draft stops agreeing; latency degrades without any obvious incident. Correction: acceptance check as a mandatory promotion step for target updates.
- **Tail-latency blowout.** Mean improves while p99 worsens because acceptance variance compounds on unlucky requests. Correction: per-route scoping (speculation off latency-critical routes), shorter drafts to bound worst-case waste, or batch-shape limits.
- **Throughput interference at high load.** Draft compute competes with target compute for the same GPUs; under saturation, speculation's extra work reduces aggregate requests-per-second even where per-request latency improves. Correction: capacity planning treats speculation as a workload multiplier; benchmark at realistic load, not just at low concurrency.
- **Implementation drift.** An engine rewrite changes acceptance semantics (e.g., tree speculation variants, modified rejection sampling) and the old equivalence assumption quietly breaks. Correction: version-pinned equivalence spot-checks after engine upgrades.

## Limitations

Realized speedup is workload-, model-, and hardware-dependent; published numbers transfer poorly and must be re-derived per deployment. Draft-model availability constrains the approach — a well-matched small model for the target does not always exist, particularly for freshly released or heavily fine-tuned targets. Engine implementations differ (sequential drafts, tree-based speculation, prompt-lookup decoding), each with different overhead and acceptance characteristics, so binding mechanics live in current engine documentation. The distribution-equivalence guarantee holds only for correctly implemented rejection sampling with exact verification; engines that cut corners for speed (approximate verification, truncated sampling checks) void it, which the spot-check control exists to catch.

## Canonical sources

- vLLM documentation, Speculative Decoding: https://docs.vllm.ai/en/latest/features/spec_decode.html
- Hugging Face Transformers documentation, Assisted Generation: https://huggingface.co/docs/transformers/en/llm_optims#assisted-generation
