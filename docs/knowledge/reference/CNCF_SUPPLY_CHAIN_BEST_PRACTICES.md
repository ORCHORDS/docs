---
title: "CNCF Supply Chain Best Practices"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "CNCF Security TAG — Software Supply Chain Best Practices; https://github.com/cncf/tag-security/tree/main/supply-chain-security"
---

# CNCF Supply Chain Best Practices

## Scope

Reference card for the CNCF Security TAG *Software Supply Chain Best Practices*. The publication collects community-endorsed practices for source-code integrity, build integrity, dependency integrity, and artifact integrity, aligned with SLSA, NIST SSDF (SP 800-218), and the Sigstore / in-toto tooling. Profiles that govern cloud-native software supply chains should reference the CNCF best practices and bind to SLSA, NIST SSDF, and the Sigstore stack.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | CNCF Security TAG Software Supply Chain Best Practices (current published version) |
| Status | Continuously maintained by the CNCF Security TAG |
| Companion artifacts | SLSA, NIST SSDF (SP 800-218), Sigstore / cosign, in-toto attestation, Cloud Native Buildpacks |
| Source URL | https://github.com/cncf/tag-security/tree/main/supply-chain-security |

## Plan

1. Reference the CNCF best practices by current version whenever a profile governs a cloud-native software supply chain.
2. Adopt the source-code integrity controls: branch protection, signed commits, protected branches, and reviewer requirements.
3. Adopt the build-integrity controls: hardened build platforms, provenance generation, provenance signing, and provenance verification.
4. Adopt the dependency-integrity controls: lockfiles, vendored dependencies, SBOM generation, dependency-update policy, and CVE monitoring.
5. Adopt the artifact-integrity controls: signed tags, signed container images, signature verification, and SLSA artifact-level expectations.
6. Bind to Sigstore / cosign and the in-toto attestation specification for cryptographically signed artifacts and attestations.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- CNCF Security TAG Software Supply Chain Best Practices.
- Internal source-code, build, dependency, and artifact configurations.
- Sigstore / cosign deployment and the in-toto attestation tooling.
- Supplier attestations and SBOMs.

## ORCHORDS Profile

ORCHORDS treats the CNCF best practices as the canonical community reference for cloud-native software supply chains. Profiles that reference CNCF best practices should cite the version, identify the controls adopted, and bind to SLSA, NIST SSDF, and the Sigstack tooling.

A profile that references "supply chain security" without binding to a recognized framework is non-conformant.

## Implementation Notes

- The CNCF best practices are not a checklist; they are organized by track (Source, Build, Dependencies, Artifacts) with controls at each track.
- Sigstore provides signing (cosign), transparency (Rekor), and short-lived key issuance (Fulcio) that work together to support provenance and artifact signing.
- SBOM formats include SPDX and CycloneDX; choose based on the consumer requirements.
- CVE monitoring should be automated; manual CVE monitoring is acceptable only for small dependency sets.
- The CNCF best practices evolve with the tooling; re-ratify profiles when the published version changes.

## Companion Documents

- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [SLSA Build Level 3 Governance](SLSA_BUILD_LEVEL_3_GOVERNANCE.md)
- [NIST SSDF SP 800-218 Secure Software Development Framework](NIST_SSDF_SP_800_218.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- NIST SP 800-218A GenAI Profile Version Guide
- [Container Image Build Hardening Response](../playbooks/CONTAINER_IMAGE_BUILD_HARDENING_RESPONSE.md)
- [Supply Chain Compromise Response](../playbooks/SUPPLY_CHAIN_COMPROMISE_RESPONSE.md)
