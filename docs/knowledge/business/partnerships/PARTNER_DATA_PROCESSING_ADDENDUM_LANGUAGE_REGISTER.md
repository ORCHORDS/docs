# Partner Data Processing Addendum Language Register

## Scope

This article governs the language register used in a data-processing addendum (DPA), data-processing agreement, or equivalent annex attached to a partnership contract that involves personal data processed on behalf of, or jointly with, another party. It exists to keep contractual wording aligned with the obligations imposed by the EU General Data Protection Regulation (GDPR) on controllers and processors, and with the European Commission's standard contractual clauses (SCCs) for transfers of personal data to third countries adopted under Implementing Decision (EU) 2021/914.

The scope is the wording register — the controlled phrases, defined terms, and obligation mappings that appear across the organization's template DPAs. It does not draft a complete contract, does not constitute legal advice, and does not replace review by qualified counsel for the specific relationship. Each DPA must still be reviewed against the parties' specific categories of data, processing purposes, sub-processors, transfers, security posture, and applicable sectoral law.

The register addresses three families of clause: clauses that mirror GDPR Article 28 processor obligations, clauses that bind the parties to the SCCs for restricted transfers, and clauses that align with the European Data Protection Board's Recommendations 01/2020 on supplementary measures. It does not attempt to reproduce the SCC modules in full; it indicates where the parties should adopt the module wording verbatim and where supplementary language is required.

## Workflow or implementation guidance

1. Maintain a single controlled-language register for DPA wording. Every approved template clause carries a version, an owner, an approval date, and a stated basis in GDPR or in the SCCs.
2. For each new partnership that involves personal data, select the controller-to-processor or joint-controller posture before drafting. The posture determines which module of the SCCs applies, which Article 28 obligations the processor takes on, and how data-subject rights are handled.
3. Map each contractual obligation to a control, a system, a named owner, and a measurable signal. Obligations written without a measurable signal cannot be enforced and tend to drift in practice.
4. Use the controller-to-processor module of the SCCs (Module Two) for transfers from a controller in the EEA to a processor outside the EEA. Use the controller-to-controller module (Module One) for transfers between controllers in different jurisdictions. Use Module Three for processor-to-sub-processor transfers where the original transfer was based on the SCCs. Use Module Four for processor-to-controller transfers.
5. For each transfer, document the transfer impact assessment, the supplementary measures considered, and the parties' conclusion. The EDPB Recommendations 01/2020 identify categories of supplementary measures — technical (for example encryption with key held in the EEA), contractual, and organizational — and the conditions under which each is appropriate.
6. Codify the processor's obligations: processing only on documented instructions, confidentiality of personnel, security of processing under Article 32, sub-processor controls under Article 28(2) and (4), data-subject rights assistance, assistance with controller obligations (Articles 32 to 36), deletion or return at end of processing, audit and inspection rights, and notification of personal-data breaches.
7. Codify the controller's obligations: choosing a processor that provides sufficient guarantees, providing documented instructions, ensuring a lawful basis, fulfilling transparency obligations, and conducting the transfer impact assessment where applicable.
8. For special-category data, criminal-conviction data, large-scale processing, or processing of children's data, add explicit clauses addressing heightened safeguards, lawful basis, and heightened transparency.
9. Include an explicit governing-law and forum clause consistent with the SCCs, taking into account the supervisory authority competent for the exporter where the SCCs leave this open.
10. Track changes to the SCCs and to EDPB guidance, and revise the register when guidance changes. Treat the register itself as a versioned asset.

## Controls

The DPA register should implement controls on its own operation. A change-management control ensures every clause update is reviewed by privacy, legal, security, and procurement before release. An applicability control ensures that the chosen clause set matches the controller/processor posture and the transfer direction. A mapping control links each contractual obligation to an operational control on the processor side, so that breach of the obligation is detectable. A version control ensures that historical DPAs remain valid against the SCC version they reference. A translation control ensures that localized variants do not silently weaken obligations. A redline control ensures that any deviation from the registered wording is reviewed and approved before signature.

## Validation evidence

Validation evidence should include the versioned register itself, dated approval records for each clause, the transfer impact assessments for restricted transfers, mapping tables from each contractual obligation to operational controls, evidence that the operational controls were operating during the period the DPA was in force (audit reports, security testing, breach records, sub-processor disclosures), evidence of data-subject-rights response within the contractual window, deletion-or-return confirmations on termination, and any post-signature amendments with their rationale.

## Failure modes and correction

Common failure modes include the SCCs being referenced but not attached, the SCCs being attached but with conflicting clauses elsewhere in the contract, sub-processors not being listed or notified as required, the data-subject-rights cooperation clause being silent on response time, the security-of-processing clause being weaker than Article 32 requires, the audit clause being unenforceable in practice, the breach-notification clause allowing too long a delay, the deletion-or-return clause being silent on retention evidence, and the transfer impact assessment being a copy-paste rather than an analysis of the specific transfer. Localized variants sometimes weaken obligations in translation; this is especially important to detect.

Correction requires identifying the weakened clause, restoring the registered wording (or a stronger variant), notifying the counterparty, and if the DPA is already signed, agreeing an amendment. Where the failure has affected data subjects, the parties must assess notification duties under GDPR Articles 33 and 34 and any sectoral rules. Repeated failure to operate the register should trigger a broader privacy-governance review.

## Limitations

This article does not replace qualified legal review for any specific relationship. It does not constitute legal advice, does not establish that any particular DPA complies with the SCCs or with GDPR, and does not address sectoral rules that may add further requirements. The clause wording described here is a starting point; final wording must be tailored to the parties' activities, data, jurisdictions, and risk profile.

## Canonical sources

- European Commission — Implementing Decision (EU) 2021/914 of 4 June 2021 on standard contractual clauses for the transfer of personal data to third countries: https://commission.europa.eu/document/fa09cbad-dd7d-4684-ae60-be03fcb0fddf_en
- European Data Protection Board — Recommendations 01/2020 on measures that supplement transfer tools to ensure compliance with the EU level of protection of personal data: https://edpb.europa.eu/our-work-tools/our-documents/recommendations/recommendations-012020-measures-supplement-transfer_en
- GDPR — Article 28 (Processor obligations): https://gdpr-info.eu/art-28-gdpr/
