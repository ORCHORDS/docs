---
title: SLSA (Supply-chain Levels for Software Artifacts) Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: SLSA project (https://slsa.dev/); SLSA v1.0 (October 2024); SLSA v1.1 (in development, 2026-09); NIST SP 800-218 SSDF v1.1 (crosswalk)
---

# SLSA (Supply-chain Levels for Software Artifacts) Version Governance

## Scope

This card governs how `orchords-docs` evaluates the SLSA framework — a graduated, auditable set of supply-chain security levels. SLSA is the reference input for any KB card that cites build provenance, source integrity, artifact verification, or dependency trust.

## Why this card exists

SLSA v1.0 (October 2024) superseded the v0.x framework and is the canonical supply-chain integrity standard. It defines four levels: Build L0, L1, L2, L3 (and Source L1/L2/L3 in the v1.x rewrite). A KB card that cites "SLSA" without binding to the level and the v1.0 mechanics produces a build-pipeline recommendation that does not survive an SLSA audit.

## Document set

- **SLSA v1.0** (October 2024) — Source Levels, Build Levels, verification.
- **SLSA v1.1** — in development (2026-09).
- **NIST SP 800-218** — SSDF v1.1 (crosswalk).

References: `https://slsa.dev/`.

## Source and Build Levels

SLSA v1.0 splits into two independent tracks:

### Source track

| Level | Description |
|---|---|
| Source L0 | no integrity guarantee |
| Source L1 | provenance exists; signed by builder |
| Source L2 | provenance is non-forgeable; signed by source control platform |
| Source L3 | provenance is non-forgeable; source platform is hardened against insider threat |

### Build track

| Level | Description |
|---|---|
| Build L0 | no integrity guarantee |
| Build L1 | build script defined; provenance generated |
| Build L2 | build hosted on isolated platform; provenance signed by build platform |
| Build L3 | build platform hardened against runtime threats; provenance non-forgeable |

A repository / artifact's SLSA rating is the combination of Source and Build levels.

References: `https://slsa.dev/spec/v1.0/levels`.

## Provenance attestation

SLSA provenance is a signed attestation that includes:

- `builder.id` — the build platform identifier (e.g., `https://github.com/actions/runner`).
- `invocation.id` — the unique invocation ID.
- `materials` — the input artifacts (source URI, hash).
- `buildType` — the build type (e.g., `https://slsa-framework.github.io/github-hosted-actions/v1`).
- `metadata.buildStartedOn` / `metadata.buildFinishedOn`.

Provenance is signed using Sigstore cosign or in-toto.

References: `https://slsa.dev/provenance/`.

## Verification

The verifier checks:

- The provenance is signed by a trusted builder.
- The source materials hash to the expected source revision.
- The build script matches the expected build script.

SLSA-verification tools: `slsa-verifier`, `cosign verify-attestation`, `gitsign`.

## Build platform mapping

| Build platform | Build level |
|---|---|
| GitHub Actions (with hardened runners) | Build L3 |
| GitHub Actions (standard) | Build L2 |
| Google Cloud Build | Build L2 / L3 |
| Tekton Chains | Build L2 / L3 |
| Ko (Go-native) | Build L2 |
| Bazel (with rules for SLSA) | Build L3 |
| Local build | Build L0 / L1 |

## Mandatory pre-flight (before adopting a new SLSA level target)

1. The source platform is identified (e.g., GitHub).
2. The build platform is identified (e.g., GitHub Actions).
3. Provenance generation is wired.
4. Provenance signing is wired.
5. Verification is wired.
6. The level target is documented.

## Mandatory pre-flight (before adopting a new SBOM / attestation tool)

1. The tool generates SLSA-compliant provenance.
2. The tool signs provenance.
3. The tool integrates with the build platform.
4. Verification can run on the produced provenance.

## Cross-reference

| Domain | Card |
|---|---|
| SSDF | `NIST_SP_800_218_SSDF_GOVERNANCE.md` |
| SBOM | `NIST_CSWP_23_2024_SSB_GOVERNANCE.md` |
| Container image | `OCI_RUNTIME_VERSION_GOVERNANCE.md` |
| Vulnerability disclosure | `ISO_IEC_30111_2019_VDP_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every reference card that cites SLSA.
2. Confirm the SLSA level is current.
3. Confirm provenance is generated and signed.
4. Confirm verification is wired.
5. Update the next-review date.

## Sources

- SLSA: `https://slsa.dev/`
- SLSA v1.0 spec: `https://slsa.dev/spec/v1.0/`
- NIST SP 800-218 SSDF: `https://csrc.nist.gov/publications/detail/sp/800-218/final`
- in-toto: `https://in-toto.io/`
- Sigstore cosign: `https://github.com/sigstore/cosign`
- SLSA verifier: `https://github.com/slsa-framework/slsa-verifier`
