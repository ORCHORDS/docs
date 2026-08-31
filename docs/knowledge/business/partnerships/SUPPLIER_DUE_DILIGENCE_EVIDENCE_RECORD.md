# Supplier Due Diligence Evidence Record

## Purpose

A supplier due-diligence decision should be reproducible from the evidence available at the time it was made. This record pattern is designed for information and communications technology (ICT) suppliers and follows the current NIST SP 1326 due-diligence model without treating the publication as a certification scheme or a substitute for organization-specific risk assessment.

NIST SP 1326, finalized in July 2026, describes due diligence as research into available, pertinent information about a supplier or product so that informed acquisition or existing-system decisions can be made. Its assessment components are Foreign Ownership, Control, or Influence (FOCI), provenance, resilience, foundational cyber practices, and supply-chain tiers.

## Record structure

For each material supplier review, keep a dated record containing at least:

- supplier and product or service being evaluated;
- business owner and reviewer;
- review date and decision date;
- intended use and expected access to systems, data, customers, or operations;
- supplier criticality or other internal risk classification where used;
- authoritative and public sources consulted;
- unresolved evidence gaps;
- decision, conditions, and decision owner; and
- next review trigger or review date.

The record should distinguish supplier-provided assertions from independently verified or publicly observable evidence.

## Evidence domains

### Foreign Ownership, Control, or Influence

Capture material ownership, control, jurisdiction, or influence information that could affect the acquiring organization's risk decision. Record the source and date rather than relying on an unattributed summary.

Do not infer wrongdoing from nationality, geography, or ownership alone. The purpose is to document relevant risk information and dependencies, not to create discriminatory screening rules.

### Provenance

Record information relevant to where the supplier, product, major components, software, or services originate when that information is material to the decision. Identify unknowns explicitly.

Provenance evidence can change over time as organizations restructure, products are acquired, manufacturing moves, or important dependencies change. Preserve the date and context of the evidence used.

### Resilience

Document evidence relevant to the supplier's ability to continue or recover delivery of the product or service under disruption. Depending on scope, this can include concentration risk, geographic or infrastructure dependencies, recovery arrangements, alternate capacity, and material single points of failure.

Do not convert marketing claims about availability or resilience into verified facts without supporting evidence.

### Foundational cyber practices

Record available evidence about the supplier's cybersecurity practices that is proportionate to the intended use and risk. Examples can include security documentation, vulnerability-management information, secure-development practices, incident-handling information, authentication and access controls, or independently published assessment material.

Absence of public evidence is not automatically evidence of absence. Mark information as unavailable or unverified when that is the actual state.

### Supply-chain tiers

Identify important downstream suppliers, service providers, software dependencies, hosting providers, manufacturers, or other tiers when they materially affect the product or service under review.

A complete supply chain is often not observable. The record should state known tiers, material unknowns, and any concentration or dependency that changes the risk decision.

## Source quality and freshness

Use current primary or authoritative sources where practical. For each material source, retain:

- source title or publisher;
- stable URL or document identifier;
- publication or retrieval date when relevant;
- what claim or decision input the source supports; and
- whether the source is current, superseded, draft, supplier-authored, or independently published.

If a source is later withdrawn or superseded, do not rewrite historical decision records as though the replacement existed at the time. Instead, trigger a reassessment where the change is material.

## Decision pattern

A practical review can end in one of several documented outcomes:

- **proceed** — available evidence is sufficient for the intended use and identified risk;
- **proceed with conditions** — the relationship can proceed only with explicit mitigations, contractual controls, reduced scope, additional monitoring, or evidence deadlines;
- **defer** — evidence is insufficient for a responsible decision;
- **do not proceed** — identified risk is outside the organization's accepted boundary; or
- **reassess existing use** — new evidence changes the risk position of an already-used supplier or product.

The record should explain why the outcome follows from the evidence. A numeric score alone is not a sufficient rationale unless the scoring method and thresholds are also documented.

## Reassessment triggers

Revisit the record when material facts change, including where relevant:

- ownership or control changes;
- acquisition, merger, divestiture, or major restructuring;
- material product or architecture changes;
- a significant security incident or vulnerability pattern;
- major hosting, manufacturing, or subprocessor changes;
- new sanctions, legal restrictions, or jurisdictional dependencies;
- evidence that an earlier supplier assertion was inaccurate;
- a substantial change in the organization's intended use or exposure; or
- expiry of the organization's normal review period.

A reassessment should preserve the prior record and create a new decision trail rather than silently overwriting history.

## Relationship to broader risk assessment

NIST SP 1326 is a due-diligence quick-start guide scoped to ICT suppliers. Its evidence model can inform supplier reviews and later supply-chain risk assessments, but it does not replace broader enterprise, system, legal, privacy, safety, financial, or operational due diligence required for a particular relationship.

## Sources

- NIST SP 1326 — *NIST Cybersecurity Supply Chain Risk Management: Due Diligence Assessment Quick-Start Guide*, final, July 8, 2026: https://csrc.nist.gov/pubs/sp/1326/final
- NIST — *NIST releases the finalized C-SCRM Due Diligence Assessment Quick-Start Guide*, July 8, 2026: https://www.nist.gov/news-events/news/2026/07/nist-releases-finalized-c-scrm-due-diligence-assessment-quick-start-guide
- NIST C-SCRM publications catalogue: https://csrc.nist.gov/Projects/cyber-supply-chain-risk-management/publications

## Scope note

This article is reusable documentation guidance. It does not establish a supplier approval, certification, legal conclusion, sanctions determination, or representation that any particular supplier has been assessed.