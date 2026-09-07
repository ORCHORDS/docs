# NIST SP 800-218 Rev. 1.1 Secure Software Development Framework (SSDF) Governance

## Purpose

NIST Special Publication 800-218 Revision 1.1 (February 2022) describes the Secure Software Development Framework (SSDF), a set of practices for integrating security throughout the secure software development life cycle (SDLC). Governance ensures that ORCHORDS software producers and acquirers apply SSDF v1.1 practices in a manner consistent with US federal procurement requirements (Executive Order 14028, OMB M-22-18, M-23-16) and with the NIST SP 800-218A v1.0 (March 2024) SSDF profile for federal procurement, and that SSDF attestations are produced from documented, testable evidence.

## Current context and source status

SSDF v1.1 supersedes SP 800-218 v1.0 and aligns with the practices called out in Executive Order 14028 (Improving the Nation's Cybersecurity, May 2021). SP 800-218A v1.0 provides a federal procurement profile that maps SSDF practices to attestation artefacts. SP 800-218A v1.1 (March 2025) added a GenAI/discriminative AI software overlay. Treat v1.1 as the canonical reference for SSDF practice definitions and v1.0/v1.1 of 800-218A as the canonical reference for attestation content.

## Governance workflow and controls

### 1. SSDF practice scope and ownership

- Apply all SSDF v1.1 practices to every line of code, configuration, and infrastructure-as-code produced under ORCHORDS ownership.
- Map SSDF practices to internal controls; record the mapping in a SSDF control matrix under change control.
- Define the producer role (the team that writes the code), the acquirer role (the team that consumes third-party code), and the attestation owner (the team that signs an SSDF attestation for release).

### 2. PO (Prepare the Organization) practices

- Define security requirements for software development, including threat modelling and abuse-case definitions.
- Define roles and responsibilities for security; embed security responsibilities in role descriptions.
- Provide tooling and infrastructure (build, test, sign, attest) that implements SSDF controls.
- Define and maintain a secure software development environment (workstation baseline, ephemeral CI runners, signed dependency lockfiles).

### 3. PS (Protect the Software) practices

- Verify the integrity and provenance of all third-party software components before they enter the build.
- Maintain a documented and tested process for delivering software to production; record the integrity check at delivery.
- Archive and protect each release; pin a canonical artifact hash and signature.

### 4. PW (Produce Well-Secured Software) practices

- Apply secure coding practices; gate merge on a secure coding review for high-risk changes.
- Use a documented review process for human-authored and AI-generated code; record reviewer identity.
- Reuse existing, vetted security software (cryptographic libraries, identity libraries, logging frameworks); do not roll your own.
- Perform a vulnerability analysis using static analysis, dynamic analysis, dependency scanning, and penetration testing as appropriate.
- Document the threat model; treat the threat model as a release artefact.

### 5. RV (Respond to Vulnerabilities) practices

- Identify and confirm vulnerabilities on a continuous basis; triage within a documented SLA.
- Assess, prioritise, and remediate vulnerabilities; track SLAs in the issue tracker.
- Analyse root cause; feed root-cause findings back into the secure-coding review process.
- Disclose vulnerabilities in accordance with a published vulnerability disclosure policy.

### 6. Attestation and evidence

- For each release, produce an SSDF attestation that maps each v1.1 practice to evidence (control ID, evidence type, evidence location, evidence retention period).
- For third-party software, request an SSDF attestation from the supplier; reject third-party software without an attestation when the component is in the critical path.
- Retain attestation evidence for the lifetime of the release plus the documented retention period (default 7 years for federal-procurement-bound releases).
- Align attestation evidence with the SP 800-218A v1.1 GenAI overlay when the release contains AI-generated code or model weights.

### 7. AI/ML overlay

- When the release contains AI-generated code, record the model identifier, prompt provenance, and human-review trail.
- When the release contains a model, apply the SP 800-218A v1.1 AI overlay and produce an additional model-card artefact.
- For AI-assisted code, gate merge on a human-authored review that explicitly attests to control correctness.

### 8. Audit and continuous improvement

- Audit SSDF practice coverage at least annually and after every significant architecture change.
- Feed audit findings into the SSDF control matrix; treat deltas as controlled changes.
- Report SSDF coverage to the executive risk committee at a documented cadence (default quarterly).

References: NIST SP 800-218 Rev. 1.1; NIST SP 800-218A v1.0, v1.1; Executive Order 14028; OMB M-22-18, M-23-16; `https://csrc.nist.gov/projects/ssdf`.
