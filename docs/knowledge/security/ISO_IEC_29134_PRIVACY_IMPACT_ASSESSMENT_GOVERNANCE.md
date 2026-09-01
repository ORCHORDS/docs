# ISO/IEC 29134 Privacy Impact Assessment Governance

## Purpose

ISO/IEC 29134:2017, *Information technology — Security techniques — Guidelines for privacy impact assessment*, is the international standard published by the International Organization for Standardization (ISO) and the International Electrotechnical Commission (IEC) that establishes guidelines for conducting a Privacy Impact Assessment (PIA). The standard is complementary to ISO/IEC 27001 (information security management), ISO/IEC 27701 (privacy information management), and ISO/IEC 27018 (public-cloud PII protection).

This article summarizes a governance pattern for adopting ISO/IEC 29134:2017 practices without assuming that the adopting organization operates under a specific privacy law or regulator. It does not constitute legal advice and does not assert compliance with any privacy regulation such as the EU GDPR, the UK GDPR, the US HIPAA, or PIPEDA.

## Scope

A PIA under ISO/IEC 29134 examines a specific processing operation and documents privacy risks, mitigations, residual risk, and the basis for proceeding. A reusable program should document:

- the operations in scope for PIA (which may include new projects, new vendors, new data flows, or periodic reviews of existing operations);
- the threshold criteria that trigger a PIA;
- the relationship between the PIA and adjacent activities (risk assessment, security assessment, data-protection impact assessment under privacy law, transfer impact assessment, vendor risk assessment); and
- the governance pathway by which the PIA is approved and reviewed.

The standard deliberately separates the *process* of assessing privacy risk from any specific legal definition of personal data. Adopting organizations should retain their own definitions and lawful-basis reasoning in the records they keep.

## Workflow

A reusable ISO/IEC 29134 PIA process runs as a small cycle.

1. **Frame the assessment.** Identify the processing operation, the controller or processor relationship, the data categories, the data subjects, the legal basis (where applicable), and the existing controls.
2. **Map the processing.** Document the data flow from collection through retention and disposal, including recipients, cross-border transfers, and joint controllers or subprocessors.
3. **Identify and assess privacy risks.** Consider risks to the data subjects (for example unauthorized access, excessive collection, function creep, secondary use, profiling harm, loss of control) and risks to the organization (regulatory, reputational, operational).
4. **Identify mitigations.** Determine the controls that reduce likelihood or impact. Distinguish planned controls from controls already in place.
5. **Evaluate residual risk.** Determine whether the residual risk is acceptable, and under what conditions. Document the basis for acceptance.
6. **Consult.** Allow internal and external review where appropriate. Record comments and how they were addressed.
7. **Approve and retain.** Capture the assessment, the approvals, and any conditions or commitments.
8. **Review on change.** Reassess when the operation, the threat picture, the legal environment, or the controls change materially.

## Controls and evidence

A PIA under ISO/IEC 29134 produces a structured record. A program should retain the following evidence for each assessment.

| PIA element | Typical content | Typical evidence |
|---|---|---|
| Context | Operation, controller, processor, applicable law | Charter, governance documents |
| Data inventory | Categories of data, sources, recipients, transfers | Data-mapping documents, data-flow diagrams |
| Legal basis | Lawful basis under applicable law (where relevant) | Basis statement, contractual notice |
| Identified risks | Risk scenarios for data subjects and organization | Risk register, threat scenarios |
| Mitigations | Controls, residual risk, conditions | Control inventory, residual-risk statement |
| Consultation | Internal review, DPO comments, data subject consultation | Review log, comment tracker |
| Approval | Approver, date, conditions | Approval record |
| Review schedule | Triggers and cadence | Review calendar, change-detection record |

A program should retain at minimum: the assessment document, with version and date; the consultation log; the approval record; the data flow diagrams; the residual-risk statement and the basis for acceptance; and the schedule for the next review.

## Validation

Validation confirms that the PIA was actually performed and that its conclusions are still correct. Useful activities include:

- reviewing recent processing operations and confirming that an in-date PIA exists where required;
- comparing the operation as currently running against the data-flow and control descriptions in the most recent PIA;
- confirming that mitigation owners and due dates were honored;
- reviewing the approval record for appropriate authority;
- reviewing how identified risks have been tracked and treated over time; and
- independent peer review of a sample of assessments to confirm consistent application of the methodology.

Validation must distinguish compliant, non-compliant, and unable-to-assess outcomes. An operation that has been described but not formally assessed should be treated as unassessed, not as compliant.

## Failure correction

When a PIA control fails, follow a documented path.

1. Confirm the failure with reproducible evidence.
2. Identify whether the failure is in scope determination, data mapping, risk identification, mitigation planning, approval, or review.
3. Apply the corrective change through the change management process.
4. Verify with new evidence rather than a closed ticket.
5. Update the methodology or training if the failure is systemic.

Common failure modes include:

- treating the PIA as a one-time approval rather than as a living record;
- describing the design intent instead of the actual processing operation;
- omitting subprocessors, third-country transfers, or secondary uses;
- adopting mitigations without owners, due dates, or evidence of completion;
- accepting residual risk without specifying the conditions under which it is acceptable; and
- failing to reassess after a material change in the operation or the threat picture.

## Limitations

ISO/IEC 29134:2017 is a methodology standard. It does not prescribe thresholds for what counts as acceptable risk, what counts as personal data, or how cross-border transfers should be handled. Those determinations come from applicable law and from the organization's own risk tolerance.

The standard also does not, on its own, constitute a data-protection impact assessment under any specific privacy law. Adopting organizations must align the PIA process with the legal regimes applicable to their operations.

## Canonical sources

- ISO/IEC 29134:2017 — *Information technology — Security techniques — Guidelines for privacy impact assessment*, ISO store catalog page: https://www.iso.org/standard/71159.html
- ISO/IEC 27001:2022 — *Information security, cybersecurity and privacy protection — Information security management systems — Requirements* (IMS context for a privacy program): https://www.iso.org/standard/27001
- ISO/IEC 27701:2019 — *Security techniques — Extension to ISO/IEC 27001 and ISO/IEC 27002 for privacy information management — Requirements and guidelines* (PIMS, formerly developed as ISO/IEC 27552): https://www.iso.org/standard/71670.html

## Scope note

This article summarizes reusable governance practices derived from ISO/IEC 29134:2017. It is not a substitute for the ISO/IEC standard, does not assert conformity with any privacy regulation, and does not constitute legal advice regarding personal data processing.
