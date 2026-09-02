# ISO/IEC 27005 Risk Treatment Plan Template Governance

## Purpose

ISO/IEC 27005:2022, *Information security, cybersecurity and privacy protection — Guidance on managing information security risks*, defines a risk-management process that pairs risk identification with risk treatment: modification, retention, avoidance, or sharing. The risk treatment plan (RTP) template records, for each identified risk, the chosen treatment option, the associated controls (typically drawn from ISO/IEC 27002:2022), the implementation owner and target date, the residual risk after treatment, and the explicit acceptance by an authorized owner. The template makes the decision auditable and prevents treatment decisions from being made implicitly during operational change.

The template must remain generic: it MUST NOT embed real system identifiers, control owners, customer names, or risk-appetite dollar values.

## Scope

This template applies to information-security risk treatment under ISO/IEC 27005:2022 and supports the Statement of Applicability (SoA) referenced in ISO/IEC 27001:2022 Clause 6.1.3. It does not replace the SoA itself and does not address non-information-security risks (financial, environmental, occupational health), which are governed by the organization's enterprise risk management framework. The template does not address the risk-assessment methodology itself (qualitative, semi-quantitative, quantitative); the chosen methodology is captured in a separate risk-assessment methodology document.

## Workflow

1. Open the template and complete the header with the assessment identifier, the methodology used (qualitative, semi-quantitative, quantitative), the assessment scope, and the date.
2. For each identified risk, populate:
   - Risk identifier, asset affected, threat, vulnerability, and existing-control description.
   - Inherent likelihood and inherent impact using the chosen scale.
   - Chosen treatment option (modify, retain, avoid, share).
   - For "modify": selected controls (referencing ISO/IEC 27002 Annex or a custom control identifier), implementation owner, target completion date.
   - For "share": insurance, contractual, or outsourcing mechanism.
   - Residual likelihood and residual impact after treatment.
   - Explicit acceptance sign-off by the named risk owner.
3. Cross-reference the risk treatment plan entries with the Statement of Applicability so the same control does not appear twice with conflicting status.
4. Identify risks that are accepted above the risk appetite; route them to the executive risk committee for documented acceptance.
5. Save the completed RTP alongside the risk register and SoA, with access restricted to risk owners and the security steering committee.

## Controls and evidence

- Header records methodology, scope, and date.
- Per-risk rows record inherent and residual rating, treatment option, controls, owner, target date.
- Acceptance sign-off block records the named risk owner for each risk.
- Cross-reference column links each "modify" entry to the corresponding SoA control.
- Risk-appetite-exceeded register lists risks escalated to executive acceptance.

## Validation

- Each risk has an explicit treatment decision; no risk is left in an "undecided" state without an owner.
- Each "modify" entry identifies at least one control and one owner with a target date.
- Residual ratings are computed using the same scale as the inherent rating.
- The RTP and SoA are reconciled: every control referenced in the RTP appears in the SoA with a consistent status.
- Acceptance signatures are present for risks retained without treatment.

## Failure correction

Common defects include omitting acceptance sign-off, treating risk as a one-time exercise rather than a continuous process, allowing "modify" entries without target dates or owners, and letting the RTP and SoA diverge. Corrective actions include restoring the sign-off discipline, scheduling recurring risk reviews, and reconciling the RTP and SoA on a quarterly cadence.

## Limitations

- The template does not define a risk-assessment methodology; it assumes one is selected.
- It does not address privacy-impact assessment specifically; entities subject to ISO/IEC 27701 should run a parallel privacy-risk process and link the two.
- It does not provide quantitative loss data; for quantitative analyses, a separate FAIR-based or probabilistic model is required.
- It does not substitute for legal review of contractual risk-sharing mechanisms.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **security** (control selection guidance), **standards** (ISO/IEC 27001:2022 and 27002:2022), **business** (enterprise risk management), and **operations** (risk-register maintenance and SoA change control). The template should be used together with those sibling-leaf articles.

## Canonical sources

- ISO/IEC 27005:2022, *Information security, cybersecurity and privacy protection — Guidance on managing information security risks* (ISO): https://www.iso.org/standard/80585.html
- ISO/IEC 27001:2022, *Information security, cybersecurity and privacy protection — Information security management systems — Requirements* (ISO): https://www.iso.org/standard/82875.html
- ISO/IEC 27002:2022, *Information security, cybersecurity and privacy protection — Information security controls* (ISO): https://www.iso.org/standard/75652.html

Sources were verified on September 1, 2026.
