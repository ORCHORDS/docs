---
title: "OWASP ASVS 5.0.0 File Handling Verification"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP ASVS 5.0.0 File Handling Verification

## Pinned source and scope
ASVS **5.0.0**, chapter **V12 Files and Resources**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Map each upload, archive extraction, parser, export, and download to applicable V12 requirement IDs. Enforce business allowlists, independently detect content, generate storage names, cap compressed and expanded sizes, isolate parsing, and serve active formats from a separate non-cookie origin with safe Content-Disposition and nosniff behavior.

## Domain-specific procedure
Upload extension/MIME mismatches, polyglots, SVG/HTML active content, traversal and Unicode filenames, duplicate extensions, decompression bombs, nested archives, oversized dimensions, parser-crash samples, and malware-test files. Test direct-object access to stored files and retrieval headers. Confirm rejected files never reach downstream previewers or public buckets.

## Evidence and decision
Preserve file hashes, detector output, parser sandbox logs, storage keys, retrieval headers, and expanded archive sizes. Evidence must follow a sample from ingress through deletion.

## Failure modes
Extension-only checks, public predictable object keys, inline active content, archive expansion before limits, and same-origin previewing are failures.

## Sources
- [Pinned canonical source](https://github.com/OWASP/ASVS/tree/v5.0.0_release/5.0/en/0x1B-V12-Files-and-Resources.md)
