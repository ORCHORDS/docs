# ISO/IEC 42001 AIMS Statement of Applicability Template Governance

## Purpose

ISO/IEC 42001:2023, *Information technology — Artificial intelligence — Management system*, defines a management-system standard for artificial intelligence. Annex A of ISO/IEC 42001:2023 contains 93 reference controls organized into nine control themes (AI-related policies, internal organization, resources, impact assessment, system lifecycle, data for AI, third-party and customer, awareness and communication, use and responsible use of AI systems). A reusable Statement of Applicability (SoA) template records, for each Annex A control, the applicability (applicable, not applicable), the implementation status (implemented, partially implemented, not implemented), the justification for applicability, the implementation evidence reference, and the explicit risk-treatment decision.

The template must remain generic: it MUST NOT embed real organization identifiers, control owners, customer names, or implementation evidence that identifies a specific AI system.

## Scope

This template applies to ISO/IEC 42001:2023 Annex A controls and supports the AIMS scope defined in Clause 4. It does not address ISO/IEC 42001:2023's normative clauses (Clauses 4-10); those are governed by separate AIMS documentation. The template does not substitute for the ISO/IEC 42001:2023 audit checklist (which captures Clause-level conformance), nor does it address ISO/IEC 23894 (AI risk management), which has a separate risk-treatment template.

## Workflow

1. Open the template and complete the header with the SoA identifier, the AIMS scope, the assessment date, the AI management representative, and the version of the AIMS.
2. For each Annex A control (organized by theme), populate:
   - Control identifier (for example A.2.1, A.5.1, A.6.1.4) and title.
   - Applicability: applicable or not applicable, with justification.
   - Implementation status: implemented, partially implemented, not implemented, or not applicable.
   - Implementation evidence: policy identifier, procedure reference, technical control reference, training record.
   - Risk-treatment decision: modify, retain, avoid, share (per ISO/IEC 42001 Clause 6.1 and 6.2).
   - Residual risk rating if the control is partially implemented or not implemented.
3. Identify AI-related controls that require special attention: those related to bias (A.5.4), explainability (A.6.3), data quality (A.7.2, A.7.4), and post-market monitoring (A.9.4).
4. Reconcile the SoA with the AI risk register so the same risk does not appear twice with conflicting treatment decisions.
5. Save the completed SoA alongside the AI risk register and AIMS scope statement, with access restricted to the AI management representative and the executive sponsor.

## Controls and evidence

- Header records SoA identifier, scope, version, date, and AI management representative.
- Per-control rows record applicability, status, evidence, risk-treatment decision, and residual risk.
- Priority control register records AI-bias, explainability, data-quality, and post-market monitoring controls.
- Reconciliation log records SoA and AI risk register consistency checks.

## Validation

- Every Annex A control is addressed; no control is left unaddressed.
- "Not applicable" controls have a documented justification.
- "Not implemented" controls have a documented risk-treatment decision and residual-risk acceptance.
- The priority control register includes all bias, explainability, data-quality, and post-market monitoring controls.
- The SoA is reviewed annually or after a significant change in the AI system inventory.

## Failure correction

Common defects include marking controls as "not applicable" without justification, omitting risk-treatment decisions for "not implemented" controls, and allowing the SoA and AI risk register to diverge. Corrective actions include restoring the applicability justification, requiring risk-treatment decisions for non-implemented controls, and reconciling the SoA and AI risk register on a quarterly cadence.

## Limitations

- The template does not substitute for the AIMS documentation required by ISO/IEC 42001:2023 Clauses 4-10.
- It does not address ISO/IEC 23894 (AI risk management) controls, which have a separate SoA-like document.
- It does not cover ISO/IEC TS 4213 (AI bias testing), which has separate documentation requirements.
- It does not address national AI regulations (EU AI Act, NIST AI RMF), which require separate compliance documentation.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **standards** (ISO/IEC 42001 and adjacent standards), **security** (AI-related security controls), **business** (AI risk management and regulatory mapping), and **engineering** (AI system lifecycle governance). The template should be used together with those sibling-leaf articles.

## Canonical sources

- ISO/IEC 42001:2023, *Information technology — Artificial intelligence — Management system* (ISO): https://www.iso.org/standard/81230.html
- ISO/IEC 23894:2023, *Information technology — Artificial intelligence — Risk management* (ISO): https://www.iso.org/standard/77304.html
- ISO/IEC TS 4213:2022, *Information technology — Artificial intelligence — Assessment of machine learning classification performance* (ISO): https://www.iso.org/standard/79799.html

Sources were verified on September 1, 2026.