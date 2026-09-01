# Partner Compliance Attestation Reciprocity

## Scope

This article governs when and how a partner's compliance attestation can be relied on by another party, and reciprocally, when an organization should accept or decline the attestation offered by a partner. The article applies the principle in ISO/IEC 27001:2022 — Information security, cybersecurity and privacy protection — Information security management systems — Requirements — that an information-security management system can provide assurance through independent attestation, and that the value of such attestation depends on the scope of the audit, the credibility of the auditor, and the currency of the opinion.

Reciprocity, in this article, means the mutual acceptance of attestations on equivalent or comparable scopes, with explicit conditions, defined exclusions, and an agreement on what additional evidence (if any) is required. It does not mean a free pass. A partner's SOC 2 report, ISO/IEC 27001 certificate, or sectoral attestation is one input among several, and reliance on it should be proportionate to the partner's access, criticality, and the residual uncertainty the attestation does not cover.

The scope is the use of partner attestations in this organization's governance. It does not address how this organization's own attestations are produced, how this organization responds to audit requests from partners, or how the auditor is selected.

## Workflow or implementation guidance

1. Classify the partner relationship by reliance on the partner's controls. The classification captures the categories of data, the systems reachable from the partner side, the operational criticality, and the regulatory regimes in scope. The classification determines the depth of reliance that is appropriate and the attestation evidence required.
2. Define the accepted attestation types for each tier. Common types include ISO/IEC 27001 certificates, SOC 2 Type II reports, sectoral attestations (PCI DSS, HITRUST), and national or regional certifications. State for each type what must accompany the attestation (scope statement, period covered, opinion, qualifications, complementary user entity controls, and any carve-outs).
3. Establish the acceptance conditions for an attestation. Conditions should cover: validity period, scope alignment with the partner's role in the relationship, identity and independence of the auditor, treatment of qualifications and exceptions, treatment of complementary controls that this organization would need to operate, and the period for which the attestation will be relied upon.
4. Reconcile the attestation scope to the partner's role. Where the attestation covers only part of the partner's activities that are relevant to the relationship, identify the gap and decide whether additional evidence (a bridge letter, a targeted control test, an extension of scope) is required.
5. Maintain a register of partner attestations, including the document reference, the period, the auditor, the scope, the qualifications, the complementary controls, and the next expected delivery date. The register is the working document for the governance process.
6. Set the cadence for re-review by tier. Higher reliance warrants more frequent review. SOC 2 Type II reports typically cover twelve months; the next report is the natural cadence anchor, with interim checks for any material change.
7. Re-evaluate the attestation on defined triggers: change of auditor, change of scope, qualified opinion, material restatement, incident, governance finding, contract change, or expiration of the attestation period.
8. Where reliance is significant, consider a reciprocal posture: this organization should be ready to offer its partner a comparable attestation, and should not demand evidence it would not itself produce. Reciprocity here is the discipline of being able to stand behind the same kind of evidence one is asking for.
9. Document the decision per partner: which attestations are accepted, on what scope, for what period, with what complementary controls, and what residual concerns remain. The decision is the basis for the privilege review, the data-sharing review, and any subsequent escalation.
10. Review the acceptance conditions themselves periodically. As the attestation landscape changes (new frameworks, deprecated reports, updated assurance standards), the criteria should be revised.

## Controls

Reciprocity of attestations requires controls on the acceptance side and on the production side. On the acceptance side, an attestation-validation control ensures that documents presented as attestations are not expired, are signed by an identified auditor, cover a named scope, and reach an identified opinion. A scope-reconciliation control ensures that the attestation scope maps to the partner's role. A complementary-controls control ensures that controls the partner expects this organization to operate are actually operated. On the production side, a documentation control ensures that this organization's own attestations meet the standard the program is asking partners to meet. An auditor-independence control ensures that the auditor selected is independent in the sense the relevant standard requires.

## Validation evidence

Validation evidence includes the attestation documents themselves, the scope statements, the auditor identification, the qualification records, the complementary-controls matrix, the partner-by-partner decisions captured in the register, the periodic re-review records, the bridge letters or targeted test results where gaps were identified, the trigger-driven re-evaluations, and any escalation records where reliance was reduced or withdrawn.

Evidence should be current. An attestation that has expired or has been superseded should not be relied on, regardless of how thoroughly it was reviewed when first received.

## Failure modes and correction

Common failure modes include accepting an attestation without reading the scope, scope misalignment being glossed over, qualifications being ignored, complementary user entity controls being neither communicated to the partner nor operated here, attestations being relied on past their expiry, and the reciprocity discipline breaking down because this organization would not produce the same evidence it demands. Another failure is treating a Type I report (point-in-time design) and a Type II report (over a period) as equivalent.

Correction requires re-evaluating the partner relationship in light of the failure: reducing reliance, requiring additional evidence, narrowing the scope of data or access, suspending the partnership, or terminating where the failure is material and irremediable. Where the failure is recurrent across multiple partners, the acceptance criteria themselves may need to be tightened.

## Limitations

This article is a governance discipline for the use of partner attestations. It does not replace each party's own audit program, does not establish that any particular attestation provides a defined level of assurance, and does not constitute advice on attestation selection or auditor engagement. ISO/IEC 27001 is a requirement standard for information-security management systems; this article draws on its assurance posture but does not claim that the organization is certified.

## Canonical sources

- ISO/IEC 27001:2022 — Information security, cybersecurity and privacy protection — Information security management systems — Requirements: https://www.iso.org/standard/27001
- ISO/IEC 27006:2015 — Requirements for bodies providing audit and certification of information security management systems (auditor accreditation basis): https://www.iso.org/standard/62380.html
