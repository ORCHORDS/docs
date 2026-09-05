---
title: "Supply Chain Levels for Software Artifacts (SLSA)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "SLSA v1.0; https://slsa.dev"
---

# Supply Chain Levels for Software Artifacts (SLSA)

## Scope

Reference card for SLSA, *Supply-chain Levels for Software Artifacts* (v1.0). SLSA is a security framework that defines increasing levels of supply-chain integrity assurance, organized into tracks (Source, Build, Provenance, Artifacts). Profiles that govern software release integrity should reference SLSA by version and identify the tracks and levels that apply.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | SLSA v1.0 specification |
| Tracks | Source, Build, Provenance, Artifacts |
| Levels | 0–3 (current), Level 4 in draft |
| Companion artifacts | in-toto attestation specification, Sigstore / cosign, SLSA Provenance Generator |
| Source URL | https://slsa.dev |

## Plan

1. Reference SLSA by version whenever a profile governs software release integrity.
2. Identify the tracks in scope (Source, Build, Provenance, Artifacts) and the level achieved for each.
3. Track the level achieved over time; SLSA levels are cumulative within each track.
4. Bind the Source track to branch protection, signed commits, and reviewer requirements.
5. Bind the Build track to hardened build platforms, provenance generation, and provenance signing.
6. Bind the Provenance track to attestation format, signer identity, and verification policy.
7. Bind the Artifacts track to artifact integrity (for example signed tags, signed container images).

## Inputs

- SLSA specification (slsa.dev).
- Internal source-code configuration, build pipeline configuration, and provenance tooling.
- Sigstore / cosign configuration if used; in-toto attestation type if used.
- Supplier attestations and SBOMs.

## ORCHORDS Profile

ORCHORDS treats SLSA as the canonical reference for software release integrity. Profiles that reference SLSA should cite the version, identify the tracks and levels, and bind to NIST SSDF (SP 800-218) and the CNCF supply-chain best practices.

A profile that claims "SLSA compliance" without a level and track is non-conformant.

## Implementation Notes

- SLSA levels are per-track, not global: a project can be at SLSA Build Level 3 and Source Level 1.
- Source track levels require branch protection, two-party review, and signed commits at higher levels.
- Build track levels require hardened build platforms, signed provenance, and provenance non-forgeability at higher levels.
- Provenance must be verified before artifact consumption; tooling should reject artifacts whose provenance is missing, malformed, signed by an unexpected identity, or inconsistent.
- SLSA Levels 4 introduces reproducibility and two-party review requirements beyond Build Level 3.

## Companion Documents

- [SLSA Build Level 3 Governance](SLSA_BUILD_LEVEL_3_GOVERNANCE.md)
- [NIST SSDF SP 800-218 Secure Software Development Framework](NIST_SSDF_SP_800_218.md)
- [CNCF Supply Chain Best Practices](CNCF_SUPPLY_CHAIN_BEST_PRACTICES.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [Container Image Build Hardening Response](../playbooks/CONTAINER_IMAGE_BUILD_HARDENING_RESPONSE.md)
- [Supply Chain Compromise Response](../playbooks/SUPPLY_CHAIN_COMPROMISE_RESPONSE.md)
