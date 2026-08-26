# llm-inference-serving-vllm

**Issue:** Calling a hosted API is the right start, but the moment you self-host an open model — for cost at scale, data control, latency, or offline operation — the naive approach (HuggingFace transformers with a FastAPI wrapper) wastes 80-95% of the GPU. Production LLM serving engines solve a systems problem: packing many concurrent requests onto a finite KV cache (PagedAttention), starting new requests the instant older ones finish (continuous batching), reusing shared prefixes (prefix caching), and exposing it all through an OpenAI-compatible API so existing clients switch by changing a base URL. vLLM is the ecosystem default, with SGLang as the strongest alternative for agentic, prefix-heavy workloads; choosing between them and tuning the deployment is a 2025-2026 core infrastructure skill.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Engine selection

1. **vLLM as the default.** Broadest model support (200+ HF architectures including Llama, Qwen, Gemma, DeepSeek, Mamba, multimodal), runs across NVIDIA, AMD, CPUs, TPU, Gaudi, and Apple Silicon, with an OpenAI-compatible server as the primary interface. The V1 engine is now the main codebase, shipping chunked prefill, prefix caching, and speculative decoding by default.

2. **SGLang when prefix reuse dominates.** SGLang's RadixAttention caches KV across requests in a radix tree, giving it an edge on agentic and multi-turn workloads where the same system prompt and conversation prefix recur — the pattern behind most coding-agent traffic. Community benchmarks repeatedly show SGLang ahead on prefix-heavy serving; vLLM's automatic prefix caching narrows the gap, so benchmark your own trace.

3. **TGI and commercial engines.** HuggingFace TGI remains viable, and NVIDIA TensorRT-LLM (vLLM adopts its kernels via TRTLLM-GEN) offers peak per-GPU performance at higher integration cost. Treat engine choice as revisitable: the OpenAI-compatible API boundary makes switching cheap by design.

4. **GGUF/llama.cpp is a different tier.** For single-user or low-concurrency local inference, llama.cpp beats everything on convenience and CPU/Metal support. vLLM-class engines only pay off with concurrent requests batching — do not deploy one to serve a single interactive user.

## Core performance features to understand

1. **PagedAttention.** KV cache memory is managed in blocks like OS virtual memory instead of contiguous pre-allocation, eliminating most fragmentation and over-reservation. This is the foundational trick that made high-concurrency LLM serving economical.

2. **Continuous batching.** The scheduler admits and retires requests at every decode step instead of waiting for a batch to finish, so one long generation no longer stalls a queue of short ones. It is the single biggest throughput multiplier over static batching.

3. **Chunked prefill.** Long prompts are processed in time-sliced chunks interleaved with decoding, smoothing the latency spike a huge prompt otherwise injects into every co-running request.

4. **Prefix caching.** Identical prefixes (system prompts, few-shot blocks, agent scaffolding) are cached and reused across requests, cutting time-to-first-token dramatically for templated traffic. Verify it is enabled (in vLLM V1 it is on by default) and structure prompts so the stable prefix comes first.

5. **Speculative decoding.** Draft-then-verify decoding (n-gram, EAGLE, MTP methods in current vLLM) trades extra compute for 2-3x lower latency on single-stream work; it is latency medicine, not throughput medicine, since batched serving usually prefers the compute for more concurrency.

## Capacity planning and tuning

1. **gpu-memory-utilization and max-model-len.** Set memory utilization around 0.90 (leave headroom for activation spikes) and cap max-model-len to what your traffic actually needs — KV cache capacity, hence concurrent sequences, scales inversely with maximum context length. An unneeded 128k context window halves your throughput.

2. **max-num-seqs as the concurrency dial.** Cap concurrent sequences to keep per-request decode speed acceptable; total throughput keeps rising with batch size, but individual token latency degrades once the GPU saturates. Pick the point from your SLO, not from the default.

3. **Compute your KV cache budget.** Usable cache equals GPU memory minus model weights; divide by per-token KV bytes (which grow with context length and model width) to get the token capacity the scheduler can pack. This arithmetic, not vendor numbers, predicts real concurrency.

4. **Scale horizontally with a router.** Put LiteLLM, an AI gateway, or a Kubernetes operator in front of multiple vLLM replicas for load balancing, retries, and model routing. The OpenAI-compatible API makes every replica interchangeable.

## Quantization and parallelism

1. **Quantize for density.** vLLM supports FP8, MXFP4/MXFP8, NVFP4, INT8, INT4, GPTQ, AWQ, GGUF, and compressed-tensors. FP8 on Hopper-plus GPUs is the high-quality default; 4-bit variants (AWQ/GPTQ/NVFP4) halve memory again at modest accuracy cost — always rerun your eval suite on the quantized artifact before serving it.

2. **Tensor parallelism within a node.** Splitting a model across multiple GPUs (tensor-parallel size 2/4/8) is required for models exceeding one GPU's memory and boosts per-request speed at the cost of inter-GPU communication; keep it intra-node where NVLink exists.

3. **Pipeline, data, and expert parallelism for larger topologies.** vLLM supports pipeline and data parallelism, plus expert and context parallelism for MoE and long-context models. Reach for multi-node setups only after quantization and batching have been exhausted.

4. **Disaggregated prefill/decode.** The 2025-era scaling pattern runs prefill and decode on separate pools matched to their differing compute profiles — relevant at large scale, and useful background even when your deployment fits one box.

## Serving API and ecosystem

1. **OpenAI-compatible first.** The bundled server speaks the chat/completions and completions APIs, so existing client SDKs, gateways, and fallback logic work unchanged. vLLM also ships an Anthropic Messages API and gRPC for other integration styles.

2. **Tool calling needs parsers.** Tool-call support depends on reasoning/chat parsers matching your model family; verify tool-call and structured-output behavior (xgrammar/guidance backends) on your specific model before standardizing clients against it.

3. **Multi-LoRA serving.** vLLM can serve many LoRA adapters over one base model in a single process — often cheaper than merging or replicating when you need per-tenant fine-tunes (see the lora-qlora article for training; this is the serving side).

4. **Observe engine metrics.** Export Prometheus metrics (token throughput, cache hit rate, queue depth, prefill vs decode time) from the engine. Cache-hit and queue metrics are the leading indicators that prefix layout or capacity tuning is off.
