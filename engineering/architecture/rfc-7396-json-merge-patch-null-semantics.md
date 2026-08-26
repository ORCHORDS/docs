# JSON Merge Patch Uses null as Deletion

**Issue:** In RFC 7396, a null member removes the target member, so the format cannot directly express setting an object member to JSON null.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Use `application/merge-patch+json` only where deletion-by-null matches the domain contract.
- Document replacement semantics for arrays and non-object patch documents.
- Authorize every affected path and validate the complete candidate resource.
- Preserve optimistic concurrency with ETags or resource versions.
- Choose JSON Patch or a domain command when null and deletion must be distinct.

## Verification
- Test absent, null, nested object, scalar-root, array, type-change, empty-object, and stale-version patches.
- Apply patches to isolated candidates and assert validation failure leaves storage unchanged.
- Generate contract examples for every nullable field.

## Gotchas
Merge Patch is concise because it cannot represent every edit precisely. Arrays are replaced as values rather than merged element by element.

## Official sources
- [RFC 7396](https://www.rfc-editor.org/rfc/rfc7396.html)
