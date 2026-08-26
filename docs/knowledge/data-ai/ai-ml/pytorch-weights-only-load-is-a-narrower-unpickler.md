# PyTorch weights_only Is a Narrower Unpickler, Not Isolation

**Issue:** PyTorch checkpoints use pickle semantics. `weights_only=True` narrows executable deserialization but does not eliminate denial-of-service or every memory-safety risk.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Prefer plain state dictionaries and load with `weights_only=True`.
- Verify artifact digest and provenance before load.
- Allowlist additional globals only through review tied to package and source versions.
- Load external artifacts in a resource-limited worker without production credentials.
- Validate tensor count, shape, dtype, sparsity, and total storage before model construction.

## Verification
- Test disallowed globals, dynamic imports, oversized shapes/storage, malformed archives, and sparse tensors.
- Assert environment policy cannot be silently disabled at a call site.
- Reconcile loaded keys and shapes to the approved architecture manifest.

## Gotchas
PyTorch explicitly notes that weights-only loading does not prevent denial of service and may not eliminate memory corruption paths.

## Official sources
- [PyTorch serialization semantics](https://docs.pytorch.org/docs/stable/notes/serialization.html#torch-load-with-weights-only-true)
- [PyTorch torch.load](https://docs.pytorch.org/docs/stable/generated/torch.load.html)
