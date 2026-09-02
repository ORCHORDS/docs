# NIST SP 800-144 Guidelines on Public Cloud Use Governance

## Purpose

NIST SP 800-144, "Guidelines on Security and Privacy in Public Cloud Computing," supplements SP 800-53 r5 and the NIST Cloud Computing Reference Architecture by providing guidance on the security and privacy challenges specific to public cloud deployments. The publication addresses the economic and operational advantages of public cloud, the security and privacy considerations, the cloud computing reference architecture, and the recommendations for organizations using public cloud services. This article governs the application of SP 800-144 so public cloud adoption decisions incorporate the security and privacy considerations the publication identifies.

## Scope

The publication applies to any organization using public cloud services. Within this knowledge base, the article covers the public cloud security and privacy challenges, the recommendations for public cloud adoption, the cloud computing reference architecture (cloud consumer, provider, carrier, auditor, broker), and the documentation of public cloud usage decisions. It does not cover private or hybrid cloud specifics (those use SP 800-145 and other NIST guidance).

## Workflow

1. Identify the public cloud services the organization uses or plans to use. For each service, identify the data, the workloads, and the compliance requirements.
3. Assess the security and privacy challenges:
   - Confidentiality: data in transit, at rest, and in use; data residency; key management.
   - Integrity: configuration management; vulnerability management; change control.
   - Availability: service-level agreements; backup and recovery; multi-region considerations.
   - Privacy: data classification; consent; data subject rights support; PII protection.
3. Apply the publication's recommendations:
   - Choose services aligned with the organization's security and privacy requirements.
   - Implement the shared responsibility model — understand what the provider handles and what the organization handles.
   - Apply defense in depth — multiple controls at different layers.
   - Use identity and access management as the primary control plane.
   - Maintain data portability and exit planning.
   - Conduct ongoing monitoring and incident response.
4. Document the public cloud adoption decisions, the security and privacy assessment, and the controls applied.

## Controls and evidence

Public cloud controls include the documented assessment, the shared responsibility mapping, the controls applied at the customer layer, the monitoring records, and the incident response coordination. Each public cloud service should be documented in the SSP with its controls and risks.

## Validation

Validation should confirm the assessment is performed, the shared responsibility is understood and documented, the customer controls are implemented, the monitoring operates, and the adoption decisions are reviewed periodically. Periodic audits confirm the posture remains aligned with the requirements.

## Failure correction

Common failure modes: shared responsibility is not understood and the provider is expected to handle customer-layer responsibilities (correct: document the shared responsibility model and the customer's responsibilities); data residency is not considered (correct: identify the data residency requirements and select services that meet them); exit planning is absent (correct: develop and an exit strategy with data portability); ongoing monitoring is not implemented (correct: implement monitoring of the customer-layer controls and provider performance).

## Limitations

NIST SP 800-144 is guidelines; it does not certify any public cloud deployment. The publication does not address every cloud service type (serverless, edge compute, etc.); the principles apply but the specifics may need additional research. Sector regulations may impose specific public cloud requirements; readers should overlay their sector requirements.

## Scope note

This article summarizes project-neutral platform use of NIST SP 800-144. It does not assert any specific deployment's conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-144 — Guidelines on Security and Privacy in Public Cloud Computing: https://csrc.nist.gov/publications/detail/sp/800-144/final
- NIST SP 800-145 — The NIST Definition of Cloud Computing: https://csrc.nist.gov/publications/detail/sp/800-145/final
- NIST SP 800-146 — Cloud Computing Synopsis and Recommendations: https://csrc.nist.gov/publications/detail/sp/800-146/final