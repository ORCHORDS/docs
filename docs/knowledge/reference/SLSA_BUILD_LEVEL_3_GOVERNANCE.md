---
title: "SLSA Build Level 3 Governance"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Supply-chain Levels for Software Artifacts (SLSA) v1.0; https://slsa.dev"
---

# SLSA Build Level 3 Governance

## Scope

Reference card for SLSA (Supply-chain Levels for Software Artifacts) Build Level 3. SLSA defines four increasing levels of build integrity and provenance assurance. Build Level 3 requires that builds run on a hardened, isolated, ephemeral build platform with strong authentication, signed provenance, and resistance to specific supply-chain attack classes (build script tampering, parameter injection, and dependency confusion). Profiles governing software release integrity should reference SLSA Build Level 3 by version when claiming an assurance level.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | SLSA v1.0 specification (slsa.dev) |
| Subject track | Build track |
| Level | Build Level 3 (out of 4) |
| Companion tracks | Source track (Levels 1–3), Provenance track, Artifacts track |
| Companion artifacts | in-toto attestation spec, Sigstore / cosign, SLSA Provenance Generator |
| Source URL | https://slsa.dev |

## Plan

1. Reference SLSA Build Level 3 by name and version whenever a release or build pipeline is documented as meeting the level.
2. Treat Build Level 3 as requiring (a) a hardened build platform with isolated runners, (b) signed provenance generated from the build platform, (c) provenance non-forgeability by build participants, and (d) resistance against runtime parameter injection.
3. Bind the build-pipeline configuration to the SLSA requirements document so a reviewer can map each requirement to a control or a setting in the pipeline.
4. Maintain provenance alongside every artifact; provenance is part of the artifact's identity, not an optional attachment.
5. Validate provenance before consumption; tooling should refuse artifacts whose provenance is missing, malformed, signed by an unexpected identity, or inconsistent with the artifact.
6. When Build Level 4 is claimed, document the additional two-party review and reproducibility expectations, not just stronger signing.

## Inputs

- Build pipeline configuration (CI/CD manifests, runner definitions, isolation posture).
- Provenance generation configuration (in-toto statement type, signing identity, key management policy).
- Source code repository configuration (branch protection, signed commits, protected branches).
- Dependency management policy (lockfiles, attestations for vendored dependencies, SBOM).
- Threat model for the build environment, including adversarial operator and adversarial dependency scenarios.

## ORCHORDS Profile

ORCHORDS treats SLSA Build Level 3 as a binding reference for any release pipeline that publishes signed artifacts consumed by ORCHORDS-managed systems. Profiles that reference SLSA should state the level (1–4) and the track (Source, Build, Provenance, Artifacts). A profile that claims "SLSA compliance" without a level is non-conformant.

Profiles that integrate Sigstore / cosign should bind the Fulcio certificate transparency log expectations and the Rekor transparency log expectations to the SLSA Provenance track requirements rather than to SLSA alone.

## Implementation Notes

- SLSA levels are cumulative: Build Level 3 implies Build Level 2 and Build Level 1.
- Build Level 3 does not require that builds be reproducible; reproducibility is a Level 4 expectation.
- Provenance non-forgeability is achieved by keeping the signing key inside the build platform; the same key must not be available to code contributors.
- Hardening means the runner cannot be modified by the build script; treat the build script and the runner as separate trust domains.
- Parameter injection (for example, environment variables that affect build outcome) should be constrained by the build platform, not by the build script.

## Companion Documents

- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [NIST SSDF SP 800-218 Secure Software Development Framework](NIST_SSDF_SP_800_218.md)
- [CNCF Supply Chain Best Practices](CNCF_SUPPLY_CHAIN_BEST_PRACTICES.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [Container Image Build Hardening Response](../playbooks/CONTAINER_IMAGE_BUILD_HARDENING_RESPONSE.md)
- [Secure Software Release Verification Response](../playbooks/SECURE_SOFTWARE_RELEASE_VERIFICATION_RESPONSE.md)
- [Supply Chain Compromise Response](../playbooks/SUPPLY_CHAIN_COMPROMISE_RESPONSE.md)
