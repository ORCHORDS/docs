# NIST Privacy Framework 1.0 Governance

## Purpose

Govern the application of the NIST Privacy Framework v1.0 so that privacy risk is managed with the same discipline as cybersecurity risk: the framework's Core functions (Identify-P, Govern-P, Control-P, Communicate-P, Protect-P) structure the program, the Profiles express current and target states, and the Tier expresses rigor — producing measurable privacy risk management rather than policy statements.

## Scope

Applies to the studio's privacy risk management program for personal data processing. Covers the framework's Core functions, Profile construction, and Tier assessment. Does not cover privacy legal compliance determination (counsel's domain) or the ISMS (27001 governs that).

## Workflow

1. Build the Current Profile: map existing privacy activities to the Core's subcategories — what the organization actually does today across Identify-P (data inventory, conditions for processing), Govern-P (policies, roles), Control-P (data minimization, disaggregation), Communicate-P (transparency, data subject interaction), and Protect-P (security controls for privacy events).
2. Define the Target Profile: the subcategory outcomes the organization commits to, driven by business requirements, risk appetite, and legal obligations; the gap between Current and Target is the action plan.
3. Assess the Tier honestly: the implementation tier (1 Partial, 2 Risk Informed, 3 Repeatable, 4 Adaptive) describes rigor of privacy risk governance processes — Tier inflation is self-deception with external consequences.
4. Prioritize the action plan from the gap: gap items ranked by privacy risk (problematic data actions and their impact) — the same risk-based prioritization discipline as security.
5. Integrate with the cybersecurity program: Protect-P overlaps security controls; the privacy framework expects coordination, not duplicated implementations.
6. Roll out Profiles per processing domain where scale warrants: organization-wide for smaller operations; per-product or per-jurisdiction profiles where privacy risk concentrates.
7. Review Profiles and Tier on cadence and on change: new processing, new data types, or incidents re-open the Profile assessment.

## Controls and evidence

- Current Profile with subcategory mappings and evidence links.
- Target Profile with commitment rationale.
- Tier assessment record with justification.
- Action plan with prioritized gap items, owners, and dates.
- Coordination records with the security program.
- Review cadence records.

## Validation

- Sample five Current Profile entries and confirm each maps to verifiable practice, not aspiration.
- Confirm the action plan's top items trace to identified privacy risks.
- Confirm the Tier assessment's justification matches observable process rigor.

## Failure correction

- **Profile maps aspirations as current** → correct to actual practice; inflated Current Profiles corrupt the gap analysis.
- **Action plan stalled** → escalate resourcing; a stalled privacy action plan with rising data processing accumulates risk silently.
- **Tier claimed above evidence** → realign the Tier claim; overstated Tiers mislead relying parties.

## Limitations

- The Privacy Framework is risk management infrastructure, not compliance law; legal obligations layer on separately by jurisdiction.
- Version 1.0 (2020) predates current AI-era processing patterns; supplement with AI-specific risk guidance (NIST AI RMF, ISO/IEC 23894).
- Tiers describe process rigor, not privacy outcomes; good process can still produce individual harms.

## Scope note

This article is part of the security leaf. Cross-reference: `ISO_IEC_29134_2023_PRIVACY_IMPACT_ASSESSMENT_APPLICATION_GOVERNANCE.md` (standards leaf), `ISO_IEC_29151_PERSONALLY_IDENTIFIABLE_INFORMATION_GOVERNANCE.md` (standards leaf, where present), and `NIST_PRIVACY_FRAMEWORK_1_0` companion guidance.

## Canonical sources

- NIST Privacy Framework v1.0 — A Tool for Improving Privacy through Enterprise Risk Management: https://www.nist.gov/privacy-framework
- NIST Privacy Framework — Core and Profiles documentation: https://pages.nist.gov/privacy-framework/
- NIST SP 800-37 Rev 2 — Risk Management Framework (integration model): https://csrc.nist.gov/pubs/sp/800/37/rev-2/final
- NIST AI Risk Management Framework 1.0: https://www.nist.gov/itl/ai-risk-management-framework
- ISO/IEC 27701:2019 — Privacy information management: https://www.iso.org/obp/ui/#iso:std:iso-iec:27701:ed-1
