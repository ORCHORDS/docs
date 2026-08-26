# Keras safe_mode Is Not a Model Sandbox

**Issue:** Keras deserialization can reconstruct custom objects and historically risky Lambda content. Treating `safe_mode` as complete isolation overstates its boundary.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Keep `safe_mode=True` for untrusted or externally supplied `.keras` artifacts.
- Allowlist reviewed custom objects and pin their implementing package and source digest.
- Verify the artifact digest before load and isolate model inspection from production credentials and networks.
- Separate deserialization approval from inference approval and model-behavior evaluation.
- Reject formats and custom objects outside the deployment profile.

## Verification
- Attempt Lambda and unregistered custom-object loads and assert rejection.
- Tamper with the archive and verify digest enforcement runs before deserialization.
- Load approved models in the same restricted runtime used by the service.

## Gotchas
Keras documents that safe mode disables unsafe Lambda deserialization; it does not isolate the local Python environment or protect against external file modification.

## Official sources
- [Keras whole-model saving and loading](https://keras.io/api/models/model_saving_apis/model_saving_and_loading/)
- [Keras serialization utilities](https://keras.io/api/models/model_saving_apis/serialization_utils/)
