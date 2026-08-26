# webgpu-compute-offload

**Issue:** CPUs are the wrong tool for large parallel math, yet browser apps keep doing image processing, physics, signal filtering, embeddings reranking, and increasingly small-model ML inference on the main thread or in Web Workers. WebGPU, shipping in Chromium browsers and progressively elsewhere through 2025-2026, exposes modern GPU APIs (Vulkan/Metal/D3D12 semantics) to the web with first-class compute shaders and dramatically lower CPU-side driver overhead than WebGL. For throughput workloads it is often 5-50x faster than JS, but it carries real costs: async pipeline compilation, memory transfer bottlenecks, and a dual-code-path maintenance burden wherever WebGL or CPU fallbacks are still required. Deciding what to offload, and budgeting the upload/readback round trips, is the actual engineering problem.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why WebGPU changes the offload calculus

1. **First-class compute shaders.** WebGL only has vertex and fragment stages, forcing GPGPU hacks like packing data into float textures and reading results via render-to-texture. WebGPU compute shaders express parallel algorithms naturally, with storage buffers and workgroups, which removes the packing/unpacking overhead entirely.
2. **Lower CPU driver overhead.** WebGPU's command encoding model (command buffers recorded once, submitted together, with explicit pipeline lifetimes) eliminates the per-draw WebGL validation overhead. Academic comparisons (DiVA 2024) and Chrome's migration guide both show meaningfully lower CPU cost per frame, which matters as much as GPU throughput on main-thread-sensitive apps.
3. **In-browser ML inference.** Matrix multiplication for transformer inference maps directly to compute shaders; benchmarks (e.g., SitePoint's WebGPU vs WebGL inference tests) show WebGL struggling where WebGPU sustains usable token throughput for small in-browser models. This is the backend story behind WebLLM-style local inference.
4. **Realistic expectations.** WebGPU is not uniformly faster: for simple scenes WebGL's long-optimized shader compilers sometimes win, and WebGPU pipeline creation has its own async costs. The decisive wins are compute workloads and CPU overhead reduction, not a blanket 2x on everything.

## The transfer bottleneck

1. **Upload and readback dominate small jobs.** mapAsync on a GPUBuffer is async and can stall for a frame or more; if your workload runs in 2 ms on the GPU but you pay 8 ms of upload plus a readback round trip, a Worker with plain JS wins. Batch many items per dispatch, not one item per dispatch.
2. **Keep data resident on the GPU.** The ideal pipeline uploads once, chains multiple compute passes via storage buffers, and reads back only a final reduced result (a sum, a top-k, a bounding box). Every staging buffer copy you remove is measurable latency.
3. **Prefer pull-based readback.** Issue copyTextureToBuffer/writeBuffer to a mapped-at-creation or MAP_READ staging buffer and read it on the next frame, rather than blocking the current frame on mapAsync resolution. Double-buffer staging allocations to avoid stalls.

## Pipeline and startup costs

1. **Async compilation by default.** createComputePipelineAsync avoids hitching while the driver compiles; synchronous createComputePipeline can block for tens of ms per pipeline. Build all pipelines during app idle time (via requestIdleCallback or a startup Worker message), not on first interaction.
2. **Pipeline caching across reloads.** Chrome's pipeline cache makes repeat visits cheaper, but cold-load shader compilation is still a real cost for large shader libraries; ship the smallest set of variants you need and consider generating permutations offline.
3. **Device loss handling.** A lost device means every resource is gone; implement re-initialization and re-upload paths, and make sure a device-lost error in a demo path does not take down the whole page. This is a correctness requirement that doubles as resilience engineering.

## Fallback strategy

1. **Feature-detect, do not UA-sniff.** Check navigator.gpu, request an adapter, and fall back to WebGL2 (with GPGPU texture tricks) or a Web Worker CPU path. WebGL is not being deprecated and remains the compatibility floor through 2026; Firefox and Safari WebGPU support has been rolling out unevenly, so the fallback path is not optional.
2. **Shared algorithm, three backends.** Write the algorithm once against a small dispatch interface (prepare inputs, run, fetch outputs) and implement CPU, WebGL, and WebGPU backends behind it. This keeps the fallback testable instead of rotting.
3. **Validate numerics per backend.** GPU float behavior (fast-math, fused operations) differs from CPU; golden-vector tests per backend prevent "works on my GPU" bugs from reaching users.

## When WebGPU is the wrong call

1. **Small or infrequent work.** Anything under roughly a millisecond of CPU math is cheaper on the CPU than the dispatch machinery. Profile the JS implementation first; only offload when profiling shows the math dominating frame budget.
2. **Latency-sensitive single results.** If users await one result synchronously (one image filter applied once), GPU readback latency can make the experience worse than a Worker. Batch or pipeline workloads before reaching for the GPU.
3. **Battery-constrained mobile contexts.** Full GPU utilization drains battery; consider an adaptive quality path that lowers workgroup counts or falls back to CPU on devices reporting low power or save-data mode.
