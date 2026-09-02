# ISO/IEC 19944:2017 Cloud Data Lifecycle Governance

## Purpose

ISO/IEC 19944:2017, "Information technology — Cloud — Data and their flow across devices and cloud services," defines a cloud computing data and data flow framework that addresses data classification, the data flow model across devices and cloud services, and the security and data protection considerations for data at the various stages of the cloud data lifecycle (capture, store, process, share, archive, dispose). This article governs the application of ISO/IEC 19944 so an organization can describe, classify, and govern the data flows between devices, cloud services, and on-premises systems with the discipline the standard requires.

## Scope

The standard applies to any organization using or providing cloud services. Within this knowledge base, the article covers the data flow framework (CDUs — Cloud Data Units, data categories, data flow), the cloud data lifecycle stages, the data classification scheme, and the documentation of data flows. It does not replace sector-specific data protection regulations; readers should overlay their sector requirements.

## Workflow

1. Identify the data categories the organization handles (personal data, sensitive personal data, financial data, confidential business data, public data, etc.).
2. Map the data flows across devices and cloud services:
   - Where the data is captured.
   - Where it is stored.
   - Where it is processed.
   - Where it is shared (between cloud services, with third parties).
   - Where it is archived.
   - Where it is disposed.
3. Apply the appropriate controls at each lifecycle stage:
   - Capture: minimize the data captured; classify at capture; obtain consent where required.
   - Store: protect at rest; segregate per classification; apply retention policies.
   - Process: protect in use; control access; log processing.
   - Share: enforce controls at the boundary; verify the recipient's protections; maintain provenance.
   - Archive: protect at rest; apply retention until end of retention period.
   - Dispose: apply the chosen disposal method (NIST SP 800-88 r2) for each storage media.
4. Document the data flow model and the controls. Update the model on changes to the data flows.

## Controls and evidence

Data lifecycle controls include the data classification scheme, the data flow model, the controls applied at each lifecycle stage, and the disposal records. Evidence includes the data flow diagrams, the classification records, the access controls, and the disposal evidence.

## Validation

Validation should confirm the data categories are documented, the data flows are mapped and current, the controls are applied at each lifecycle stage, and the disposal records are complete. Periodic data flow reviews confirm the model reflects actual practice.

## Failure correction

Common failure modes: data flows are not mapped (correct: produce a data flow model for each system that handles data); classification is applied but controls are not matched to the classification (correct: align controls with classification); disposal is informal (correct: apply a documented disposal method with evidence); sharing across cloud services is not governed (correct: define the sharing policy and enforce at the boundary).

## Limitations

ISO/IEC 19944 is a framework; it does not certify any specific data flow or deployment. The standard does not prescribe specific technical controls; the organization selects the controls that fit its context. The standard does not replace data protection regulations (GDPR, CCPA, etc.); readers should overlay their sector requirements.

## Scope note

This article summarizes project-neutral platform use of ISO/IEC 19944:2017. It does not assert any specific deployment's conformance or claim any certification outcome.

## Canonical sources

- ISO/IEC 19944:2017 — Information technology — Cloud — Data and their flow across devices and cloud services: https://www.iso.org/standard/66675.html
- ISO/IEC 27018:2019 — Code of practice for protection of personally identifiable information in public clouds acting as PII processors: https://www.iso.org/standard/76559.html