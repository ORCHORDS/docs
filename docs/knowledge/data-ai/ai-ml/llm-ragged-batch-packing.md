# LLM Ragged Batch Packing

Real LLM traffic is ragged: prompts and generations of wildly different lengths arrive together, but accelerator kernels want rectangular tensors. Serving engines resolve the mismatch by padding every sequence in a batch to the longest member — paying compute and memory for phantom tokens — or by packing multiple short sequences into shared rows with careful attention masking. Packing done correctly reclaims most of the waste; done incorrectly, it silently corrupts generation by letting sequences attend to each other's tokens.

## Scope

This article covers ragged batch handling in LLM inference: the mechanics of padding waste, sequence packing with block-diagonal attention masks, correct masking as the primary correctness control, and the measurement discipline to know whether packing is paying. It targets engineers operating or evaluating inference engines.

Excluded: training-time sequence packing (same math, different constraints and risk tolerance), paged attention memory management as such, and batching-scheduler policy, which interacts but is a separate discipline.

One framing note: padding waste is worst precisely where serving economics hurt most — short-prompt, short-generation workloads (classification, extraction, routing) — because a 30-token request padded into a batch with a 2,000-token request spends 98.5 percent of its row on nothing. High-volume short-request services benefit from packing disproportionately.

## Workflow or implementation guidance

1. **Quantify current padding waste.** From logged request lengths, compute tokens-paid versus tokens-used at your engine's batching behavior: sum over batches of (batch-max-length × batch-size) against sum of true lengths. This number, not intuition, decides whether packing work is justified. Services dominated by long, uniform requests may see single-digit waste and should stop here.
2. **Understand the engine's native options before building anything.** Modern engines implement paged attention and ragged kernels that already avoid classic rectangular padding; some additionally pack prefill sequences or offer chunked prefill. Know exactly what your version does before adding custom logic — double packing on top of engine packing adds complexity for no gain.
3. **If packing is implemented, treat the mask as the deliverable.** Packing correctness lives entirely in the attention mask: each token may attend to positions belonging to its own sequence only, plus permitted shared context if the design deliberately shares prefixes. A mask that lets sequence B attend to sequence A's tokens produces fluent nonsense — the model incorporates foreign context and output quality degrades without any error being raised.
4. **Bound packing aggressiveness.** Packing until every row is full maximizes utilization but delays admission: short requests wait to fill slots. As with batch formation generally, derive the packing window from the latency objective; a small un-utilized margin is cheaper than queue delay.
5. **Keep position identifiers straight.** Packed sequences need position embeddings restarted per sequence (or an equivalent scheme matching the model's expectations). Off-by-one errors here produce subtle quality damage that only task-level evaluation catches — a packed and unpacked run of the same evaluation suite should match within tolerance.
6. **Validate with paired runs.** Route a fixed evaluation set through packed and unpacked paths and compare outputs. Distribution shifts beyond tolerance mean a masking or position-id defect. Repeat this check on every engine upgrade; packing bugs are rare but catastrophic and silent.

## Controls

- **Padding-waste metric.** Tokens-paid/tokens-used ratio from production sampling; a rising trend signals batch composition drift that packing (or scheduler tuning) should address.
- **Paired-output equivalence testing in CI.** The evaluation suite runs both paths on engine upgrades; material divergence blocks promotion.
- **Packing-ratio telemetry.** Average sequences per row and slot utilization, confirming packing is actually filling rows rather than adding overhead at low occupancy.
- **Latency guardrails.** Time-to-first-token percentiles watched after enabling packing; admission-delay regressions are caught here rather than in user complaints.
- **Mask construction review.** Any change to masking logic (new shared-prefix optimization, format change) requires review against a documented mask specification — this is the highest-risk code in the path.

## Validation evidence

- Before/after utilization and cost measurements: padding-waste ratio, throughput at matched offered load, and GPU memory headroom, with traffic composition recorded so the comparison is reproducible.
- Paired evaluation results: packed versus unpacked task scores and output-diff statistics on identical inputs and seeds, demonstrating equivalence within tolerance.
- Latency percentiles across the rollout window, showing no tail regression from admission delay.
- Mask unit evidence: for each mask variant in production, documented expected-attention structure and unit tests asserting blocked cross-sequence attention at boundaries.

## Failure modes and correction

- **Cross-contamination via mask defects.** Sequences see each other's tokens; outputs become subtly wrong with no exception raised. Correction: paired equivalence tests in CI catch it on the next run; immediately disable packing and rerun affected-traffic quality sampling to bound the damage window.
- **Position-identifier drift.** Position embeddings continue across packed boundaries; model quality degrades on position-sensitive tasks (long-context recall, counting). Correction: per-sequence position reset verified in unit tests and the paired evaluation gate.
- **Admission delay creep.** Aggressive packing waits to fill rows; first-token latency rises. Correction: cap the packing window by latency budget; accept partial rows when the window expires.
- **Double-packing overhead.** Custom packing layered over an engine that already handles ragged batches adds serialization and mask cost with no utilization gain. Correction: measure before building; remove custom logic where the engine's native path suffices.
- **Skewed batch composition.** A few very long requests make packing decisions that starve short-request admission (or vice versa after a "fix"). Correction: length-class segregation — separate pools or scheduler classes for short and long traffic so packing optimizes within similar lengths.

## Limitations

Engine capabilities are the moving target: paged attention, ragged kernels, and native packing differ by engine and version, so the binding guidance is each engine's current documentation. Realized savings depend heavily on traffic-length distribution; published packing gains from uniform benchmarks do not transfer. This article addresses inference only, and it assumes the evaluation suite used for equivalence testing is itself adequate — a weak suite validates nothing. Mask-optimization variants (shared-prefix attention, block-sparse schemes) add correctness conditions beyond plain packing and need their own specifications.

## Canonical sources

- vLLM documentation, Automatic Prefix Caching related memory design: https://docs.vllm.ai/en/latest/design/v1/prefix_caching.html
- PyTorch documentation, Nested Tensors: https://pytorch.org/docs/stable/nested.html
