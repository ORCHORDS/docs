---
title: in-toto Attestation Framework Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://in-toto.io/ ; https://github.com/in-toto/in-toto-golang
---

# in-toto Attestation Framework Version Governance

## 1. Purpose

This reference card governs the lifecycle of the **in-toto** attestation framework — the supply-chain integrity layer that produces, verifies, and chains SLSA-conformant attestations across source, build, and delivery stages.

## 2. Scope

In scope:

- in-toto specification v0.9 (current).
- Reference libraries: `in-toto-golang >= 0.9`, `in-toto-python >= 2.x`.
- Attestation envelope: DSSE (Dead Simple Signing Envelope, in-toto.io/envelope/v1).
- Predicates: SLSA Provenance v1, SPDX SBOM v2.3, CycloneDX 1.7, VEX v0.2.
- Storage backends: Rekor transparency log, local filesystem for air-gapped builds.

Out of scope:

- in-toto runlib execution (the policy-engine style of attestation collection).
- The TUF delivery side (covered separately under `TUF_VERSION_GOVERNANCE.md`).

## 3. Versioning policy

- Pin in-toto-golang library to a specific minor; upgrades require a verification round with all pinned predicates.
- DSSE payload type MUST be `application/vnd.in-toto+json`.
- All attestations MUST be verifiable against a known root signing key.
- Attestations older than 365 days MUST be re-signed during routine maintenance.

## 4. Compatibility matrix

| in-toto spec | in-toto-golang | in-toto-python | Predicate library | Notes |
| --- | --- | --- | --- | --- |
| 0.9 (2024) | 0.9.x | 2.4.x | intoto-attestation v0.4 | DSSE v1 canonical |
| 0.9.x (2025) | 0.10.x | 3.0.x | intoto-attestation v0.5 | Added attestation grouping |

## 5. Predicate best practices

- **SLSA Provenance**: required fields `buildDefinition`, `runDetails`, `metadata.buildStartedOn/FinishedOn`. Always set `metadata.completeness` to `{"environment": true, "materials": true}`.
- **SPDX SBOM**: include all transitive deps; do not filter by license type.
- **CycloneDX 1.7**: prefer over SPDX for application services (smaller, faster).
- **VEX 0.2**: emit only for vulnerabilities with `state=not_affected` or `state=fixed`.

## 6. Verification procedure

1. Verify envelope signature against the pinned public key.
2. Decode DSSE payload and check `payloadType` is the expected predicate URI.
3. Material verification: every `materials.uri` resolves to a content-addressed digest.
4. Predicate verification: predicate-specific invariants (SLSA source provenance requires `subject[0].digest.sha256`).

## 7. Pipeline integration

- Source stage: in-toto SourceLink attestation emitted on PR merge.
- Build stage: in-toto BuildSLSA attestation emitted by Tekton / BuildKit.
- Deploy stage: in-toto ProvenanceGate admission controller validates SLSA Build L3 threshold.

## 8. Upgrade procedure

1. Read the in-toto release notes for predicate changes.
2. Roll in-toto-golang library; run conformance tests against existing attestations.
3. Regenerate attestation predicates that have breaking changes.
4. Promote after 7 days of clean pipeline runs.

## 9. Rollback procedure

- Revert the in-toto-golang library to the previous tag.
- Existing attestations remain valid because the envelope format is backward compatible.
- If a new predicate type was added, re-emit at next pipeline run.

## 10. Observability

- Required metrics: `in_toto_attestation_emit_total{stage,predicate,result}`, `in_toto_attestation_verify_total{predicate,result}`, `in_toto_dsse_signature_total{keyid,result}`.
- Alert on `in_toto_attestation_verify_total{result="failure"}` > 0.01 sustained over 1 hour.

## 11. References

- in-toto specification — https://github.com/in-toto/docs
- DSSE envelope spec — https://github.com/secure-systems-lab/dsse
- SLSA Provenance v1 — https://slsa.dev/provenance/v1
