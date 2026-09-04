# Archive Limits Must Be Enforced Before Extraction

**Issue:** An application validates the uploaded archive file size but only discovers the expanded size or number of entries after decompression has already consumed excessive CPU, memory, disk, or file-system resources.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP ASVS 5.0.0 V5.2.3 requires checking compressed files against maximum uncompressed size and maximum file count before uncompressing them. The compressed object is not the real resource cost; extraction is the trust boundary where a small input can expand into disproportionate work.

## Engineering rule

- Define maximum uncompressed size and archive-entry count for every archive-enabled upload feature.
- Evaluate those limits before extraction, not only after files have been written.
- Account for nested archives according to the application's supported processing model.
- Reject archive structures that exceed the approved resource envelope without leaving partially trusted output available to later stages.
- Treat symlinks in uploaded archives as disallowed unless specifically required and tightly constrained, consistent with ASVS V5.2.5.

## Verification

- Submit an archive whose compressed size is small but whose expanded size exceeds the configured limit and confirm rejection before full extraction.
- Submit an archive with excessive entries and confirm the entry-count control triggers before material extraction work.
- Submit a symlink-containing archive and confirm it is rejected unless the feature has an explicit allowlisted symlink design.

## Official source

- OWASP ASVS 5.0.0 requirements V5.2.3 and V5.2.5: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
