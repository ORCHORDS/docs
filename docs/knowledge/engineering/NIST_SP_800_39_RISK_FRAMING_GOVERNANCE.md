# NIST SP 800-39 Risk Framing Governance

## Purpose

NIST Special Publication 800-39, "Managing Information Security Risk — Organization, Mission, and Information System View," defines the multi-tier risk management approach that underpins NIST's risk management publications: Tier 1 (organization), Tier 2 (mission/business process), and Tier 3 (information system). The publication establishes risk framing, risk assessment, risk response, and risk monitoring activities at each tier and the relationships between tiers. This article governs Tier 1 risk framing — how the organization establishes its risk assumptions, constraints, priorities, and tolerances that propagate down to mission and system tiers.

## Scope

The publication applies to federal organizations and to any organization adopting NIST's risk management approach. Within this knowledge base, the article covers Tier 1 risk framing (risk assumptions, risk constraints, risk priorities, risk tolerances), the relationship between Tier 1 framing and downstream tiers, and the documentation that supports risk decisions. It does not replace the system-level risk assessment in NIST SP 800-30; readers should consult 800-30 for Tier 3 assessments.

## Workflow

1. Identify the risk assumptions at Tier 1: assumptions about threats, vulnerabilities, the organization's mission, and the operating environment that are taken as given when risks are assessed.
2. Identify the risk constraints at Tier 1: constraints imposed by law, regulation, policy, available resources, technical limitations, or organizational culture that bound what risk responses are feasible.
3. Establish risk priorities: classify information systems, mission processes, and assets by their importance to the organization's mission, so that risk decisions at lower tiers can weigh them appropriately.
4. Define risk tolerances at Tier 1: the level of risk the organization is willing to accept in pursuit of its mission, expressed for the categories that matter to the organization.
5. Communicate Tier 1 framing down to Tier 2 and Tier 3 so that mission and system tiers operate within the same assumptions, constraints, priorities, and tolerances.
6. Monitor and adjust Tier 1 framing on changes to mission, environment, or strategic posture.

## Controls and evidence

Tier 1 framing evidence includes the documented risk assumptions, the documented risk constraints, the risk priority classification, the documented risk tolerances, and the communication records that propagate Tier 1 framing to lower tiers. Each Tier 2 and Tier 3 risk decision should be traceable back to the Tier 1 framing that informed it.

## Validation

Validation should confirm Tier 1 framing is documented and current, the framing is communicated to the responsible tiers, Tier 2 and Tier 3 risk decisions align with Tier 1 priorities and tolerances, and the framing is reviewed on changes to mission or environment. Spot checks should confirm that risk decisions at lower tiers cite the relevant Tier 1 framing.

## Failure correction

Common failure modes: Tier 1 framing is missing or undocumented (corrective: produce the framing artifacts and have them approved at the appropriate level); framing is defined but not communicated (corrective: include Tier 1 framing in onboarding and in Tier 2/3 planning); lower-tier risk decisions do not cite framing (corrective: require a framing reference in each risk decision record); framing is not updated on mission change (corrective: schedule a framing review on mission change and on strategic posture change).

## Limitations

NIST SP 800-39 establishes the multi-tier risk management structure; it does not replace detailed risk assessment methods. The publication assumes the organization has the governance authority and resources to maintain Tier 1 framing; smaller organizations may treat tiers in a more compressed way but should preserve the purpose of each tier. The publication does not prescribe specific risk metrics or risk scoring schemes.

## Scope note

This article summarizes project-neutral engineering use of NIST SP 800-39. It does not assert any specific organization's risk management conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-39 — Managing Information Security Risk: Organization, Mission, and Information System View: https://csrc.nist.gov/publications/detail/sp/800-39/final
- NIST SP 800-30 r1 — Guide for Conducting Risk Assessments: https://csrc.nist.gov/publications/detail/sp/800-30/rev-1/final