# ISO 22317:2019 Business Impact Analysis Governance

## Purpose

Govern the application of ISO 22317:2019 (security and resilience — business continuity management systems — guidelines for business impact analysis, BIA) so that business impact analysis is performed as a structured method: impacts assessed against time, prioritization derived from evidence, and resource requirements identified — producing the recovery priorities and objectives that continuity strategies must satisfy.

## Scope

Applies to the studio's BIA activity within the business continuity management system. Covers the BIA method, impact assessment, prioritization, and the resulting recovery time and recovery point objectives. Does not cover continuity strategy design or exercise programmes (covered separately).

## Workflow

1. Scope the BIA deliberately: which products, services, and supporting activities are analyzed, at what granularity, and by whom — with scope decisions recorded before data collection begins.
2. Collect impact data against defined impact types per the guideline's categories (financial, legal/regulatory, contractual, reputational, safety, and societal), assessed over elapsed time from disruption rather than as single-point estimates.
3. Determine prioritization from the data: rank activities by the urgency their impact-over-time curves show; prioritization follows the evidence, not organizational politics or the loudest service owner.
4. Derive recovery objectives: recovery time objectives from the point where impacts become unacceptable, and recovery point objectives from tolerable data loss — each objective traced to the impact assessment that produced it.
5. Identify dependencies: the upstream activities, suppliers, systems, people, and information each prioritized activity depends on; dependencies absent from the analysis produce recovery plans that fail at their first missing link.
6. Identify resource requirements for recovery: minimum staff, systems, information, and suppliers needed within the RTO — the gap between minimum and normal operations is the continuity strategy's design constraint.
7. Review and refresh: re-run the BIA on the defined cadence and on trigger events (new services, dependency changes, post-incident findings); an unrefreshed BIA silently invalidates the continuity strategies built on it.

## Controls and evidence

- BIA scope record with granularity and participant decisions.
- Impact assessment data per activity, per impact type, over time.
- Prioritization ranking derived from assessment data.
- RTO/RPO statements traced to impact evidence per activity.
- Dependency mapping per prioritized activity.
- Resource requirement records; BIA refresh calendar with trigger events.

## Validation

- Sample three prioritized activities and confirm their RTOs trace to impact-over-time evidence, not assertion.
- Confirm dependency maps for the sample include systems, suppliers, and information dependencies.
- Confirm the last BIA refresh occurred within cadence or after a recorded trigger event.

## Failure correction

- **RTO without impact trace** → re-derive the objective from the assessment data; political RTOs are reset to evidence-based values with the change documented.
- **Missing dependency discovered in an exercise or incident** → add it to the BIA, assess its impact, and propagate to the affected continuity strategy.
- **BIA stale past cadence** → refresh immediately and re-validate derived objectives before the next planning cycle uses them.

## Limitations

- BIA quality depends on participant honesty about impact tolerance; optimistic assessments understate urgency.
- Impact-over-time curves are estimates; uncertainty should be recorded rather than collapsed to single values where material.
- The BIA feeds continuity strategy; it does not design it — resource gaps identified remain strategy work.

## Scope note

This article is part of the business leaf. Cross-reference: `BUSINESS_CONTINUITY_MANAGEMENT_SYSTEM.md`, `ISO_22398_2019_EXERCISE_PROGRAMME_GOVERNANCE.md`, and `ITIL_4_SERVICE_CONTINUITY_MANAGEMENT_PRACTICE_GOVERNANCE.md` (operations leaf).

## Canonical sources

- ISO 22317:2019 — Security and resilience — Business continuity management systems — Guidelines for business impact analysis: https://www.iso.org/obp/ui/#iso:std:iso:22317:ed-2
- ISO 22301:2019 — Security and resilience — Business continuity management systems — Requirements: https://www.iso.org/obp/ui/#iso:std:iso:22301:ed-2
- ISO 22398:2019 — Guidelines for conducting exercises: https://www.iso.org/obp/ui/#iso:std:iso:22398:ed-1
- NIST SP 800-34 Rev 1 — Contingency Planning Guide for Federal Information Systems: https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final
- DRI International — Professional Practices for Business Continuity Management: https://drii.org/
