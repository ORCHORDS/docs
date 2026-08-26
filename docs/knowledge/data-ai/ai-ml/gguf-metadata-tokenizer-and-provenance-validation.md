# GGUF Metadata, Tokenizer, and Provenance Validation

**Issue:** A GGUF file can load while carrying the wrong chat template, tokenizer metadata, architecture parameters, or quantization provenance for the intended model.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Validate architecture-specific required metadata and tensor inventory before registration.
- Bind tokenizer vocabulary, special tokens, chat template, quantization method, and source revision to the artifact digest.
- Compare converted outputs with the source model on fixed prompts.
- Reject unknown critical metadata and impossible tensor shapes.

## Verification

- Swap tokenizer or chat-template metadata and confirm admission fails.
- Truncate or alter a tensor and verify digest/inventory detection.
- Run deterministic conversion and inference comparisons.

## Gotchas

- The filename is not authoritative model identity.
- Quantized output need not be bit-identical, so define numeric tolerances.

## Official sources

- https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
