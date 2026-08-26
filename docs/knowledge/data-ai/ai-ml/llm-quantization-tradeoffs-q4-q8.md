# llm-quantization-tradeoffs-q4-q8

**Issue:** Local LLM deployments default to "grab the Q4 file and go" without understanding what each quantization level actually costs in quality, speed, and VRAM. Teams either over-provision (wasting half the GPU on Q8_0 for a chat bot) or under-provision (Q2/Q3 wrecking a coding model's indentation and tool-call syntax). The vram-budget article covers the arithmetic of what FITS; this article covers the separate question of what each quant level DESTROYS, and how to pick the right point on the size-quality curve deliberately.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What each quant tier actually costs

1. **Q8_0 is effectively lossless.** Perplexity increase over FP16 is around +0.01 (e.g. 6.00 → 6.01) — indistinguishable in normal use. The cost is purely size: ~1 byte per weight, so a 32B model is ~32GB before KV-cache. Use it as the reference baseline when validating that observed problems are NOT quantization-related.
2. **Q6_K is the conservative sweet spot when VRAM allows.** Quality loss is measurable but negligible for most tasks, at ~75% of the Q8 file size. Good default for dense models that comfortably fit.
3. **Q4_K_M is the standard workhorse.** Averages ~4.5 bits per weight by keeping the most sensitive layers at 6-bit, recovering roughly 5-8% quality versus plain Q4_0 at near-identical size. This is the right default when the bigger quant does not fit.
4. **Below Q4 quality falls off a cliff.** Q3 and Q2 quants exist for extreme VRAM constraints, but coding ability, instruction following, and structured output (JSON, tool-call syntax) degrade non-linearly. A Q2 model that "works" on chat will silently produce malformed tool calls.
5. **The dominant rule: a bigger model at Q4 beats a smaller model at Q8.** Model size matters more than quantization precision. When choosing between 30B@Q4 and 14B@Q8 on the same VRAM budget, take the 30B almost every time.

## K-quants, I-quants, and the imatrix

1. **K-quants (Q4_K_M etc.) super-block scale across tensor types.** They adapt block sizes per tensor and keep attention/output layers at higher precision — that is where the "M" (medium, mixed) suffix quality recovery comes from.
2. **I-quants (IQ4_XS, IQ4_NL etc.) give better quality per byte when calibrated.** They use non-linear codebooks and shine at 2-4 bit ranges, but their quality depends heavily on having a good importance matrix baked in at quantization time.
3. **An imatrix (importance matrix) calibrates quantization to real data.** Quantizers weighted by an imatrix computed from representative calibration text (project domain data, code, docs) preserve the weights that matter for YOUR workload. Without one, quantization noise lands uniformly and hurts sensitive layers.
4. **Calibration data must match deployment data.** An imatrix built from Wikipedia-style text will mis-weight a model used for code generation. Spend the 10 minutes generating it from your actual corpus.
5. **Benchmark noise is real at small deltas.** Differences between adjacent quant levels (Q4_K_S vs Q4_K_M) are within run-to-run variance of many community benchmarks — do not cargo-trade one step up or down based on a single leaderboard cell.

## Verifying quality before committing

1. **Run perplexity on your own corpus, not the published one.** A quick llama.cpp `perplexity` pass over a few MB of representative text catches gross damage; published numbers are for other people's data.
2. **Test the tasks you actually ship, especially structured output.** Quantization damage shows up first in the hardest formatting constraints: valid JSON, tool-call grammar, code indentation. A 20-prompt smoke suite of your real task beats any generic benchmark.
3. **Compare against FP16/Q8 ground truth on the same prompts.** Diff the outputs; if the Q4 output is semantically equivalent, ship it. If it drifts on 10%+ of prompts, step up one tier.
4. **Watch MoE models specially.** Sparse mixture-of-experts models tolerate Q4 on routed experts better than dense models, but shared attention layers at low quant hurt every token — prefer quant mixes that keep attention heavy.
5. **Re-verify on every model upgrade.** Quantization sensitivity varies per model family and per training run; a "Q4_K_M is always fine" rule inherited from the previous model does not transfer.

## Anti-patterns

1. **Defaulting to Q8 "for safety" on a VRAM-constrained card** — it halves the model size you could be running, and the bigger model at Q4 wins.
2. **Shipping Q2/Q3 to fit a model that does not belong on that hardware** — the honest fix is a smaller model or routing to cloud, not a strangled big one.
3. **Grabbing uncalibrated community quants for a specialized domain** — no imatrix means quantization noise lands where your domain cares most.
4. **Judging quants by vibes on three chat prompts** — chat hides damage; your JSON/tool-call suite exposes it. Test the fragile surfaces.
