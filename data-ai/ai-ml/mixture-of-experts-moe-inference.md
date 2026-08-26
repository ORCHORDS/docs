# mixture-of-experts-moe-inference

**Issue:** Mixture-of-Experts (MoE) models now dominate the open-weight landscape — Qwen3-30B-A3B, Mixtral 8x7B, DeepSeek-V3, gpt-oss — because they decouple total parameter count from per-token compute. But the same sparsity that makes them cheap to run makes them weird to operate: total weights are huge (all experts must live somewhere), per-token cost is small (only a few experts fire), and router behavior interacts with batching, parallelism, and quantization in ways dense-model intuition gets wrong. Engineers who size VRAM, pick serving flags, or estimate cost using dense-model math will either overspend or OOM. This article captures how MoE changes the inference math and what to do about it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How MoE changes the inference math

1. **Total vs active parameters.** A 30B-A3B model stores ~30B weights but activates ~3B per token. Memory footprint follows total parameters; compute (tokens/sec, FLOPs) follows active parameters. Sizing one from the other is the classic MoE mistake.

2. **VRAM is bounded by all experts.** Every expert must be resident (GPU or offload tier) before routing can happen, so model memory is roughly total-params x bytes-per-weight, same as a dense model of the same total size. A "small-feeling" 3B-active model does not fit like a 3B dense model.

3. **Throughput scales with batch.** With a batch of 1, sparsity wins are modest; with large batches, different tokens route to different experts, so effective FLOPs per token stay near the active count while the GPU stays busy. MoE economics are best under concurrent load, not serial single-user chat.

4. **Router load imbalance is real.** Natural language concentrates certain experts (code, specific languages, common patterns). Hot experts become throughput bottlenecks and cold experts waste resident memory. Expect skewed expert utilization and measure it rather than assuming uniform routing.

5. **Cost accounting must use active parameters.** For provider APIs priced per token this is invisible, but for self-hosted cost-per-million-tokens calculations, divide GPU cost by measured tokens/sec under production batch mix — not by vendor benchmark numbers produced at max batch.

## Serving stack configuration

1. **Expert parallelism (EP) over naive tensor parallelism.** vLLM and SGLang both support EP, which shards experts across GPUs instead of slicing every expert. For single-node multi-GPU MoE, combine tensor parallelism (attention) with EP (experts) rather than pure TP; the vLLM MoE playbook for ROCm documents the TP/DP/PP/EP combinations that actually help.

2. **Quantize experts first.** Experts are the bulk of the weights and are activated sparsely, so Q4/Q8 quantized experts with higher-precision attention ("quantization-aware" mixes) preserve quality while cutting the memory bill. Measure quality on your own eval set — router sensitivity to weight perturbation varies by model.

3. **Pick the server by benchmark, not vibes.** MoE-CAP (arXiv 2412.07067) benchmarks cost, accuracy, and performance across vLLM, SGLang, MoE-Infinity, K-Transformer, and vanilla Transformers. SGLang sometimes beats vLLM on MoE throughput and sometimes loses (a Qwen3-30B-A3B case on Ascend NPUs showed SGLang ~23% slower); there is no universal winner, so run the benchmark harness on your hardware.

4. **Use fused MoE kernels.** Both vLLM and TensorRT-LLM shipped MoE-specific kernel optimizations through 2025 (fused grouped GEMMs, expert dispatch). Running an MoE checkpoint through generic dense kernels silently costs multiples of throughput. Verify the server logs the fused path for your model.

## Running big MoE on small hardware

1. **Expert offloading is the main lever.** Systems like MoE-Lightning (ASPLOS 2025) hit up to 10.3x higher throughput than prior offloading systems for Mixtral 8x7B on a single T4 by streaming cold experts from CPU/NVMe while keeping hot ones on-GPU. vLLM's cpu_offload_gb achieves a simpler version of this.

2. **Cache-aware routing helps at the edge.** Research systems (MoE-Infinity, Mixtral-offloading line) exploit temporal locality — consecutive tokens in a conversation hit overlapping expert sets — to keep the working set small. This is why interactive use offloads better than random workloads.

3. **KV-cache offloading compounds with expert offloading.** LMCache-style in-process KV offloading combined with data parallelism reported ~10x MoE inference boosts in 2026. Long-context MoE serving is usually KV-bound before it is expert-bound; tune both.

4. **Prefer more-active-params over more-total-params under 16GB.** On a small card, a dense 8B or a 30B-A3B at Q4 both fit, but the MoE gives dense-14B-ish quality at dense-3B speed — provided experts fit. If they do not fit and you cannot offload, the dense model wins on latency consistency.

## Failure modes and pitfalls

1. **OOM at batch peaks, not at load.** Expert workspace buffers and activation memory scale with concurrent tokens routed per expert. A server that loads fine can OOM minutes later under bursty load; load-test at production concurrency before declaring capacity.

2. **Quality regression from expert quantization hides in aggregate evals.** Routing is a hard argmax — small weight changes can flip token routing and compound. Evaluate with per-domain slices (code, math, long-tail languages) not just aggregate benchmarks after any MoE quantization change.

3. **Speculative decoding interplay.** Draft-model acceptance with MoE targets is cheaper per draft token but routing overhead per verification batch can dominate at small batch. Benchmark speculation on/off for your MoE specifically; dense-model speculation intuition transfers poorly.

4. **Fine-tuning touches routers.** LoRA on MoE layers or any router-affecting training shifts expert load balance; a fine-tune that improves quality can degrade serving throughput. Re-measure expert utilization after fine-tuning, not just eval scores.
