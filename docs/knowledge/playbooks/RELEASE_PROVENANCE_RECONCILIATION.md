# Release Provenance Reconciliation

## Trigger
Run before or after a supported release, after material dependency/build-input changes, during vulnerability-response exercises, and when release provenance is suspected to be incomplete or stale.

## Inputs
- Exact release/artifact identifier.
- Provenance/SBOM or component record associated with that release.
- Resolved dependency/build-input evidence.
- Artifact integrity or release evidence.
- Internal/external provenance retrieval process.

## Procedure
1. Select one exact supported release or immutable artifact as the reconciliation target.
2. Retrieve the provenance/component record associated with that exact release.
3. Obtain resolved dependencies, build inputs, or equivalent authoritative component evidence from the approved build process.
4. Compare the release provenance against the resolved/build evidence and identify missing, extra, stale, or ambiguous components.
5. Verify component versions/identities and source/origin information are sufficient for the organization’s vulnerability-response use case.
6. Verify the provenance record is integrity-protected according to the release-evidence model.
7. Change a component in a safe test release and confirm the generated provenance changes with the artifact rather than remaining a static product-level record.
8. Ask an internal vulnerability-response or operations role to retrieve the provenance for the selected release without reconstructing it manually.
9. If customer/acquirer sharing is part of policy, exercise the supported delivery mechanism and verify the correct release-specific record is provided.
10. Record coverage or retrieval gaps, remediate, and repeat the reconciliation.

## Escalation
Escalate release records that cannot be tied to a specific artifact, missing material components, stale provenance after component changes, integrity gaps, or inability of responders to retrieve evidence for supported releases.

## Evidence
- Exact release/artifact reference.
- Release provenance/component record.
- Resolved/build-input evidence.
- Reconciliation results.
- Integrity verification.
- Internal retrieval test.
- External delivery test where applicable.
- Findings and retest evidence.

## Completion criteria
The selected release has accurate, release-specific, retrievable, integrity-protected provenance that reconciles with authoritative build/component evidence.

## Source basis
- NIST SP 800-218, Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project page — PS.3.2: https://csrc.nist.gov/projects/ssdf
