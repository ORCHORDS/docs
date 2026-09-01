# ISO/IEC 27001:2022 Annex A Control Themes

## Purpose

ISO/IEC 27001 defines the requirements for an Information Security Management System (ISMS). The 2022 revision retains the high-level structure of prior editions while reorganizing its Annex A controls into four thematic areas instead of the prior 14-control-objective domains. This article summarizes the 2022 control themes as a reference for engineering teams that need to interpret the new taxonomy when designing or reviewing controls. It is not a conformity audit guide.

## Themes introduced in the 2022 revision

ISO/IEC 27001:2022 reorganizes Annex A into four control themes:

- **People controls**, covering human resource security, screening, terms of employment, awareness and education, disciplinary process, and termination or change of employment.
- **Physical controls**, covering physical security perimeters, physical entry, securing premises, storage media, environmental threats, working in secure areas, and equipment lifecycle controls.
- **Technological controls**, covering endpoint security, privileged access rights, information access restriction, secure authentication, capacity management, change management, backup, data destruction, data leakage prevention, logging, network controls, cryptographic protection, secure development, supplier relationship security, and similar platform- and software-oriented controls.
- **Organizational controls**, covering policies, information security roles and responsibilities, segregation, threat intelligence, information classification, information labeling, access control policy, supplier management, incident management planning and response, business continuity, legal compliance, intellectual property protection, protection of records, privacy of personally identifiable information, independent review, and the policies governing the use of cryptography.

A second part of the control catalog, Annex A of ISO/IEC 27001:2022, contains 93 controls distributed across these four themes. The number will evolve as the standard is periodically revised; the thesis is the structure, not the count.

## Why the re-organization matters

The themes align directly with operational accountability rather than with abstract domains. People and Physical controls are typically implemented by human resources and facilities teams, while Technological controls typically involve platform, infrastructure, and engineering teams. Organizational controls are usually the responsibility of information security, legal, compliance, and senior leadership. Mapping controls to themes makes shared-responsibility models easier to design and review because each theme has a clearer ownership profile than the legacy domain list.

The themes also reinforce the focus on attributes that ISO/IEC 27001:2022 highlights for each control: control type (preventive, detective, corrective), information security properties (confidentiality, integrity, availability), cybersecurity concepts (identify, protect, detect, respond, recover), operational capabilities (governance, asset management, protection, etc.), and security domains.

## Adoption workflow

1. Confirm ISO/IEC 27001:2022 is the active edition before starting or extending implementation work.
2. Map current ISO/IEC 27001:2013 controls to the 2022 themes and identify any controls that are now combined, renamed, or merged.
3. Review the 11 new controls introduced in 2022 (including threat intelligence, information security for use of cloud services, ICT readiness for business continuity, and data masking) and assess applicability.
4. Assign theme-level ownership to operational functions that have the right authority and resources.
5. Review the Statement of Applicability against the 2022 control list and update justifications and inclusion or exclusion decisions.
6. Adjust internal audit coverage and evidence gathering to reflect theme-based ownership.
7. Update management review inputs to surface theme-level performance, not just control-by-control compliance rates.

## Validation evidence

Retain the Statement of Applicability, control mapping tables, theme-level ownership assignments, control implementation evidence for each applicable control, internal audit reports structured by theme, management review minutes with theme-level performance data, the risk register aligned with ISO/IEC 27005 guidance, and any nonconformity or corrective action records. Where controls are inherited from a parent organization or a service provider, retain the inheritance mapping and the residual controls retained internally.

Validation should compare actual control behavior against the control's intent and not just against the documented procedure. A control that is documented but not exercised produces false confidence.

## Failure modes

Common failures include:

- treating the re-organization as cosmetic when it shifts control ownership and audit coverage;
- missing the small number of new 2022 controls that did not exist in 2013;
- leaving the Statement of Applicability static while actual control scope drifts;
- mapping controls to themes in documentation but not changing operational ownership;
- waiting for the certification cycle before performing internal audits, and thereby losing the value of feedback on the new theme structure;
- performing theme-based reporting without denominators that allow risk-based prioritization.

## Threat intelligence and the new 2022 control families

Among the new controls introduced in 2022, **threat intelligence** and **information security in cloud services** are of particular operational significance. Threat intelligence requires the organization to collect and analyze information about threats, evaluate that information against its own services and assets, and produce structured output that other controls can consume. Information security in cloud services requires the organization to define responsibilities with cloud providers, demand evidence that the cloud environment meets stated requirements, and document the residual responsibilities the organization retains. Both controls belong to the Organizational theme and benefit from being owned by an information security function that operates across the platform boundary.

## Statement of Applicability as a managed artifact

The Statement of Applicability is the central artifact that records which Annex A controls apply, whether each applicable control is implemented, and the justification for inclusion or exclusion. It is the cross-reference for internal audit, certification audit, and the ISMS management review. Operations teams should treat the SoA as a managed artifact under change control rather than a static document: each row should reference evidence, the evidence location, and the latest verification date; each change should follow the same change-control pathway as other ISMS deliverables. An SoA whose rows point to evidence that has moved or expired becomes a misleading inventory at audit time.

## Integrating with supplier relationships

Annex A 2022 introduces and expands controls that govern suppliers. These controls require the organization to define supplier security requirements, monitor compliance with those requirements, and manage supplier risks across the lifecycle of the relationship. Operations teams that consume supplier services should establish the supplier-side evidence once and replicate the supplier's assertions across the services that depend on the supplier, rather than asking each consuming service to re-validate.

## Canonical sources

- ISO/IEC 27001:2022, Information security, cybersecurity and privacy protection — Information security management systems — Requirements: https://www.iso.org/standard/27001
- ISO/IEC 27002:2022, Information security, cybersecurity and privacy protection — Information security controls (implementation guidance): https://www.iso.org/standard/75615.html
- ISO/IEC 27001 family overview: https://www.iso.org/standards/popular/iso-iec-27001-family

## Scope note

This article summarizes control-theme changes introduced in 2022 and does not provide a conformity assessment. Adoption decisions should be made against the current ISO/IEC 27001 and ISO/IEC 27002 texts and with input from qualified auditors.
