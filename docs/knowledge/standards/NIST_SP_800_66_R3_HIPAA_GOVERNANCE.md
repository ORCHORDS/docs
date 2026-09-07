# NIST SP 800-66 Rev. 3 (2024) HIPAA Security Rule Implementation Governance

## 1. Scope
This standard establishes governance requirements for implementing the HIPAA Security Rule within covered entities and business associates. It operationalizes NIST SP 800-66 Rev. 3 (2024) guidance, mapping administrative, physical, and technical safeguards to auditable controls. The standard applies to all systems that create, receive, maintain, or transmit electronic protected health information (ePHI). It supports the Office for Civil Rights (OCR) enforcement posture and aligns with the HHS Security Rule at 45 CFR Part 164 Subpart C.

## 2. Normative references
- 45 CFR Part 164 Subpart C, HIPAA Security Rule
- 45 CFR Part 164 Subpart D, Breach Notification Rule
- NIST SP 800-66 Rev. 3, Implementing the HIPAA Security Rule (2024)
- NIST SP 800-53 Rev. 5, Security and Privacy Controls
- NIST SP 800-30 Rev. 1, Guide for Conducting Risk Assessments
- HITRUST CSF v11, Information Security Framework
- AICPA TSC 2017 (SOC 2), Trust Services Criteria

## 3. Terms and definitions
ePHI (Electronic Protected Health Information): individually identifiable health information held or transmitted in electronic form by a covered entity or business associate, as defined at 45 CFR 160.103.
HHS (Health and Human Services): the United States Department of Health and Human Services, the federal executive department responsible for HIPAA administration and OCR oversight.
Covered Entity: a health plan, healthcare clearinghouse, or healthcare provider that transmits health information in electronic form, per 45 CFR 160.103.
Business Associate: a person or entity performing functions or services involving PHI on behalf of a covered entity, per 45 CFR 160.103.

## 4. Background
NIST SP 800-66 Rev. 3 supersedes Rev. 2 (2008) and aligns HIPAA Security Rule mapping with the risk-based methodology of NIST SP 800-53 Rev. 5. The revision responds to the HIPAA Modernization Act of 2023 and the HITECH amendments. The document provides guidance, not regulation, but remains the authoritative implementation reference for OCR auditors. The HHS Office for Civil Rights enforces the Security Rule through audits, breach investigations, and monetary penalties under the tiered penalty matrix.

## 5. HIPAA Security Rule administrative safeguards
The administrative safeguard category at 45 CFR 164.308 comprises the following implementation specifications:
- Security management process (164.308(a)(1)): risk analysis, risk management, sanction policy, information system activity review.
- Workforce security (164.308(a)(3)): authorization or supervision, workforce clearance, termination procedures.
- Information access management (164.308(a)(4)): isolating health care clearinghouse functions, access authorization, access establishment and modification.
- Training (164.308(a)(5)): security awareness, security reminders, password management, protection from malicious software, log-in monitoring, password standards.
- Incident procedures (164.308(a)(6)): response and reporting.
- Contingency plan (164.308(a)(7)): data backup, disaster recovery, emergency mode operation, testing and revision, applications and data criticality analysis.
- Evaluation (164.308(a)(8)): periodic technical and non-technical evaluation.
- Business associate agreements (164.308(b)(1)): written contract or other arrangement. See [BAA-inventory.md:1] for the canonical register template.

## 6. HIPAA Security Rule physical safeguards
The physical safeguard category at 45 CFR 164.310 comprises:
- Facility access controls (164.310(a)(1)): contingency operations, facility security plan, access control and validation, maintenance records.
- Workstation use (164.310(b)): policies and procedures specifying proper functions, manner, and environment.
- Workstation security (164.310(c)): physical safeguards to restrict access to authorized users.
- Device and media controls (164.310(d)(1)): disposal, media re-use, accountability, data backup and storage.

## 7. HIPAA Security Rule technical safeguards
The technical safeguard category at 45 CFR 164.312 comprises:
- Access control (164.312(a)(1)): unique user identification, emergency access procedure, automatic logoff, encryption and decryption.
- Audit controls (164.312(b)): hardware, software, and procedural mechanisms recording system activity.
- Integrity (164.312(c)(1)): protecting ePHI from improper alteration or destruction.
- Person authentication (164.312(d)): verifying the identity of the accessing party.
- Transmission security (164.312(e)(1)): integrity controls and encryption when transmitting ePHI electronically.

## 8. Risk analysis and risk management requirements
A formal risk analysis per 45 CFR 164.308(a)(1)(ii)(A) shall inventory all ePHI assets, identify threats and vulnerabilities, assess likelihood and impact, and document residual risk. Risk management per 164.308(a)(1)(ii)(B) shall implement security measures to reduce risk to reasonable and appropriate levels. The risk register at [risk-register.md:1] tracks findings, owners, and remediation status through closure.

## 9. Breach notification and incident response
Incidents affecting 500 or more individuals require HHS notification within 60 days via the OCR breach portal at 45 CFR 164.408. Sub-500 incidents are reported annually. Affected individuals must be notified without unreasonable delay and no later than 60 days after discovery. Media notification is required for breaches affecting residents of any state or jurisdiction. Documentation shall be retained for six years per Section 11.

## 10. HITRUST CSF and SOC 2 cross-mappings
The HIPAA Security Rule maps to HITRUST CSF v11 domains 01 (Access Control), 02 (Audit Logging), 05 (Risk Management), 06 (Compliance), 09 (Endpoint Protection), 10 (Password Management), and 12 (Network Security). SOC 2 Common Criteria CC6.1, CC6.6, CC7.2, and CC8.1 satisfy corresponding Security Rule provisions when evidence demonstrates ePHI scope coverage. See [mapping-matrix.md:1] for the authoritative crosswalk.

## 11. Compliance evidence
Audit log retention shall align to HIPAA requirements with a minimum six-year retention period per 45 CFR 164.316(b)(2)(i). Security-relevant logs, access reports, and incident documentation shall be retained in tamper-evident storage with chain-of-custody controls. BAA inventory shall enumerate every business associate agreement with scope, services, PHI categories, effective dates, renewal dates, and termination triggers. Workforce training records shall document annual HIPAA awareness training, role-based security training, sanction policy acknowledgements, onboarding attestations, and termination acknowledgements. Evidence packages shall be indexed per [evidence-index.md:1] to support OCR audit response within regulatory timeframes.

## 12. Risk register
The risk register shall capture identifier, asset, threat, vulnerability, likelihood, impact, inherent risk, applied controls, residual risk, owner, and target closure date. Risks above the organizational tolerance threshold require documented exception approval from the Security Officer and Privacy Officer. Register entries inherit the template at [risk-register.md:1] and feed the remediation backlog tracked in [remediation-backlog.md:1].

## 13. Review cadence
This standard is reviewed at least annually and following any material regulatory change, including HHS rulemaking, NIST publication updates, or enforcement guidance. Findings feed the risk register and the remediation backlog, and reviewed versions supersede prior editions upon approval by the Security Officer.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.