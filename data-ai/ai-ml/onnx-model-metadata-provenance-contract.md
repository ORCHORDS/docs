# ONNX Model Metadata Provenance Contract

**Issue:** An ONNX graph may be technically valid yet lack the provenance needed to reproduce, approve, or safely route it.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Populate producer_name, producer_version, domain, model_version, and doc_string under a documented convention.
- Use metadata_props for immutable identifiers such as training-run ID, source revision, dataset snapshot, license, and evaluation report URI.
- Sign or hash the final serialized model; metadata inside the file is not independently trustworthy.
- Validate metadata keys and required values before registry admission or deployment.

## Verification

- Run the ONNX checker and a custom metadata schema validator.
- Verify the recorded source revision and evaluation artifact exist and are access-controlled.
- Modify one metadata value and confirm artifact digest or signature verification fails.

## Gotchas

- metadata_props are strings and do not provide authenticity.
- Do not embed credentials, private dataset records, or mutable environment URLs.

## Official sources

- https://onnx.ai/onnx/api/classes.html#modelproto
- https://onnx.ai/onnx/repo-docs/IR.html
