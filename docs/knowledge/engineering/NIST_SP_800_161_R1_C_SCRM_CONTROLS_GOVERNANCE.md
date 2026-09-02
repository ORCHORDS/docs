# NIST SP 800-161 r1 Cybersecurity Supply Chain Risk Controls Governance

## Purpose

NIST SP 800-161 r1, "Cybersecurity Supply Chain Risk Management Practices for Systems and Organizations," updated to align with NIST SP 800-53 r5 and NIST SP 800-37 r2, expands the Cybersecurity Supply Chain Risk Management (C-SCRM) guidance to cover enterprise-wide practices for identifying, assessing, responding to, and monitoring supply chain risks across the system life cycle. This article governs how engineering teams select, tailor, and apply C-SCRM controls so that supply chain risks are treated alongside cyber risks in the project's control baseline.

## Scope

The publication applies to any organization that procures, develops, integrates, or operates systems with third-party components, software, or services. Within this knowledge base, the article covers the C-SCRM control families, the application of C-SCRM overlays to a system security plan, the supply chain risk assessment activities, and the documentation of supply chain controls. It does not cover contractual mechanisms for supply chain assurance (these are typically addressed in the procurement and contracts domain).

## Workflow

1. Establish the C-SCRM context: identify the organization's mission reliance on external suppliers, the categories of third-party components in use, and the regulatory requirements that apply to supply chain assurance.
2. Identify suppliers and components that warrant C-SCRM attention: critical components, components with elevated threat exposure, components from suppliers of concern, and components that affect safety-critical functions.
3. Conduct a supply chain risk assessment for each identified supplier or component category: threat, vulnerability, likelihood, impact, and risk determination.
4. Select C-SCRM controls from the families in SP 800-161 r1 (governance, risk assessment, controls, life cycle, and the supporting controls that map to SP 800-53). Apply the controls as an overlay to the existing control baseline.
5. Implement the controls: supplier evaluation, software bills of materials, integrity verification, provenance attestation, supplier incident coordination, and end-of-life planning.
6. Monitor C-SCRM risks continuously: supplier posture changes, vulnerability disclosures affecting components, and changes to the threat landscape.
7. Respond to identified supply chain risks with the chosen risk treatment (avoid, reduce, transfer, accept).

## Controls and evidence

C-SCRM evidence includes the C-SCRM plan, the supplier list with risk classification, the supply chain risk assessments, the SBOM and integrity artifacts for components, the supplier agreements with the chosen C-SCRM clauses, the incident response coordination records, and the monitoring records. Each system security plan that applies a C-SCRM overlay should cite the overlay and reference the supporting artifacts.

## Validation

Validation should confirm the C-SCRM context is documented, the supplier and component risk classifications are current, the controls in the overlay are implemented, the SBOM is maintained for the components that warrant it, and supply chain incidents are coordinated with suppliers per the documented process. Spot checks should confirm a sample of components can be traced to their supplier and to their risk treatment.

## Failure correction

Common failure modes: C-SCRM is treated as a procurement activity and not integrated with engineering (corrective: integrate C-SCRM into the engineering process from requirements through retirement); SBOM is produced for compliance but not maintained (corrective: maintain SBOM as part of the configuration baseline and update on each component change); supplier risks are not re-assessed on incident (corrective: trigger a supplier risk re-assessment on supplier incident or significant change); controls are selected but not implemented (corrective: for each control in the overlay, document the implementation and the evidence).

## Limitations

NIST SP 800-161 r1 provides the C-SCRM framework and the control catalog; it does not prescribe supplier evaluation methods or supplier-specific obligations. The publication does not address contractual mechanisms directly (those are governed by procurement and contracts guidance). The publication assumes the organization has baseline cyber controls in place; C-SCRM augments rather than replaces them.

## Scope note

This article summarizes project-neutral engineering use of NIST SP 800-161 r1. It does not assert any specific organization's C-SCRM conformance or claim any supplier assurance outcome.

## Canonical sources

- NIST SP 800-161 r1 — Cybersecurity Supply Chain Risk Management Practices for Systems and Organizations: https://csrc.nist.gov/publications/detail/sp/800-161/rev-1/final
- NIST SP 800-53 r5 — Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final