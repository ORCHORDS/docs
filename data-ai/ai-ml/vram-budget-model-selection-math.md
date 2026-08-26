# vram-budget-model-selection-math

**Issue:** Teams pick a model by reputation ("GLM-5.2 is great") and only later discover it needs ~380GB of VRAM against the ~26GB the hardware has. Promises get made, then quietly walked back. The math must happen BEFORE committing to a model — computed, not vibes. Learned sizing the local fleet on a 12GB RTX 3060 + three laptops (2/4/8GB).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The math that must be done first

1. **Weight bytes = params × bytes-per-weight.** Q4 ≈ 0.5 B/param, Q8 ≈ 1 B/param, FP16 ≈ 2 B/param. A 30B at Q4 is ~15-18GB before anything else.
2. **Add KV-cache for your context length.** Cache grows with layers × context × width; 16k-32k contexts can add multiple GB — size for the TARGET context, not the demo context.
3. **Add activation/overhead headroom (~10-20%).** A model that "just fits" OOMs at peak attention.
4. **Compare against SUMMED local VRAM only if you accept cluster speeds** — 26GB across four machines over Wi-Fi is not 26GB on one card; tensor-split over Wi-Fi is unusable for big models, pipeline split is slow but possible.
5. **Divide by measured tok/s, not paper tok/s.** Measured warm speed on the actual card (e.g. 26.3 tok/s on a 30B-A3B MoE) sets what "usable" means.

## The decision table it produces

1. **Fits single card (12GB):** MoE sparse models (30B-A3B class at Q4) — fast, the daily driver for easy/medium tasks.
2. **Fits cluster pipeline-slow:** 32B dense at Q4 — "quality" tier when waiting is acceptable.
3. **Does not fit (380GB class):** frontier dense models — route to subscription/API paths instead; no local story exists.
4. **Never fits:** pretending quantization rescues a 380B — even Q1-Q2 artifacts exceed the hardware and destroy quality.
5. **The honest output is a routing table**, not a hero effort: local for what fits, cloud for what doesn't, with the boundary written down.

## Anti-patterns

1. **Naming a model before sizing it** — commitment precedes feasibility, and the walk-back wastes a session.
2. **Summing VRAM across machines as if it were one pool** — interconnect dominates; Wi-Fi tensor parallelism is a trap.
3. **Sizing weights only, forgetting KV-cache** — the model loads then OOMs on the first long context.
4. **Trusting vendor tok/s** — measure warm on your own hardware; cold-start and thermal states differ wildly.
5. **Treating "we'll offload to RAM" as free** — CPU-offloaded layers drop tok/s by an order of magnitude; sometimes correct for batch jobs, never for interactive.

## Related

- `llm-fallback-provider-rotation.md`
- `../lessons/` hardware-sizing post-mortems
