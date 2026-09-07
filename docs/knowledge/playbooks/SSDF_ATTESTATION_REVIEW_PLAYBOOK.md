# SSDF Attestation Review Playbook

## Purpose

Review a Secure Software Development Framework (SSDF) attestation produced under `NIST_SP_800_218_SSDF_V1_1_GOVERNANCE.md` (NIST SP 800-218 v1.1 + SP 800-218A v1.1) before accepting a release into the ORCHORDS production estate, so that attestation evidence is mapped to SSDF practices and the resulting gaps are tracked to remediation.

## Audience

Supply-chain security engineers, compliance leads, and platform engineers responsible for release acceptance.

## Pre-conditions

- The supplier or internal producer has produced an SSDF attestation that references NIST SP 800-218 v1.1 and (where AI is in scope) SP 800-218A v1.1 GenAI overlay.
- The attestation evidence package is available (control matrix, evidence artefacts, retention policy).
- The release scope (products, services, versions, AI components) is documented.

## Procedure

### Step 1 — Validate attestation scope and ownership

- Confirm the attestation covers the release scope (product name, version, release date).
- Identify the attestation owner and the named role that signed the attestation.
- Confirm the attestation is current (within the documented attestation validity window).

### Step 2 — Map attestation to SSDF practices

- For each PO, PS, PW, RV practice family: confirm the attestation maps each practice to evidence (control ID, evidence type, evidence location, retention period).
- Validate the evidence links resolve and the evidence is retrievable.
- Flag any missing practice mapping as a review defect; assign severity by SSDF practice family (PW and RV defects are release-blocking; PO and PS defects are documented but not always release-blocking).

### Step 3 — Test the evidence

- Sample at least one evidence artefact per practice family; verify the artefact independently where possible (regenerate SBOM, re-run the build, re-execute the vulnerability scan, re-run the secure-coding review).
- For AI components, re-run the bias test, the explainability check, and the human-oversight verification on the released model.
- Treat failed evidence as a release-blocking defect.

### Step 4 — Apply the GenAI overlay (Article 6 scope)

- If the release contains AI-generated code, validate the prompt-provenance record, the model identifier, and the human-review trail.
- If the release contains a model, validate the model card and the SP 800-218A v1.1 AI-overlay mappings.
- Flag missing overlay mappings as a release-blocking defect when the release is in AI scope.

### Step 5 — Acceptance decision

- Record the review outcome (accept, accept with conditions, reject) in the release ticket.
- For conditional accept, document the conditions and the remediation owner; track to closure in the issue tracker.
- For reject, document the release-blocking defects and the resubmission path.

### Step 6 — Archive and notify

- Archive the attestation and the review record for the documented retention period (default 7 years for federal-procurement-bound releases).
- Notify the producer and the supply-chain security lead of the review outcome.
- Feed the review findings into the SSDF control matrix and into the next SSDF audit.

## Rollback

- If the attestation is later found to be inaccurate, suspend the release's production status; re-run the review with corrected evidence.
- If the release is already in production, follow the documented incident-response playbook (NIST SP 800-61 Rev. 3 / ISO/IEC 27035).
- Do not delete attestation evidence; retain for the documented retention period even when the release is rolled back.

## References

- `NIST_SP_800_218_SSDF_V1_1_GOVERNANCE.md`
- `NIST_SP_800_218A_GENAI_PROFILE_VERSION_GOVERNANCE.md`
- `ISO_IEC_27036_2_2022_SUPPLIER_RELATIONSHIPS_GOVERNANCE.md`
- `SLSA_BUILD_LEVEL_3_GOVERNANCE.md`
- `EU_CYBER_RESILIENCE_ACT_2024_GOVERNANCE.md`
- `COSIGN_IMAGE_SIGNING_PLAYBOOK.md`
- `BUILD_PROVENANCE_REVIEW.md`
- `COMPONENT_PROVENANCE_REVIEW.md`
- `SBOM_COMPLETENESS_REVIEW.md`
