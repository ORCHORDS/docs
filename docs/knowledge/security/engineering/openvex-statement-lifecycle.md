---
title: "OpenVEX Statement Lifecycle and Distribution"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OpenVEX Statement Lifecycle and Distribution

## OpenVEX document rules

OpenVEX documents use context `https://openvex.dev/ns/v0.2.0`, an `@id`, `author`, `timestamp`, `version`, optional `tooling`, and `statements`. Each statement identifies one vulnerability, one or more products, a status, and status-dependent fields. Status is exactly `not_affected`, `affected`, `fixed`, or `under_investigation`. `not_affected` requires a recognized `justification`; an `impact_statement` explains the product-specific reasoning. `affected` should carry `action_statement` and optionally `action_statement_timestamp`. `fixed` identifies products for which the issue is fixed. `under_investigation` is temporary and needs an operational deadline.

```json
{"@context":"https://openvex.dev/ns/v0.2.0","@id":"https://example/vex/42","author":"Example PSIRT","timestamp":"2026-09-01T12:00:00Z","version":3,"statements":[{"vulnerability":{"name":"CVE-2026-1234"},"products":[{"@id":"pkg:oci/app@sha256%3A..."}],"status":"not_affected","justification":"vulnerable_code_not_in_execute_path","impact_statement":"Feature X is disabled in this build."}]}
```

## Supersession and consumption

Use exact purl, CPE, or digest-based product IDs; a name-only match can suppress the wrong version. Consumers must retain document origin and signature result, then order revisions by stable document `@id` and increasing `version`, not download time alone. A later product-specific statement should not automatically supersede an unrelated broader product.

Validate against the released OpenVEX schema and sign the document or authenticated distribution envelope. Test unknown product, conflicting statements, duplicate CVE aliases, lower document version, invalid justification, and transition from investigation to each terminal decision. Scanner findings remain stored; VEX changes triage state, not historical detection.

Track investigation age, unsigned or invalid documents, unmatched products, and conflicts. Rollback republishes a higher document version correcting the assertion; never rewrite an already distributed document under the same version and digest. Preserve analyst evidence and review approval with the OpenVEX digest.

## Sources

- [OpenVEX spec](https://github.com/openvex/spec)
- [OpenVEX docs](https://openvex.dev/docs/)
