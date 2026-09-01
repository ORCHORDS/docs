---
title: "SPDX 3 Security Profile Adoption"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# SPDX 3 Security Profile Adoption

## SPDX 3 model

SPDX 3.0 is an object graph. Core supplies `SpdxDocument`, `Element`, `Relationship`, creation information, namespaces, and external identifiers; Software models packages, files, snippets, and artifacts; Security adds vulnerability and assessment concepts. A document declares profiles used. Every element has a globally scoped SPDX identifier within its namespace, and relationships identify elements by ID rather than nesting an ambiguous component copy.

Security assertions must distinguish vulnerability identity, affected element, assessment, evidence, and lifecycle data. Use canonical CVE or advisory identifiers through external identifiers and preserve the source. Do not translate SPDX 2.3 `Package`, `ExternalRef`, and relationship rows into SPDX 3 by field-name similarity alone: profile classes and graph semantics differ. State the exact 3.0 release and serialization (JSON-LD, JSON, or another supported form) accepted by each consumer.

## Interoperability procedure

Create fixtures with one package, one file, two external identifiers, dependency relationships, a vulnerability, an assessment, creator identity, and timestamps. Validate against the official 3.0 model/schema and load into two independent consumers. Compare graph nodes and edges, not only parse success. Round-trip through the legacy converter and report dropped classes, relationship types, namespaces, extensions, or attribution.

Reject duplicate element IDs, dangling relationship endpoints, unsupported profile declarations, malformed external identifiers, and creation records without attributable agents. Preserve unknown extension data when the serialization permits; otherwise quarantine rather than silently discard. Bind the document to its described artifact with checksums and an explicit relationship.

Track validation errors, unresolved IDs, conversion loss, unsupported profiles, and consumer-version divergence. Keep source and transformed document hashes plus mapping-tool versions. Rollback to the prior serialization pipeline when semantic fixture comparisons change. SPDX security data informs analysis but does not itself authenticate the issuer; verify the enclosing signature or trusted delivery channel separately.

## Sources

- [SPDX 3.0](https://spdx.github.io/spdx-spec/v3.0/)
- [Security profile](https://spdx.github.io/spdx-spec/v3.0/model/Security/)
