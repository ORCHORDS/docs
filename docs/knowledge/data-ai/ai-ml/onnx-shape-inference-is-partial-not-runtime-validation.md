# ONNX shape inference is partial, not runtime validation

**Issue:** Successful ONNX shape inference can be mistaken for proof that all runtime tensor shapes, operator semantics, and backend behavior are valid.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run model checking and shape inference as separate gates; neither replaces backend execution tests.
- Use `check_type=True` and qualify `strict_mode=True` where incomplete inference must fail the release.
- Preserve unknown rank, symbolic dimensions, and anonymous dimensions instead of inventing concrete sizes.
- Test custom operators with registered type-and-shape inference and representative dynamic inputs.
- Use `infer_shapes_path` for models over 2 GB and keep external data with the model bundle.

## Verification

Exercise constants, symbolic dimensions, dynamic reshape, control-flow operators, custom domains, and conflicting declared shapes. Compare inferred metadata with actual outputs on every supported execution provider.

## Gotchas

ONNX documents that inference is not guaranteed to be complete. Dynamic behavior and unsupported operators can stop propagation, and conflicting pre-existing shape information makes the result unspecified.

## Official sources

- [ONNX shape inference](https://onnx.ai/onnx/repo-docs/ShapeInference.html)
- [ONNX shape inference API](https://onnx.ai/onnx/api/shape_inference.html)
