# ONNX Opset Conversion Needs Semantic Qualification

**Issue:** Converting a model between ONNX operator-set versions rewrites versioned operator semantics and may fail or produce a technically valid artifact whose outputs differ.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Record source and target opsets, converter and ONNX versions, model digest, and conversion logs.
- Convert only across versions supported by the official converter and fail on unsupported adapters.
- Run the checker and shape inference where appropriate after conversion.
- Qualify converted outputs and performance on each target runtime/provider.
- Preserve the source artifact and make conversion reproducible.

## Verification
- Test representative, boundary, empty, and dynamic-shape inputs before and after conversion.
- Assert tolerances per output rather than one aggregate score.
- Exercise unsupported operators and target opsets as negative tests.

## Gotchas
Schema validation is not numerical equivalence. Conversion does not guarantee that a target runtime implements every target-opset operator.

## Official sources
- [ONNX version converter API](https://onnx.ai/onnx/api/version_converter.html)
- [ONNX checker API](https://onnx.ai/onnx/api/checker.html)
