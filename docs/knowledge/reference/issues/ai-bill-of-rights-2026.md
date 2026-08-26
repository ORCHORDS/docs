# ai-bill-of-rights-2026

**Issue:** A US company deploys an AI system that screens job applications. The team wants to align with US AI policy but the regulatory landscape is fragmented. The Blueprint for an AI Bill of Rights provides a non-binding framework, but operationalizing it is unclear.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The US has no single binding federal AI law comparable to the EU AI Act. The de facto framework is the Blueprint for an AI Bill of Rights (White House OSTP, October 2022), with five principles. It is non-binding; the team needs to know whether to follow it and how.

## Root cause

The Blueprint outlines five principles for protecting the American public from automated systems:

1. **Safe and Effective Systems**
2. **Algorithmic Discrimination Protections**
3. **Data Privacy**
4. **Notice and Explanation**
5. **Human Alternatives, Consideration, and Fallback**

Each principle comes with associated practices for designers, developers, and deployers. The framework applies to "automated systems that have the potential to meaningfully impact the American public's rights, opportunities, or access to critical resources or services."

## The 5 principles in detail

**1. Safe and Effective Systems.** You should be protected from unsafe or ineffective systems. Pre-deployment testing, risk identification and mitigation, ongoing monitoring, independent evaluation, and reporting. Outcomes include the possibility of not deploying or removing a system.

**2. Algorithmic Discrimination Protections.** You should not face discrimination by algorithms. Proactive equity assessments, representative data, protection against proxies for demographic features, pre-deployment and ongoing disparity testing and mitigation, clear organizational oversight. Independent algorithmic impact assessments are recommended.

**3. Data Privacy.** You should be protected from abusive data practices via built-in protections. Privacy by design and by default, data minimization, use-specific consent, regular independent audits, limits on access to sensitive data and derived data, prohibition on selling/sharing sensitive data.

**4. Notice and Explanation.** You should know that an automated system is being used and understand how and why it contributes to outcomes that impact you. Plain language documentation, clear descriptions, notice that systems are in use, the responsible organization, explanations of outcomes that are clear, timely, accessible. Notice of significant use case or key functionality changes.

**5. Human Alternatives, Consideration, and Fallback.** You should be able to opt out, where appropriate, and have access to a person who can quickly consider and remedy problems. Human consideration and remedy by a fallback and escalation process if a system fails, produces an error, or the user wants to appeal.

## The 2026 US regulatory landscape

- **NIST AI RMF 1.0** (January 2023) — voluntary risk management framework; GOVERN/MAP/MEASURE/MANAGE functions
- **NIST AI 600-1 Generative AI Profile** (July 2024) — companion to AI RMF for generative AI; 12 GAI risk categories
- **Executive Order 14110** (October 2023) — required NIST to develop standards; rescinded January 2025
- **Executive Order 14179** (January 2025) — "Removing Barriers to American Leadership in AI"; current administration's pivot
- **OMB M-24-10** (March 2024) — federal agency AI use requirements; Chief AI Officer designation
- **OMB M-25-21** (2025) — further agency guidance under the new administration

The Blueprint remains the OSTP's foundational document. The NIST AI RMF is the practical operationalization.

## The in-scope test

A system is in scope of the Blueprint if it:

1. Is an automated system
2. Has the potential to meaningfully impact individuals' rights, opportunities, or access to critical resources or services

"Meaningfully impact" includes:

- **Rights:** Civil rights, civil liberties, privacy, freedom of speech, voting, protections from discrimination
- **Opportunities:** Equal access to education, housing, credit, employment
- **Access to critical resources:** Healthcare, financial services, safety, social services, government benefits

A team that has a system in any of these areas should apply the Blueprint, even though it is non-binding.

## The 5 operational practices (per principle)

For each principle, the Blueprint recommends specific practices:

| Principle | Key practices |
|---|---|
| Safe and Effective Systems | Pre-deployment testing, ongoing monitoring, independent evaluation, public reporting of safety assessments, "not deploying" as a valid outcome |
| Algorithmic Discrimination Protections | Proactive equity assessments, representative data, proxy variable analysis, pre-deployment disparity testing, ongoing testing, plain-language reporting of disparity results |
| Data Privacy | Privacy by design and default, data minimization, use-specific consent, regular audits, limits on access, no selling/sharing of sensitive data |
| Notice and Explanation | Plain language documentation, clear system descriptions, notice of use, organization responsible, outcome explanations, notice of significant changes |
| Human Alternatives | Opt-out from automated systems where appropriate, fallback to human, escalation process, accessible and equitable alternatives |

A team that implements these practices has a defensible compliance posture for the US non-binding framework.

## The interaction with state laws

Several US states have enacted AI-specific laws that overlap with or extend the Blueprint:

- **Colorado AI Act** (SB 24-205, 2024) — risk management for high-risk AI in insurance, employment, education, financial services, government, healthcare, housing, legal services
- **California AB 2013 / SB 1120** — training data transparency for generative AI
- **Illinois AI Video Interview Act** (2020, amended) — AI in hiring
- **New York City Local Law 144** (2023) — automated employment decision tools; bias audit required
- **Texas TRAIGA** (2024) — Texas Responsible AI Governance Act

A team operating in multiple states must navigate the patchwork. The most restrictive state often sets the floor for the company-wide practice.

## The 5 compliance pattern steps

1. **Scope assessment.** Identify all AI systems in the product portfolio. Classify each against the Blueprint's in-scope test.
2. **Principle mapping.** For each in-scope system, map against the 5 principles. Identify gaps.
3. **Practice implementation.** Apply the operational practices: pre-deployment testing, bias testing, privacy controls, notice, opt-out.
4. **Documentation.** Public-facing system card, internal risk register, ongoing monitoring logs.
5. **Continuous review.** Annual review; updates on system changes; regulatory change monitoring.

## The 5 best practices

1. **Follow the Blueprint voluntarily.** The non-binding status means a team that follows it voluntarily has a compliance defense if regulation tightens.
2. **Implement NIST AI RMF.** The GOVERN/MAP/MEASURE/MANAGE structure operationalizes the Blueprint.
3. **Document the algorithmic impact assessment.** Even when not legally required, it is a defensible artifact.
4. **Provide human alternatives.** The opt-out to human is the most actionable principle for B2B and B2C products.
5. **Monitor state laws.** The patchwork is the de facto compliance regime; the Blueprint is the de facto framework.

## The verification

The tell that the team is following the Blueprint:

- A documented system inventory aligned with the in-scope test
- Algorithmic impact assessments for in-scope systems
- Notice and explanation features in the product
- Human opt-out mechanisms
- Independent evaluation for high-impact systems

The tell it isn't:

- "We don't have US AI-specific obligations"
- No documentation of system impact on rights/opportunities/access
- No human opt-out
- The team cannot name which systems are in scope

## Gotchas

- **The Blueprint is non-binding, but the standards are tightening.** State laws (Colorado, California, NYC) have force. The Blueprint is the framework the states are converging toward.
- **Executive Order 14110 is rescinded.** The Trump administration's January 2025 EO 14179 reversed much of 14110, but NIST AI RMF remains in force.
- **State laws are the de facto compliance regime.** The Blueprint is the framework; states are the enforcement.
- **NIST AI RMF is voluntary for private sector.** Federal agencies must follow OMB M-24-10. Private sector adoption is voluntary but strategically smart.
- **In-scope is broader than the EU AI Act.** The Blueprint's "meaningful impact" is broader than the EU's "high-risk." A US team might be in scope of the Blueprint but not of the EU AI Act.
- **The algorithmic impact assessment is the primary artifact.** Even when not legally required, the assessment is the operationalization of the Blueprint.

## Related

- `issues/nist-ai-rmf-genai-profile-2026.md` — the operational companion
- `issues/eu-ai-act-annex-iii-2026.md` — the EU counterpart
- `lessons/ai-bias-fairness-2026.md` — algorithmic discrimination in practice
- `lessons/ai-explainability-2026.md` — notice and explanation

## Source URLs (verified 2026-08-10)

- https://aisecurityandsafety.org/en/frameworks/blueprint-for-ai-bill-of-rights/
- https://www.whitehouse.gov/ostp/ai-bill-of-rights/
- https://www.freshfields.com/en/our-thinking/blogs/a-fresh-take/the-white-houses-blueprint-for-an-ai-bill-of-rights-the-biden-administration-102i03a
- https://www.nist.gov/itl/ai-risk-management-framework
- https://www.federalregister.gov/documents/2023/11/01/2023-24283/safe-secure-and-trustworthy-development-and-use-of-artificial-intelligence
