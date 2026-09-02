# NIST IR 8441 Cybersecurity Supply Chain Risk Governance

## Purpose
Establish the governance pattern for applying NIST IR 8441 (Cybersecurity Supply Chain Risk Management — Findings, Evidence, and Monitoring) to record, retain, and act upon supply-chain risk findings across the software supply chain.

## Scope
Applies to every upstream component, vendor relationship, third-party service, and downstream consumer of the studio's software artefacts that is in scope of the studio's C-SCRM program.

## Workflow
1. Capture each supply-chain finding using the IR 8441 finding schema: identifier, affected component, severity, evidence reference, and remediation status.
3. Store evidence artefacts (scan results, attestation reports, audit summaries) with a content address and signed manifest.
5. Map each finding to the SP 800-161 r1 control family it informs (e.g., supplier assessment, provenance, integrity verification).
7. Define remediation or acceptance actions with owner, target date, and re-evaluation trigger; record actions in the C-SCRM register.
9. Reassess each open finding quarterly; close findings that have been remediated and verified, or escalate unresolved findings to the risk register.

## Controls and evidence
- IR 8441 finding register with status (Open, In Progress, Accepted, Closed), evidence hash, and review date.
- Evidence manifest with content-addressed entries and verifier signature.
- C-SCRM control mapping table linking finding categories to SP 800-161 r1 control families.
- Remediation backlog with priority, owner, and due date.

## Validation
- Replay three randomly-selected findings, verify the evidence hash, and confirm the status reflects the current state.
- Run a quarterly scan that exercises the entire supply-chain scope, then reconcile new findings with the register.
- Confirm that every Accepted finding has compensating controls documented.

## Failure correction
- **Evidence manifest hash mismatch** → stop using the manifest, regenerate from authoritative source, and document the discrepancy in a post-mortem.
- **Finding open beyond 90 days** → escalate to the C-SCRM owner and produce a written remediation or acceptance decision.
- **Missing C-SCRM mapping** → assign the mapping within 14 days, retrain the responsible team, and update the policy.

## Limitations
- NIST IR 8441 is a draft publication; refer to the latest revision for definitive schema details.
- The studio's C-SCRM scope is necessarily limited to components within reach of available scanning and provenance tooling.
- Some upstream vendors may not publish findings in a format compatible with IR 8441; in such cases, manual normalisation is required.

## Scope note
This article is part of the security leaf. Cross-reference: NIST_SP_800_161_R1_C_SCRM_PROGRAM_GOVERNANCE.md, NIST_SP_800_218A_SSDF_TAGGING_GOVERNANCE.md, MITRE_D3FEND_DETECTION_COUNTERMEASURE_GOVERNANCE.md.

## Canonical sources
- NIST IR 8441 (Cybersecurity Supply Chain Risk Management — Findings, Evidence, and Monitoring): https://csrc.nist.gov/pubs/ir/8441/ipd
- NIST SP 800-161 r1 (C-SCRM Practices): https://csrc.nist.gov/pubs/sp/800/161/r1/final
- NIST SP 800-218 (SSDF v1.1): https://csrc.nist.gov/pubs/sp/800/218/final
- ISO/IEC 27036-1:2022 (Supplier relationships): https://www.iso.org/standard/82905.html
- ENISA — Threat Landscape for Supply Chain: https://www.enisa.europa.eu/publications/threats-and-vulnerabilities-to-ict-supply-chains