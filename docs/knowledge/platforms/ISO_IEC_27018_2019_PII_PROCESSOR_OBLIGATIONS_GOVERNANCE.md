# ISO/IEC 27018:2019 PII Processor Obligations Governance

## Purpose

ISO/IEC 27018:2019, "Code of practice for protection of personally identifiable information in public clouds acting as PII processors," establishes controls and guidelines for implementing measures to protect Personally Identifiable Information (PII) in line with the privacy principles in ISO/IEC 29100 for public cloud service providers that act as PII processors. This article governs the application of ISO/IEC 27018 so a public cloud service provider that processes PII implements the controls the standard requires.

## Scope

The standard applies to public cloud service providers acting as PII processors. Within this knowledge base, the article covers the PII protection controls, the consent and choice mechanisms, the data subject rights support, the data breach notification, and the transparency obligations. It does not apply to PII controllers (the organization that determines the purpose and means of processing); the controller's obligations are governed by privacy laws. The standard does not replace sector privacy regulations (GDPR, CCPA, HIPAA, etc.); readers should overlay their sector requirements.

## Workflow

1. Establish the scope: identify the cloud services that process PII, the categories of PII, the data subjects, and the data flows.
3. Apply the controls from Annex A (the standard's control catalog):
   - Consent and choice: provide mechanisms to obtain and record the controller's consent where required.
   - Purpose legitimacy and specification: process PII only for the purposes specified by the controller.
   - Collection limitation: collect only the PII specified by the controller.
   - Data minimization: process only the PII needed for the purpose.
   - Use, retention, and disclosure limitation: retain PII only for the period specified by the controller; disclose only per the controller's instructions.
   - Accuracy and quality: keep PII accurate and current where the controller specifies.
   - Openness, transparency, and notice: provide the controller with the information needed to fulfill transparency obligations.
   - Individual participation and access: support the controller's response to data subject access requests.
   - Accountability: maintain records of processing; demonstrate compliance.
   - Information security: apply ISO/IEC 27002 controls; add the controls specific to public cloud PII processing.
   - Privacy compliance: monitor the regulatory environment; maintain compliance.
4. Implement the data breach notification mechanism: detect breaches; notify the controller; provide information needed for the controller's notifications to regulators and data subjects.

## Controls and evidence

PII protection evidence includes the documented scope, the controls applied, the consent records, the processing records, the breach notification records, the transparency information, and the audit records. Each material control should have an implementation and evidence record.

## Validation

Validation should confirm the controls are applied, the controller's instructions are followed, the breach mechanism operates, transparency information is available, and the audit records support a compliance review. Periodic audits by the controller or by a third party confirm the controls.

## Failure correction

Common failure modes: PII is processed beyond the controller's instructions (correct: restrict processing to the documented purpose); breach notification is slow (correct: define and rehearse the breach notification process); transparency information is incomplete (correct: provide the information the standard lists); retention exceeds the controller's instructions (correct: implement retention enforcement); audit records are not maintained (correct: maintain the records and audit them periodically).

## Limitations

ISO/IEC 27018 is a code of practice; it does not certify PII protection. The standard does not replace privacy laws; the PII controller remains responsible for the legal basis for processing. The standard does not address every aspect of privacy (e.g., automated decision-making) that may be governed by law.

## Scope note

This article summarizes project-neutral platform use of ISO/IEC 27018:2019. It does not assert any specific cloud provider's PII protection conformance or claim any certification outcome.

## Canonical sources

- ISO/IEC 27018:2019 — Code of practice for protection of personally identifiable information in public clouds acting as PII processors: https://www.iso.org/standard/76559.html
- ISO/IEC 29100:2011 — Privacy framework: https://www.iso.org/standard/45123.html