# Privacy Information Management Governance

## Scope

This article covers the umbrella governance discipline of a privacy information management system (PIMS), which establishes and maintains policies, procedures, and controls for the processing of personally identifiable information (PII). It draws on ISO/IEC 27701:2019, which extends ISO/IEC 27001 and ISO/IEC 27002 into privacy management, and on the OECD Privacy Guidelines, which provide the enduring international baseline for the governance of personal data. It addresses the management system rather than individual customer data-request workflows, which are covered in the customer-success and support collections.

## Workflow

ISO/IEC 27701 adds privacy-specific requirements and controls to an information security management system and organises them for two distinct roles — PII controllers and PII processors. The recurring workflow is:

1. **Establish context and privacy policy.** The organisation determines the internal and external issues relevant to PII processing, the interested parties, and the scope of the PIMS. A privacy policy is established that reflects the applicable data-protection regime(s) and the organisation's obligations as controller or processor.
2. **Determine role: controller or processor.** The standard applies different control sets depending on whether the organisation determines the purposes and means of processing (controller) or processes PII on behalf of another (processor). Cloud providers, business-process outsourcers, and analytics vendors commonly act as processors and therefore adopt the processor control set.
3. **Assess and document processing.** Data inventories and processing records identify the categories of PII, purposes, legal bases or justifications, recipients, retention periods, and cross-border transfer mechanisms. Privacy risk assessments identify harms to individuals — not only harms to the organisation — and drive treatment decisions.
4. **Select and implement controls.** Privacy controls operate across collection limitation, data minimisation, purpose specification, use limitation, security safeguards, openness, individual participation, and accountability. The OECD Privacy Guidelines articulate these principles, and ISO/IEC 27701 Annexes A–D map them to operational controls.
5. **Support data-subject rights.** Processes exist to receive and act on requests from individuals for access, correction, erasure, restriction, portability, and objection, within the timeframes required by the applicable regime.
6. **Monitor, audit, and improve.** Performance evaluation, internal audit, management review, and corrective action maintain and improve the PIMS. Evidence of accountability — records, policies, assessments, and training — is retained as documentation of compliance.

## Controls and evidence

Typical evidence supporting privacy governance includes:

- A privacy policy and, where applicable, controller–processor agreements allocating responsibilities for PII processing.
- Records of processing activities (data maps) with data categories, purposes, retention, recipients, and transfer mechanisms.
- Privacy impact or data-protection impact assessments for high-risk processing, including methodology, findings, and treatment decisions.
- Lawful-basis or justification records for each processing purpose.
- Consent records where consent is the basis, including the time, wording, and scope of the consent captured.
- Evidence of data-subject right fulfilment — request logs, response times, and outcomes.
- Cross-border transfer safeguards, such as contractual clauses or adequacy findings.
- Records of privacy training, incident response involving PII, and breach notifications.
- Internal audit findings and management review records.

## Validation

Validation draws on:

- Certification or third-party attestation against ISO/IEC 27701, typically issued together with ISO/IEC 27001 certification.
- Internal audits of privacy controls and of compliance obligations under the applicable data-protection regime.
- Independent verification by supervisory authorities — for example, audits and investigations under the EU General Data Protection Regulation or equivalent national regimes.
- Customer second-party audits and standardised assurance requests (such as responses to privacy questionnaires and independent attestations).
- Periodic review of the data inventory against actual systems and data flows, which frequently reveals undocumented processing.

## Failure correction

Common PIMS failures and their remedies:

- **Undocumented processing discovered late.** Shadow systems and untracked exports undermine the entire control set. Corrective action includes automated data discovery, refresh of the records of processing, and gating of new processing on privacy review.
- **Retention not enforced.** Policies that state retention periods but are not technically enforced accumulate unnecessary PII. Correction requires data-deletion pipelines, legal-hold integration, and periodic attestation by system owners.
- **Vendor oversight gaps.** Processors engaged without flow-down of privacy obligations leave the controller exposed. Corrective action includes contract clauses, diligence records, and periodic reassessment of vendor controls.
- **Data-subject requests mishandled.** Late or incomplete responses to rights requests are a common enforcement theme. Correction includes a tracked workflow with timers, identity-verification standards, and exception handling.
- **Breach response gaps.** Slow detection or unclear notification decisions aggravate harm. Corrective action includes rehearsed playbooks, defined notification decision authority, and post-incident review.

## Limitations

ISO/IEC 27701 is a management-system extension and does not constitute legal compliance with any specific data-protection statute. The GDPR, the California Consumer Privacy Act, Brazil's LGPD, and other regimes impose binding obligations, supervisory authorities, and penalties that the standard does not replace. The OECD Privacy Guidelines are intergovernmental guidance directed at member-country law rather than at enterprise certification, although their principles are reflected in most national regimes. Emerging areas — including privacy considerations for artificial intelligence, automated decision-making, and cross-border government access — continue to develop and may impose requirements beyond the 2019 edition of the standard.

## Canonical sources

- ISO/IEC — ISO/IEC 27701:2019, Security techniques — Extension to ISO/IEC 27001 and ISO/IEC 27002 for privacy information management — Requirements and guidelines: https://www.iso.org/standard/71670.html
- OECD — OECD Privacy Guidelines (OECD Guidelines on the Protection of Privacy and Transborder Flows of Personal Data): https://www.oecd.org/digital/privacy/
