# A Data Export Needs a Verifiable Completeness Manifest

**Issue:** A successful archive download does not prove that every expected object arrived or that bytes were unchanged. Exports need an independently verifiable inventory.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Produce a deterministic manifest listing every payload path exactly once with a modern checksum.
- Include export identity, generation time, source snapshot or cutoff, schema version, record and byte counts, and any intentional exclusions.
- Protect metadata and payload manifests together; sign the manifest or deliver its trusted digest out of band when authenticity matters.
- Use stable path encoding and reject traversal, duplicate, case-collision, and normalization-collision paths.
- Validate completeness and checksums before importing or declaring custody transfer complete.
- Preserve validation results and the exact manifest as transfer evidence.

## Verification

- Delete, add, rename, truncate, and bit-flip payload files and assert validation fails.
- Test Unicode filenames, empty files, large files, and multiple archives in one export.
- Reconcile manifest counts against source snapshot counts and import counts.
- Verify that a forged manifest is rejected by the authenticity control.

## Gotchas

Checksums detect accidental change but do not authenticate an attacker-controlled manifest. Archive-level hashing alone cannot identify a missing logical object or support selective validation.

## Official sources

- [RFC 8493: BagIt File Packaging Format](https://www.rfc-editor.org/rfc/rfc8493.html)
