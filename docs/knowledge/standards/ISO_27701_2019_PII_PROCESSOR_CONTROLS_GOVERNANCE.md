# ISO/IEC 27701 PII Processor Controls Governance

## Purpose

Govern the application of ISO/IEC 27701:2019's PII processor control set (Annex B) so that when the studio acts as a PII processor — processing personal information on behalf of a controller — the processor-specific controls are implemented and evidenced: processing per controller instructions, sub-processor management, data return and deletion, and records that demonstrate all of it.

## Scope

Applies to every processing activity where the studio is a PII processor. Covers Annex B (PII processor controls) implemented as an extension of the ISO/IEC 27001 ISMS. Does not cover controller-side obligations (Annex A), nor the underlying ISMS.

## Workflow

1. Maintain the processor processing register: each processing activity with controller, purposes (as instructed), categories of PII, systems, sub-processors, retention, and cross-border transfer basis.
2. Anchor each engagement in controller instructions: the contract or instructions define permitted processing; processing beyond instructions without documented controller authorization is a control failure, whatever the operational motive.
3. Manage sub-processors per the control set: authorization flow (controller notice/objection where required), due diligence, flow-down obligations, and a current sub-processor list available to controllers.
4. Implement data return and deletion capability per engagement: on termination or instruction, return or delete per contract terms, and evidence the action (certificates, deletion logs) rather than assert it.
5. Support controller obligations: assist with data subject requests, breach notification, and impact assessments to the extent the contract requires, with defined response processes and timelines.
6. Apply technical and organizational measures consistent with the stated guarantees: the measures record (from the ISMS) must match what controllers are told; a gap between promised and actual measures is a finding.
7. Audit the processor control set on the ISMS audit cycle: internal audit covers Annex B controls with the same rigor as 27001 Annex A.

## Controls and evidence

- Processor processing register with per-engagement entries.
- Instruction anchor records: contracts and documented authorizations for processing changes.
- Sub-processor register with authorization flow and due diligence records.
- Return/deletion evidence per terminated engagement.
- Controller support process records (DSR assistance, breach support) with response times.
- Internal audit results covering Annex B controls.

## Validation

- Sample five processing activities and confirm each traces to controller instructions and a contract.
- Confirm the sub-processor list shown to controllers matches the actual sub-processor register.
- Confirm the last terminated engagement has return/deletion evidence on file.

## Failure correction

- **Processing beyond instructions discovered** → stop the processing, notify the controller, document the authorization gap, and fix the change-control path that allowed it.
- **Sub-processor used without authorization flow** → regularize with the controller or terminate the sub-processor; assess the data exposure during the gap.
- **Deletion unevidenced** → perform and evidence deletion, notify the controller of the delay, and fix the evidence step in offboarding.

## Limitations

- 27701:2019 extends 27001:2013/27002:2013; the standards' later revisions may re-align clause mappings — track updates.
- Processor obligations ultimately derive from contracts and law; 27701 organizes controls but does not replace legal review.
- Controller vs processor roles can differ per processing activity; classify per activity, not per customer.

## Scope note

This article is part of the standards leaf. Cross-reference: `ISO_27018_CLOUD_PII_TEMPLATE_GOVERNANCE.md` (templates leaf), `ISO_IEC_29134_2023_PRIVACY_IMPACT_ASSESSMENT_APPLICATION_GOVERNANCE.md`, and `compliance/iso-iec-27701-2025-standalone-pims-transition.md` (standards leaf).

## Canonical sources

- ISO/IEC 27701:2019 — Security techniques — Privacy information management: https://www.iso.org/standard/71670.html
- ISO/IEC 27001:2013/AMD 1:2016 — Information security management systems: https://www.iso.org/obp/ui/#iso:std:iso-iec:27001:ed-2
- ISO/IEC 27018:2019 — Code of practice for PII in public clouds (PII processors): https://www.iso.org/standard/76559.html
- ISO/IEC 29151:2017 — Code of practice for PII protection: https://www.iso.org/obp/ui/#iso:std:iso-iec:29151:ed-1
- GDPR — Regulation (EU) 2016/679 Article 28 (processor): https://eur-lex.europa.eu/eli/reg/2016/679/oj
