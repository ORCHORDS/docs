# ASD Australian Cyber Security Framework 2024 Governance

## Purpose
Establish the governance pattern for aligning the studio's security posture with the Australian Signals Directorate (ASD) Cyber Security Framework (CSF) 2024, including the Essential Eight maturity model and the Information Security Manual (ISM) controls.

## Scope
Applies to Australian deployments, services delivered to Australian government clients, and any organisation seeking ASD-aligned cybersecurity posture as a baseline for assurance review.

## Workflow
1. Map the studio's existing controls against the ASD CSF 2024 categories and the Essential Eight maturity model.
3. Establish a target maturity per Essential Eight mitigation (Maturity Level 0–3) based on the sensitivity of the data handled.
5. For each control identified as below target, draft a remediation plan with owner, deadline, and acceptance criteria.
7. Maintain an evidence repository that includes configuration exports, change records, screenshots, and audit logs cited by the relevant ISM control number.
9. Re-run the maturity assessment quarterly and adjust the target maturity as the threat landscape or data classification changes.

## Controls and evidence
- Maturity assessment table showing Essential Eight mitigation, current maturity, target maturity, gap, owner, and review date.
- ISM control cross-reference table linking internal policies to specific ISM control identifiers.
- Evidence repository snapshot with hash-signed manifest for integrity.
- Remediation plan backlog with priority scoring based on maturity gap and threat relevance.

## Validation
- Run a sample audit against 10 randomly-selected ISM controls to confirm the evidence repository is intact, current, and traceable to the control objective.
- Recompute the Essential Eight maturity score and reconcile with the previous quarter; investigate any unplanned regression.
- Validate that the evidence manifest hash matches the hash stored in the studio's content-addressed store.

## Failure correction
- **Maturity regression in a critical mitigation (e.g., application control, multi-factor authentication)** → suspend production changes for affected systems, escalate to the CISO, and produce a recovery plan within five business days.
- **Evidence repository integrity failure** → restore from backup, document the incident, and re-validate all hashes.
- **ISM control mapping missing** → assign an owner, document the mapping within 14 days, and add to the next quarterly review.

## Limitations
- ASD CSF 2024 is one of many cybersecurity frameworks; it does not by itself provide assurance of compliance with sector-specific requirements (e.g., PCI DSS, HIPAA).
- Essential Eight maturity levels are guidance-based; some mitigations may be impractical in certain deployment contexts, requiring compensating controls that must be documented.
- The ISM is updated frequently; always reference the latest published version.

## Scope note
This article is part of the security leaf. Cross-reference: FIRST_CVSS_V4_0_SCORING_GOVERNANCE.md, NIST_SP_800_218A_SSDF_TAGGING_GOVERNANCE.md, NCSC_UK_ACTIVE_CYBER_DEFENCE_KNOWLEDGE_GOVERNANCE.md.

## Canonical sources
- ASD Cyber Security Framework 2024: https://www.cyber.gov.au/cyber-security-framework
- ASD Information Security Manual: https://www.cyber.gov.au/ism
- ASD Essential Eight maturity model: https://www.cyber.gov.au/essential-eight
- ASD Strategies to mitigate targeted cyber intrusions: https://www.cyber.gov.au/threat-defence
- Australian Government — Security of Critical Infrastructure (SOCI) Act rules: https://www.cisc.gov.au/soci-act