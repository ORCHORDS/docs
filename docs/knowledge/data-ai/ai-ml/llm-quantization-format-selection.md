# LLM Quantization Format Selection

Quantization trades numerical precision for memory, speed, and cost. Halving weight precision roughly halves weight memory and often raises achievable batch sizes and decode throughput. The trade is not free: each step down in precision risks task-specific accuracy loss, and the ecosystem's formats — INT8, FP8, INT4, and weight-only schemes like AWQ and GPTQ — differ in how they protect accuracy, what hardware they require, and how they fail. Choosing among them is a decision with an evidence file, not a default.

## Scope

This article covers selecting and validating quantization for deployed LLM inference: the practical differences between precision families, calibration methodology for weight-only schemes, and the accuracy gates that must pass before a quantized model serves traffic. It addresses practitioners deploying open-weight models on their own infrastructure.

Excluded: quantization-aware training and fine-tuning recovery techniques (model-development territory), KV-cache quantization (a separate decision with different failure modes), and provider-side serving where quantization is invisible to the operator.

The decision landscape in one view: FP8 and INT8 are numerical-precision reductions usually applied broadly; INT4-class weight-only methods (AWQ, GPTQ) quantize weights to 4 bits while keeping activations at higher precision, protecting accuracy via calibration against representative data. Lower precision is not automatically faster on all hardware — kernel support determines realized speed, which must be measured, not assumed.

## Workflow or implementation guidance

1. **Start from the constraint, not the format.** Identify the binding constraint: memory capacity (model must fit), memory bandwidth (decode is bandwidth-bound), or hardware kernel support. A 4-bit format that fits the memory budget but has no optimized kernel for your accelerator delivers capacity without speed. List candidate formats that satisfy the constraint before comparing accuracy.
2. **Shortlist by hardware and engine support.** Confirm which quantization paths your inference engine actually accelerates on your specific hardware generation. Support matrices change per release; a format that is nominally supported but falls back to dequantize-then-compute can be slower than the unquantized baseline. Verify with the engine's documentation for your exact versions.
3. **Prepare a calibration set for weight-only schemes.** AWQ and GPTQ derive their scaling from calibration data. Use text drawn from the target distribution — the languages, domains, and instruction formats the model will actually see. Calibrating a code model on news prose, or a multilingual deployment on English-only data, shifts error onto the unrepresented distribution. Keep the calibration set versioned and documented.
4. **Build the evaluation gate before quantizing.** Select task suites matching production use: language coverage, long-context behavior if relevant, and at least one adversarial or edge-case suite. Record the unquantized baseline's scores on identical inputs. The gate is defined in advance so the decision is not reverse-engineered from a pleasing number.
5. **Quantize, evaluate, and compare distributions, not averages.** Run the gate on each candidate. Mean quality deltas near zero can conceal large per-category regressions — a language that degrades sharply while others improve. Inspect per-slice results and set per-slice thresholds, not just aggregate ones.
6. **Measure realized performance.** Benchmark memory footprint, time-to-first-token, inter-token latency, and peak throughput at production-like batch shapes on the target hardware. Compare against the baseline and against the theoretical gain; kernel overheads frequently eat a chunk of it.
7. **Record the decision.** The evidence file holds: format, bit width, calibration set version, engine and kernel versions, per-slice evaluation results, and performance measurements. Re-run the gate when the engine, hardware, or model version changes — quantization quality is not stable across kernel or implementation updates.

## Controls

- **Per-slice accuracy thresholds.** Each task slice has a maximum acceptable regression relative to the unquantized baseline; any slice breaching its threshold blocks rollout regardless of aggregate scores.
- **Calibration set governance.** The calibration corpus is versioned, access-controlled, and reviewed for representativeness; changes to it trigger re-evaluation because they alter the quantized model's error profile.
- **Deterministic rebuild.** The quantization pipeline (model checkpoint, calibration data, method parameters, engine version) is fully specified so the artifact can be rebuilt and its provenance audited.
- **Staged rollout with quality sampling.** Quantized models roll out behind sampling comparison or shadow traffic; production outputs are spot-checked against the baseline on a fixed schedule during the first weeks.
- **Benchmark currency.** Performance claims cite engine and hardware versions; stale benchmarks are retired when versions change.

## Validation evidence

The evidence file proves both accuracy and speed claims:

- Evaluation tables per candidate: per-slice scores for quantized and baseline, deltas with thresholds, pass/fail per slice.
- Calibration documentation: dataset version, size, source distribution, and rationale for representativeness.
- Performance benchmarks: throughput, latency percentiles, and memory at stated batch shapes, with hardware and engine versions recorded; ideally re-verified by a second operator on a second machine.
- Regression behavior: at least one deliberately mismatched calibration (wrong domain) run once, documenting how far scores moved — this calibrates the sensitivity of the gate itself.

## Failure modes and correction

- **Aggregate-average camouflage.** Overall score holds while a language or task slice collapses. Correction: per-slice thresholds as rollout-blocking gates; investigate any slice outside tolerance even when the mean improves.
- **Calibration distribution mismatch.** Production traffic differs from calibration data; degradation appears only after launch. Correction: recalibrate with sampled production data (privacy-reviewed), re-run the gate, and version the new calibration set.
- **Phantom speedup.** The format is supported but unaccelerated on this hardware; memory shrinks but latency rises. Correction: benchmark before rollout and treat engine fallback paths as disqualifying for latency-sensitive serving; check kernel support for the exact accelerator.
- **Version-fragile quality.** An engine update changes kernels; accuracy or speed shifts silently. Correction: pin versions in deployment manifests and re-run the accuracy and performance gate on any engine or model update before promotion.
- **Threshold erosion.** Repeated "small" regressions accumulate across updates until quality is materially worse than the original baseline. Correction: track scores against the original unquantized baseline over time, not just against the previous quantized version.

## Limitations

Quantization outcomes are model- and task-dependent; results for one checkpoint do not transfer to another, which is why the evaluation gate is mandatory rather than advisory. Format support and performance characteristics differ across hardware generations and engine releases, so binding guidance lives in current engine and vendor documentation. This article covers weight quantization for inference only; it does not address training-time quantization, KV-cache precision, or the distinct behavior of mixture-of-experts routing under quantization, each of which follows different rules and deserves separate treatment.

## Canonical sources

- Hugging Face Transformers documentation, Quantization overview: https://huggingface.co/docs/transformers/en/quantization/overview
- vLLM documentation, Quantization and Optimized Kernels: https://docs.vllm.ai/en/latest/features/quantization/index.html
