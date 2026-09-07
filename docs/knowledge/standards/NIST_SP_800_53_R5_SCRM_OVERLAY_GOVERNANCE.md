# NIST SP 800-53 Rev 5 SCRM Control Overlay Governance

## Purpose

NIST SP 800-53 Revision 5 (September 2020, including updates through Rev 5.1.1) introduces the SCRM (Supply Chain Risk Management) control family (SR) and explicitly requires an organizational overlay for systems that consume third-party software, services, and components. This card records the governance decisions that translate SP 800-53 Rev 5 SR-family and related controls (CA, CM, MA, RA, SA, SI) into a concrete overlay that ORCHORDS platforms apply during system authorization and continuous monitoring.

## Current context and source status

SP 800-53 Rev 5 is the canonical catalog of security and privacy controls for federal information systems and is the de-facto baseline in regulated industries. The SCRM overlay draws from CISA's ICT SCRM Task Force publications, NIST SP 800-161 Rev 2, and NIST IR 8270 (vendor risk practices). Treat SP 800-53 Rev 5 as the authoritative source for control numbering; treat SP 800-161 Rev 2 as the authoritative source for overlay application guidance.

## Governance workflow and controls

### 1. SR-1 / SR-2: SCRM policy and procedures

- Publish an organizational SCRM policy that names the CISO (or delegate) as accountable and that defines the SBOM retention, vendor-review, and incident-disclosure requirements.
- Review the policy at the same cadence as the information security policy.
- Cross-reference `NIST_SP_800_218_SSDF_GOVERNANCE.md` for software-development controls and `NIST_SP_800_161_R2_CYBER_SCRM_GOVERNANCE.md` for the upstream-governance inputs.

### 2. SR-3: Supply chain controls and processes

- Maintain a component inventory per system that records: component name, version, source, license, upstream maintainer, known-CVE status, and end-of-support date.
- Every component MUST have an owner (team or individual) recorded in the inventory; unowned components are unauthorized.
- Integrate the inventory with the SBOM format (SPDX or CycloneDX) and store alongside the build artifact (see `COSIGN_VERSION_GOVERNANCE.md` and `NOTARY_V2_VERSION_GOVERNANCE.md`).

### 3. SR-4: Provenance

- Every production artifact MUST carry provenance evidence meeting SLSA Build Level 2 (or stricter) and MUST be verifiable before deploy.
- Provenance MUST identify the build runner identity, the source commit, and the input parameter set.
- Unverifiable provenance is treated as a deployment-blocking condition.

### 4. SR-5 / SR-6: Acquisition strategies, tools, and methods

- Vendor selection MUST include a documented SCRM review that covers the vendor's own SBOM disclosure posture, incident-disclosure SLA, and breach-notification terms.
- Acquisition decisions that introduce a single point of failure (sole-source components) require an exception ticket and a compensating-control plan.
- Re-evaluate vendor SCRM posture at the contract renewal boundary and at least annually.

### 5. SR-7 / SR-8: Third-party standards and assessment

- Vendors that produce security-critical components MUST hold a recognized certification (SOC 2 Type II, ISO/IEC 27001, FedRAMP Moderate) and MUST provide the most recent audit report on request.
- Assessment evidence MUST be retained for the duration of the contract and at least three years after termination.
- A vendor that fails to provide evidence on request is treated as a control failure during continuous monitoring.

### 6. SR-9 / SR-10: Tamper resistance and inspection

- All production artifacts MUST be cryptographically signed; verification MUST be enforced at the admission boundary (see `COSIGN_VERSION_GOVERNANCE.md`).
- Build runners MUST be hardened (ephemeral, no persistent state, no cross-build data) and MUST be re-imaged on a published schedule.
- Physical or logical tampering of a build runner triggers an SCRM incident; see the IR plan.

### 7. SR-11 / SR-12: Component authenticity and disposal

- Component authenticity MUST be verifiable through the SBOM, the signature, and the upstream maintainer's published hash.
- Disposal of components that reach end-of-support MUST be a planned event: notify stakeholders, migrate dependencies, and remove from the inventory before the EoS date.

### 8. CA-7: Continuous monitoring

- Continuous monitoring MUST include SCRM signals: new CVEs against components in the inventory, vendor disclosure of breaches, and SLSA-level regressions.
- SCRM signals feed the POA&M and the risk register at the cadence defined by the monitoring plan.

### 9. CM-8 / CM-10: Information system component inventory and software usage restrictions

- The component inventory (from SR-3) is the authoritative component inventory for CM-8.
- Software usage restrictions (CM-10) MUST prohibit components with a published EoS date that is less than the migration lead time.

### 10. MA-6: Timely maintenance

- Vendor security patches MUST be applied within the SLA declared by the vendor and the system's service-level objectives.
- Patch deferrals MUST be risk-accepted by the system owner; deferrals older than 90 days trigger an escalation.

### 11. RA-3 / RA-5: Risk assessment and vulnerability monitoring

- Authorize every system against the SCRM overlay in addition to the baseline control set.
- Vulnerability scans MUST cover the SBOM-derived CVE list and the runtime detection feed (see `FALCO_VERSION_GOVERNANCE.md`).

## Mapping to other ORCHORDS standards

- `NIST_SP_800_218_SSDF_GOVERNANCE.md`: SDLC controls (PO, PS, PW, RV, RA, SA, SR, ST, SI) align 1:1 with SP 800-53 SR family where applicable.
- `OWASP_CICD_TOP_10_2024_GOVERNANCE.md`: each CICD-SEC item maps to one or more SR-family controls; treat as the implementation playbook.

## Review cadence

- Re-baseline the overlay at every SP 800-53 update (currently Rev 5.1.1) and at every SP 800-161 revision.
- Quarterly: validate the component inventory against production deployment records.
- Annually: re-validate vendor SCRM posture for every vendor in the register.

References: `https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final`, `https://csrc.nist.gov/publications/detail/sp/800-161/rev-2/final`, `https://csrc.nist.gov/publications/detail/sp/800-218/final`, `https://www.cisa.gov/sbom`, `https://slsa.dev/`.
