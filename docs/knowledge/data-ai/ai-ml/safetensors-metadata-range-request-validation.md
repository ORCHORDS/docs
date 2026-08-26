# Validate Safetensors Metadata Before Range-Based Loading

**Issue:** Remote metadata inspection uses the file's length prefix and JSON header before tensor bytes are fetched. Trusting offsets, shapes, or response ranges can cause excessive allocation or wrong-byte loading.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Verify artifact identity and expected total length before trusting metadata.
- Cap header length, tensor count, dimensions, element count, and aggregate byte size.
- Validate nonoverlapping offsets within the declared file length and dtype/shape byte consistency.
- Require correct HTTP range semantics; reject a full or mismatched response where a bounded range was expected.
- Treat metadata as untrusted even though the format avoids pickle execution.

## Verification
- Fuzz length prefix, JSON, duplicate names, offsets, shapes, dtypes, truncated ranges, changed ETags, and oversized headers.
- Swap the remote object between metadata and tensor requests and assert identity mismatch.
- Compare streamed and whole-file loaders on valid fixtures.

## Gotchas
“Safe” refers chiefly to avoiding arbitrary code execution, not authenticity or unlimited resource safety. Multiple range requests need a stable object version.

## Official sources
- [Safetensors format](https://huggingface.co/docs/safetensors/index)
- [Safetensors metadata parsing](https://huggingface.co/docs/safetensors/metadata_parsing)
