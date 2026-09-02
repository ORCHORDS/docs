# NIST SP 800-61 r3 Incident Response Legal Coordination Governance

## Purpose
Establish the governance pattern for coordinating incident response activities with legal, regulatory, and contractual obligations as described in NIST SP 800-61 r3, particularly under its new "Authority, Reporting, and Communication" life-cycle phase.

## Scope
Applies to every security incident response engagement that may result in regulatory disclosure, contractual notification, civil or criminal litigation, or law-enforcement coordination.

## Workflow
1. Identify applicable regulatory regimes (GDPR, NIS2, HIPAA, GLBA, state breach laws) and contractual obligations at the start of every engagement, based on data types and customer profiles involved.
3. Engage legal counsel within 60 minutes of engagement for incidents likely to require disclosure; record the counsel's identity and the engagement timestamp.
5. Maintain an evidence-handling log that documents chain of custody, including hashes, custodian identity, and access events.
7. Prepare a draft notification within 24 hours of engagement and route it through legal review before transmission.
9. Coordinate with law enforcement per local jurisdictional rules; record contact attempts, decisions, and outcomes in the engagement file.

## Controls and evidence
- Applicable regulatory matrix keyed to data classification, customer contract, and jurisdiction.
- Engagement log recording counsel identity, regulator contact, decision timestamp, and evidence custody entries.
- Notification draft register with version, reviewer, transmission status, and approved-by record.
- Law-enforcement contact log with date, contact, instructions received, and outcomes.

## Validation
- Run a tabletop that exercises a GDPR-style breach and confirm the notification draft is produced within the agreed timeline.
- Verify the chain-of-custody log by hashing three randomly-selected evidence items and comparing to log entries.
- Confirm that all counsel-of-record entries in the engagement log are current (within the last 12 months).

## Failure correction
- **Counsel engagement delayed beyond policy timeline** → root-cause the delay, retrain responders, and document corrective action in the post-incident review.
- **Chain-of-custody gap detected** → investigate the gap, document the impact assessment, and re-validate custody from the point of detection forward.
- **Unauthorised disclosure** → engage legal counsel immediately, document the disclosure scope, and execute a written redaction and response plan.

## Limitations
- SP 800-61 r3 was published in April 2025 and remains under active community revision; consult the latest version.
- Local legal requirements can vary substantially; this article provides a governance pattern, not a substitute for jurisdiction-specific legal advice.
- Law-enforcement coordination depends on jurisdiction, agency, and incident type; the response is necessarily case-specific.

## Scope note
This article is part of the security leaf. Cross-reference: ENISA_THERMAL_AND_REMOTELY_EXPLOITABLE_VULN_DISCLOSURE_GOVERNANCE.md, FIRST_CVSS_V4_0_SCORING_GOVERNANCE.md, ISO_IEC_27035_3_2023_INCIDENT_RESPONSE_EXERCISES_GOVERNANCE.md.

## Canonical sources
- NIST SP 800-61 r3 (Computer Security Incident Handling Guide): https://csrc.nist.gov/pubs/sp/800/61/r3/ipd
- NIST SP 800-86 (Guide to Integrating Forensic Techniques into Incident Response): https://csrc.nist.gov/pubs/sp/800/86/final
- ISO/IEC 27035-1:2023 Information security incident management: https://www.iso.org/standard/78975.html
- ENISA NIS2 Directive implementation guidance: https://www.enisa.europa.eu/topics/nis-directive
- FIRST.org PSIRT Services Framework: https://www.first.org/standards/frameworks/psirts/psirt-services-framework-v1.1