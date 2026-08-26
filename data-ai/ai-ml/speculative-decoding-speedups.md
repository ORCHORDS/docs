# speculative-decoding-speedups

**Issue:** Autoregressive decoding generates one token per forward pass — the GPU sits mostly idle waiting on memory bandwidth, and local inference on a single card feels slow no matter how good the model is. Speculative decoding attacks exactly this bottleneck: a cheap guesser drafts several tokens, the big model verifies them in one pass, and accepted tokens come out free. Teams either have never tried it or enable it blindly and get no speedup (or a slowdown) because it is extremely workload-dependent. This article covers the variants, the numbers reported in 2025, and when it helps.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How it works and why it is safe

1. **Draft-then-verify.** A small draft model (or attached head, or n-gram matcher) proposes K tokens; the target model runs them all through in a single forward pass and accepts the longest prefix it agrees with, resampling the first disagreement. Outputs are drawn from the target model's own distribution — quality is provably unchanged, only speed varies.
2. **The speedup math.** Wall-clock win ≈ (accepted tokens per verification) / (1 + draft overhead). If the draft accepts 3 of 5 proposed tokens cheaply, you approach ~2-3x; if it accepts 0-1, you paid draft compute for nothing and run slower.
3. **Acceptance rate is everything.** It depends on how well the guesser matches the target's distribution — same family (Qwen draft for Qwen target) accepts far better than cross-family pairs. EAGLE-3's feature-fusion improvements raised acceptance by 6-12 percentage points over prior methods on Llama and Qwen models.
4. **It exploits the memory-bandwidth bottleneck, not FLOPs.** Verifying K drafted tokens costs about the same memory traffic as generating one — that is why the trick is nearly free per attempt. It also means gains shrink as batch size grows (batching already fills the GPU), so this is a single-user/small-batch technique.

## The variant landscape (2025 state)

1. **Classic draft-model spec decoding.** Run a 0.5-3B sibling alongside the target (llama.cpp `-md`, vLLM `speculative_model`). Simple, works today, but needs a good small model in the same family and doubles model management.
2. **EAGLE-3 (attached head).** Trains a lightweight head on the target's hidden states; vLLM supports it (`speculative_algorithm: eagle3`) with up to ~2.5x speedups reported by Red Hat, and 3-4x on well-matched GPU deployments. Best current trained-head option; requires a published EAGLE head for your exact model.
3. **Medusa (multiple decode heads).** Extra heads on the target itself propose tokens in parallel — no separate draft model to load, but acceptance rates generally trail EAGLE-style methods.
4. **N-gram / self-speculative.** No draft model at all: guess from n-grams already in the prompt/context. vLLM ships an n-gram speculator; llama.cpp favors this route (layer-skipping, draft-from-context). Wins big on tasks that copy or transform prompt text (summarization, extraction, code editing) and does nothing for open-ended generation.
5. **Meta's EAGLE-at-scale (arXiv 2508.08192).** Documents EAGLE-based speculative decoding serving Llama models in production — the pattern is proven at scale, not just a paper curiosity.

## When it helps — and when it hurts

1. **Best case: batch-size-1 local coding agents.** Greedy-ish decoding (low temperature), structured output, heavy prompt-referencing — acceptance is high and idle GPU capacity is maximal. This matches the local fleet's daily-driver profile.
2. **Second best: streaming chat on a single card** where TTFT is hidden by prompt caching and per-token rate dominates perceived speed.
3. **Neutral-to-bad: high batch serving.** With 16+ concurrent sequences the GPU is already compute-saturated; verification adds work and throughput per GPU drops. Turn it off for throughput-oriented endpoints.
4. **Bad: draft from a different family than the target.** Cross-family acceptance rates collapse; you carry a useless second model in VRAM. The draft must share tokenizer at minimum, ideally a distilled ancestor.
5. **Bad: high-temperature creative generation.** Divergent sampling lowers prefix agreement between drafter and target, dropping acceptance; speedups evaporate.
6. **Measure, do not assume.** Bench tok/s with the same prompts and seed on/off. Real-world vLLM EAGLE results (~1.5x in mixed workloads) trail headline 2.5-4x numbers; llama.cpp single-user gains are modest. One hour of benchmarking decides.

## Anti-patterns

1. **Enabling spec decoding globally on a shared multi-user endpoint** — batch saturation turns speedup into slowdown.
2. **Pairing a random small model as drafter because it is small** — tokenizer mismatch or distribution mismatch silently produces 1-2% acceptance and negative net speed.
3. **Expecting quality changes.** Verification guarantees the target's distribution; if outputs got worse, the bug is elsewhere (usually the draft model's template applied to the target).
4. **Skipping it because "the model is already fast enough"** on a batch-1 local agent — it is the cheapest 1.5-2x on the table for the exact workloads the fleet runs, no quality risk attached.
