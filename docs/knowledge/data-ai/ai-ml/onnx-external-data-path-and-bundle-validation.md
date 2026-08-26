# ONNX External-Data Path and Bundle Validation

**Issue:** Large ONNX tensors can be stored outside the model file. Missing, replaced, absolute, or escaping locations can make the model non-portable or load unintended files.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Require relative external-data locations rooted in an immutable model bundle.
- Reject absolute paths and normalized paths that escape the bundle.
- Hash and inventory the ONNX file plus every external data file as one artifact.
- Apply file-size and tensor-allocation limits before loading.

## Verification

- Move the complete bundle and verify it still loads.
- Replace, omit, truncate, and path-traverse an external data location.
- Confirm the registry verifies every file digest before runtime load.

## Gotchas

- Signing only model.onnx does not authenticate external tensor bytes.
- A valid ONNX graph can still reference unavailable external data.

## Official sources

- https://onnx.ai/onnx/repo-docs/ExternalData.html
