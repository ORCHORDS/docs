# OpenSSF S2C2F Self-Hosted Integration Governance

## Purpose

Govern the application of the OpenSSF Secure Supply Chain Consumption Framework (S2C2F) so that open source consumption — ingesting, scanning, rebuilding, and updating third-party dependencies — follows defined practices at the appropriate maturity level, with the studio's own hosting and proxying infrastructure operating as part of the supply chain it governs.

## Scope

Ingest, scan, rebuild, update, and audit practices for third-party open source dependencies consumed by studio projects, including the self-hosted proxies, artifact registries, and mirror infrastructure that mediate consumption. Does not cover first-party secure development (covered by SSDF guidance) or vulnerability remediation SLAs.

## Workflow

1. Establish the S2C2F maturity baseline: assess current ingestion, scanning, rebuild, update, and audit practices against the framework's levels (1 through 4) and record the target level per project criticality.
2. Ingest through governed paths only: dependencies enter via the approved proxy or registry, not directly from public ecosystems on developer machines; direct fetch bypasses scanning and provenance checks.
3. Scan every ingested artifact for vulnerabilities and license issues before it is available to projects; the registry is the enforcement point, not developer discipline.
4. Rebuild critical dependencies from source where the threat model justifies it (framework levels 3-4), comparing rebuilt artifacts against published ones to detect divergence.
5. Update on cadence with automated tooling, with update risk assessed (semantic version distance, changelog review) and rollback paths defined.
6. Audit consumption continuously: every dependency in use traces to an ingestion record with scanner results and license decision; unknown provenance dependencies are quarantine-class findings.
7. Operate the self-hosted mirror itself under supply chain controls: pinned upstreams, integrity verification on sync, access control, and monitoring for sync failures.

## Controls and evidence

- S2C2F maturity assessment record and per-project target levels.
- Proxy/registry configuration showing that only governed paths are available and scanning is enforced at ingestion.
- Rebuild records with divergence analysis for critical dependencies.
- Consumption audit reports mapping dependencies to ingestion records.
- Mirror operation records: upstream pinning, sync integrity checks, and access control.

## Validation

- Attempt to add a dependency bypassing the governed path and confirm the attempt is blocked or detected.
- Sample 10 production dependencies and confirm each traces to an ingestion record with scan results and a license decision.
- Confirm mirror sync integrity verification catches a deliberately corrupted artifact in a test.

## Failure correction

- **Bypass path discovered** → close it at the registry or proxy, trace what entered through it, and scan those artifacts retroactively.
- **Dependency without ingestion record in production** → quarantine, reconstruct the record, and remediate the ingestion gap.
- **Mirror sync silently failing** → alert on sync failure (already required), backfill missed updates, and fix the upstream or credential cause.

## Limitations

- S2C2F governs consumption; upstream project compromise requires the rebuild and provenance controls at higher levels.
- Self-hosted infrastructure shifts trust from public ecosystems to internal operations; mirror compromise is a new critical risk.
- Maturity advancement is incremental; level jumps without practice evidence produce paperwork, not security.

## Scope note

This article is part of the platforms leaf. Cross-reference: `OPENSSF_SCORECARD_GOVERNANCE.md`, `OPENSSF_CII_BADGE_GOVERNANCE.md`, and `CNCF_TEKTON_PIPELINE_SUPPLY_CHAIN_GOVERNANCE.md` (operations leaf).

## Canonical sources

- OpenSSF S2C2F — Secure Supply Chain Consumption Framework: https://github.com/ossf/s2c2f
- OpenSSF — Secure Supply Chain Consumption Framework specification: https://ossf.github.io/s2c2f/
- NIST SP 800-218 — Secure Software Development Framework (SSDF): https://csrc.nist.gov/publications/detail/sp/800-218/final
- SLSA v1.0 — Supply-chain Levels for Software Artifacts: https://slsa.dev/
- OpenSSF Scorecard: https://securityscorecards.dev/
