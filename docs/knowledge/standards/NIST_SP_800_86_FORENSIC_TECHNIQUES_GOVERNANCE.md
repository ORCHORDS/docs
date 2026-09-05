---
title: "NIST SP 800-86 Forensic Techniques Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-86 (September 2006); https://csrc.nist.gov/publications/detail/sp/800-86/final"
---

# NIST SP 800-86 Forensic Techniques Governance

## Purpose

NIST Special Publication 800-86, *Guide to Integrating Forensic Techniques into Incident Response* (September 2006), defines forensic-process guidance that complements SP 800-61 incident handling and SP 800-37 RMF. The publication is one of the foundational references for the order of volatility, evidence collection, integrity, and chain of custody. Profiles that govern digital evidence handling should reference SP 800-86 alongside ISO/IEC 27037, ISO/IEC 27042, and ISO/IEC 27043.

## Current context and source status

SP 800-86 was published in September 2006 and has not been revised as of September 2026. The 2006 edition remains the normative reference; newer forensic guidance has been issued in NIST IR 8389 and the current ISO/IEC 27037/27042/27043 stack. Profiles that reference SP 800-86 should call out the publication date and identify the companion documents that update the operational guidance.

## Governance workflow and controls

1. Plan: define the forensic capability scope, the legal framework, the rules of engagement, the chain-of-custody tooling, and the relationship to incident response.
2. Identify: identify sources of evidence (volatile, non-volatile), the order of volatility, and the data sources that may be required for the investigation.
3. Collect: collect evidence with documented integrity controls, including cryptographic hashes, write-blocker usage, and chain-of-custody records.
4. Examine: examine the evidence using validated tooling, documented procedures, and reproducible methods.
5. Analyze: analyze the results, build a timeline, identify indicators of compromise, and prepare findings.
6. Report: report findings with the supporting evidence, the analytical methods, the limitations, and the recommended corrective actions.
7. Treat forensic tooling as validated: use vetted tools, document validation status, and qualify tools that have not been formally validated.

## Validation and evidence

- Forensic-process documentation aligned with SP 800-86, ISO/IEC 27037, ISO/IEC 27042, and ISO/IEC 27043.
- Chain-of-custody records, evidence-integrity controls, and validated-tool inventory.
- Forensic examination reports with methodology, findings, limitations, and corrective-action recommendations.
- Periodic competency assessment for the forensic practitioners.
- Coordination procedure with legal counsel and law enforcement.

Evidence that omits the chain-of-custody records, the tool validation, or the coordination procedure does not establish SP 800-86 conformance.

## Failure correction

Common defects include ad-hoc evidence collection without documented integrity controls, missing chain-of-custody records, and unvalidated forensic tooling. Corrective actions include a mandatory evidence-collection checklist, an evidence-tracking system integrated with incident response, and a tool-validation cadence.

## Companion documents

- [ISO/IEC 27035-1:2023 Incident Management Governance](ISO_IEC_27035_1_INCIDENT_MANAGEMENT_GOVERNANCE.md)
- [ISO/IEC 27035-2:2023 Incident Response Version Transition Governance](ISO_IEC_27035_2_INCIDENT_RESPONSE_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO/IEC 27037:2012 Digital Evidence Version Transition Governance](ISO_IEC_27037_DIGITAL_EVIDENCE_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO/IEC 27042:2015 Digital Evidence Interpretation Governance](ISO_IEC_27042_DIGITAL_EVIDENCE_INTERPRETATION_GOVERNANCE.md)
- [ISO/IEC 27043:2015 Incident Investigation Principles Governance](ISO_IEC_27043_INCIDENT_INVESTIGATION_GOVERNANCE.md)
- [Cybersecurity Incident Response Playbook](../playbooks/CYBERSECURITY_INCIDENT_RESPONSE.md)
