# ISO/IEC 29134 Privacy Impact Assessment Application Governance

## Purpose

Govern the application of ISO/IEC 29134 (guidelines for privacy impact assessment) so that privacy impact assessments are triggered by defined criteria, follow a consistent method, produce traceable findings with owners, and actually influence system design rather than documenting risk after decisions are locked.

## Scope

Applies to every processing of personal information by the studio that meets the assessment trigger criteria. Covers trigger definition, assessment method, finding treatment, and reassessment. Does not cover the legal bases for processing or jurisdiction-specific DPIA requirements (regulatory compliance guidance covers those).

## Workflow

1. Define assessment triggers in policy: new processing of personal information, material change to existing processing (purpose, data categories, recipients, retention), new technology introduction, and any processing matching the high-risk criteria; triggers are automatic, not discretionary.
2. Scope each assessment: the processing under assessment, its purposes, data flows, parties involved, and the technologies used — recorded before analysis begins.
3. Analyze impacts on data subjects per the 29134 method: identification of impacts on individuals (loss of control, discrimination, financial harm, reputational harm), their likelihood and severity, and existing controls.
4. Identify additional treatment measures for impacts exceeding the acceptance threshold: each measure has an owner, implementation date, and the residual impact it achieves.
5. Record the decision point: proceed, proceed with measures, or redesign — signed by the accountable owner; proceeding despite unmitigated high impact requires explicit, recorded acceptance at the appropriate authority level.
6. Maintain the assessment as living documentation: reassess on trigger events (processing change, incident affecting the processing, control failure) and version the assessment records.
7. Connect assessments to design artefacts: findings and measures reference the system design documents they change; an assessment that changed nothing in the design is a red flag for late or superficial assessment.

## Controls and evidence

- Trigger criteria policy with automatic application records.
- Assessment records: scope, impact analysis, treatment measures with owners and dates.
- Decision records with accountable owner signature.
- Reassessment records triggered by processing changes or incidents.
- Traceability from assessment measures to design artefacts.

## Validation

- Sample five processing changes from the period and confirm each triggered assessment per the criteria.
- Confirm each assessment's treatment measures have owners, dates, and evidence of implementation.
- Confirm at least one assessment measurably changed a design decision; zero design influence across all assessments indicates process failure.

## Failure correction

- **Processing launched without triggered assessment** → halt or document interim risk acceptance at authority, complete the assessment retroactively, and close the trigger automation gap.
- **Treatment measure unimplemented past due date** → escalate to the accountable owner and suspend the related processing if residual impact is high.
- **Assessment stale after processing change** → reassess immediately and version the record.

## Limitations

- 29134 provides the method; jurisdictional DPIA regimes (e.g., GDPR Article 35) impose specific legal content requirements beyond it — satisfy both.
- Impact severity assessment involves judgment; document the basis so conclusions are reviewable.
- Assessments are snapshots; continuous processing changes need trigger discipline to keep them current.

## Scope note

This article is part of the standards leaf. Cross-reference: `ISO_IEC_29134_PRIVACY_IMPACT_ASSESSMENT_GOVERNANCE.md` (security leaf), `ISO_27701_2019_PII_PROCESSOR_CONTROLS_GOVERNANCE.md` (standards leaf), and `compliance/iso-iec-27701-2025-standalone-pims-transition.md` (standards leaf).

## Canonical sources

- ISO/IEC 29134 — Information technology — Security techniques — Guidelines for privacy impact assessment: https://www.iso.org/obp/ui/#iso:std:iso-iec:29134:ed-1:en
- ISO/IEC 29134:2011 — Guidelines for privacy impact assessment (first edition): https://www.iso.org/obp/ui/#iso:std:iso-iec:29134:ed-1:en
- ISO/IEC 27701:2019 — Privacy information management: https://www.iso.org/standard/71670.html
- ISO/IEC 29151:2017 — Code of practice for PII protection: https://www.iso.org/obp/ui/#iso:std:iso-iec:29151:ed-1
- NIST Privacy Framework v1.0: https://www.nist.gov/privacy-framework
