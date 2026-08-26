# Safetensors Shared-Tensor Alias Preservation

**Issue:** PyTorch state dictionaries can contain tensors that share storage. Saving them naively can duplicate data or lose alias relationships, changing memory use or model behavior after loading.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use safetensors framework helpers designed for model save/load when shared storage is possible.
- Record the framework, library version, and expected alias groups with the artifact.
- After conversion, compare parameter names, values, storage-sharing expectations, and inference outputs.
- Keep conversion reproducible and retain the source artifact until validation completes.

## Verification

- Construct tied weights and partial shared views, then round-trip the model.
- Measure artifact size and loaded memory to detect unintended duplication.
- Run fixed-seed inference equivalence checks after conversion.

## Gotchas

- The safetensors file format does not generally preserve arbitrary shared-tensor graphs by itself.
- A successful load does not prove tied-weight semantics were restored.

## Official sources

- https://huggingface.co/docs/safetensors/main/en/torch_shared_tensors
