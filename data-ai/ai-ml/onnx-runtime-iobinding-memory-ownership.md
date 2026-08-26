# Define ONNX Runtime IOBinding Memory Ownership

**Issue:** IOBinding can avoid copies by binding device buffers directly, but incorrect device, dtype, shape, lifetime, or synchronization assumptions cause corruption or hidden fallback copies.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Record device type/id, element type, shape, pointer owner, allocation size, and lifetime for each binding.
- Keep bound buffers alive until execution and required device synchronization complete.
- Let runtime allocate unknown-shape outputs and retrieve their OrtValues.
- Rebind after buffer replacement or shape change.
- Separate zero-copy claims from measured copy and transfer telemetry.

## Verification
- Test CPU/GPU inputs, dynamic outputs, wrong device IDs, undersized buffers, repeated runs, and concurrent streams.
- Destroy or mutate owners at controlled points and verify guards prevent use-after-free.
- Profile transfers around bound and ordinary runs.

## Gotchas
IOBinding is an ownership and synchronization contract, not just a performance flag. Completion of the host call may not mean unrelated device work is synchronized.

## Official sources
- [ONNX Runtime IOBinding](https://onnxruntime.ai/docs/performance/tune-performance/iobinding.html)
- [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/api_summary.html#data-on-device)
