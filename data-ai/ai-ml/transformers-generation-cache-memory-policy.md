# Transformers Generation-Cache Memory Policy

**Issue:** Dynamic, static, offloaded, and quantized generation caches trade latency, compilation behavior, device memory, and precision differently. A silent cache change can cause OOM or latency regressions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Select cache implementation explicitly per model and workload.
- Benchmark prompt length, batch size, beams, device memory, host memory, and transfer bandwidth.
- Version cache configuration with the serving artifact and capacity model.
- Fail safely when offload or quantization support is unavailable.

## Verification

- Measure first-token and total latency across representative sequence lengths.
- Drive device and host memory near limits and verify controlled rejection.
- Compare generated outputs where cache quantization may affect numerics.

## Gotchas

- A cache reduces repeated key/value computation, not model weight memory.
- Offloading can replace device OOM with transfer-bound latency.

## Official sources

- https://huggingface.co/docs/transformers/kv_cache
