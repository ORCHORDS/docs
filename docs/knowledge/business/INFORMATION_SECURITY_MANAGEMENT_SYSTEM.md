# Information Security Management System Governance

## Scope

This article addresses the umbrella governance practices for protecting the confidentiality, integrity, and availability of information assets through an information security management system (ISMS). It draws on ISO/IEC 27001:2022 and the NIST Cybersecurity Framework (CSF) 2.0. It sits above customer-success, marketing, support, and partnership topics in this directory but treats information security as a board-level concern because of the systemic consequences of major breaches.

## Workflow

ISO/IEC 27001 organises information security management around a Plan-Do-Check-Act cycle and a set of mandatory clauses. NIST CSF 2.0 organises the same activity around six functions: Govern, Identify, Protect, Detect, Respond, and Recover. Together they describe a recurring workflow:

1. **Govern.** Governance establishes the policies, roles, and oversight needed to manage cybersecurity risk. NIST CSF 2.0 introduces the Govern function to emphasise that cybersecurity is a board and executive responsibility, not solely an IT one.
2. **Identify.** The organisation identifies the information assets, the systems that process them, and the threats and vulnerabilities applicable to them. ISO/IEC 27001 requires a statement of applicability that maps controls in Annex A to identified risks.
3. **Protect.** Protective controls include access control, awareness and training, data security, platform security, and the security of the technology development life cycle. ISO/IEC 27001 Annex A includes a broad catalogue of control objectives and controls.
4. **Detect.** Detection controls include continuous monitoring, anomaly detection, and event-detection processes. The objective is timely discovery of cybersecurity events that have bypassed preventive controls.
5. **Respond.** Response processes include incident management, analysis, mitigation, communication, and reporting. Coordination with law enforcement, regulators, and affected stakeholders is part of the response.
6. **Recover.** Recovery activities restore capabilities and services that were impaired by a cybersecurity incident and incorporate lessons learned into future planning.

## Controls and evidence

Documentation and evidence support the auditability of the ISMS. Common elements include:

- An information security policy approved by leadership and reviewed periodically.
- A statement of applicability listing Annex A controls, their applicability, and the justification for inclusion or exclusion.
- Risk-treatment plans linked to selected controls and to the owners responsible for their operation.
- Records of management review, including the inputs and outputs required by ISO/IEC 27001 clause 9.3.
- Evidence of competence, awareness, and communication activities.
- Internal audit reports and corrective-action records.
- Incident logs and post-incident reviews, including lessons learned.

## Validation

Validation sources include:

- External certification audits by accredited certification bodies against ISO/IEC 27001.
- Internal audits conducted by personnel independent of the area being audited.
- Independent testing such as vulnerability assessments and penetration tests, with remediation evidence.
- Maturity or gap assessments against the NIST CSF tiers and profiles.
- Regulatory examinations and reporting to supervisory authorities in regulated sectors such as financial services and critical infrastructure.
- Customer and partner assurance requests, including responses to security questionnaires and the publication of independent attestations.

## Failure correction

When information security incidents or control deficiencies occur, corrective action includes:

- A documented incident response that prioritises containment, eradication, and recovery while preserving evidence.
- A root-cause analysis identifying the technical, procedural, and governance factors that allowed the event.
- Notification decisions consistent with applicable breach-notification laws, sector-specific obligations, and contractual commitments.
- Corrective actions that address both the immediate control gap and the underlying governance issues — for example, unclear ownership, inadequate training, or insufficient management review.
- Follow-up testing to confirm that corrective actions operate effectively over a sustained period.

## Roles and responsibilities

Successful operation of the ISMS depends on clearly defined accountability at every level of the organisation:

- **Governing body.** Approves information security policy, accepts residual risk above management's authority, and receives periodic reporting on the effectiveness of controls. NIST CSF 2.0 expects the governing body to integrate cybersecurity risk into enterprise risk management and to oversee the organisation's cyber strategy.
- **Executive sponsor.** A named senior leader — typically the chief information security officer (CISO) or equivalent — owns the operation of the ISMS and is accountable for resource allocation, control performance, and incident response coordination.
- **Information security function.** Designs, implements, and operates the controls catalogue, monitors for control failures, and coordinates with internal audit and external assurance providers. The function maintains the statement of applicability and the risk register.
- **Process owners and asset owners.** Accountable for the controls that operate within their respective processes and for the integrity, confidentiality, and availability of the assets under their stewardship.
- **All personnel.** Required to follow applicable policies and procedures, report suspected events, and complete assigned training. ISO/IEC 27001 clause 7.2 requires the organisation to determine necessary competencies and ensure that persons doing work under its control are aware of the information security policy and their contribution.

## Limitations

ISO/IEC 27001 is a management-system standard, not a technical control catalogue. Effective implementation depends on selecting controls proportionate to the organisation's risk profile and on the competence of those applying them. NIST CSF 2.0 is a voluntary framework that complements, but does not replace, sector-specific requirements such as the New York Department of Financial Services cybersecurity regulation, the European Union NIS2 directive, or the U.S. Health Insurance Portability and Accountability Act (HIPAA) Security Rule. The frameworks are also technology-agnostic and do not prescribe specific products, vendors, or architectures.

## Canonical sources

- ISO/IEC — ISO/IEC 27001:2022, Information security, cybersecurity and privacy protection — Information security management systems — Requirements: https://www.iso.org/standard/27001
- NIST — Cybersecurity Framework 2.0 (CSWP 29, February 2024): https://www.nist.gov/cyberframework
