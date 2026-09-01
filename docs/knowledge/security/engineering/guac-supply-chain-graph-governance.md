---
title: "GUAC Supply-Chain Graph Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# GUAC Supply-Chain Graph Governance

## Graph and ingestion semantics

GUAC ingests documents such as SPDX, CycloneDX, SLSA provenance, vulnerability feeds, and OpenVEX, then normalizes assertions into a graph. Package identities commonly use package URLs (purl); artifacts require cryptographic digests. An alias, name, version, purl, and digest are not interchangeable. Preserve qualifiers and subpath in purls and define whether repository URLs identify source, package, or distribution location.

Collectors acquire data, parsers produce GUAC ingestion predicates, and the assembler writes graph relationships. Record collector URI, source-document digest, parser and GUAC versions, ingestion time, and cryptographic verification result. Keep original documents because normalization can lose extension fields or provenance envelope details. Conflicting assertions must coexist with origin and time; “last write wins” is unsafe for VEX or identity.

## Query controls and completeness

Define a bounded question such as “which release digests contain package purl X and have an affected VEX assertion?” Build a fixture with known SBOM `DEPENDS_ON` edges, provenance subjects, vulnerabilities, and conflicting VEX statuses, then assert exact graph results through the supported GraphQL API. Test purl case/encoding, versionless packages, duplicate BOM refs, digest algorithms, cyclic dependencies, deleted sources, and stale vulnerability feeds.

GUAC can show that no matching assertion was ingested; it cannot prove that no vulnerability exists unless collection completeness and freshness are established. Publish collection coverage and maximum ingest lag with every policy result. Separate collector credentials, ingestion rights, and query tenants. Bound document size and parser resources to resist poisoned metadata.

Monitor failed collectors, parse rejection, assembler backlog, orphan identities, unresolved aliases, source age, and contradictory VEX. Back up graph storage plus raw-source manifests and restore into a compatible schema before upgrades. If a migration changes query results, roll back storage and parser versions together, then replay from immutable source documents rather than hand-edit graph nodes.

## Sources

- [GUAC docs](https://docs.guac.sh/)
- [GUAC repository](https://github.com/guacsec/guac)
