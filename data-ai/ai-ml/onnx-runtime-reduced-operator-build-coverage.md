# ONNX Runtime Reduced-Operator Build Coverage

**Issue:** A reduced ONNX Runtime build can pass its original smoke test yet fail when a model, opset, custom operator, or tensor type absent from the build configuration reaches production.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Generate the reduced-operator configuration from the complete, release-qualified model corpus rather than one representative model.
- Pin the ONNX Runtime source version, model digests, opset imports, build flags, configuration file, compiler, and target architecture as one release manifest.
- Prefer generated configuration. Treat manual edits as reviewed code because removing an operator or supported type changes runtime capability.
- Enable operator type reduction only from ORT-format models that contain the required type information.
- Keep custom-operator libraries and their loading tests beside the model bundle.
- Reject a model rollout unless its required operator/domain/opset/type set is covered by the shipped runtime.

## Implementation and tests

1. Recursively generate the configuration from all production and rollback models.
2. Build the minimal runtime in a clean environment and retain its digest and configuration.
3. Load and execute every model with boundary-shaped inputs on every target architecture.
4. Add a negative fixture whose operator or type was intentionally omitted and assert a clear, fail-closed load error.
5. Compare outputs with the full runtime and run rollback models before publishing the package.

## Gotchas and applicability

A smaller binary is an optimization, not evidence of semantic equivalence. Optimized model conversion can change the required set, and a later model release can invalidate an older configuration. ONNX-format models are not guaranteed to carry the per-node type information needed for type reduction. Recheck current ONNX Runtime documentation and platform support whenever the runtime or model toolchain changes.

## Official sources

- https://onnxruntime.ai/docs/reference/operators/reduced-operator-config-file.html
- https://onnxruntime.ai/docs/build/custom.html
- https://onnxruntime.ai/docs/performance/model-optimizations/ort-format-models.html
