# ISO/IEC 27035-1:2023 Incident Detection and Response Governance

## Purpose

ISO/IEC 27035-1:2023, "Information technology — Information security incident management — Part 1: Principles and process," updates the incident management standard with refreshed guidance on the principles and process for managing information security incidents. The standard defines the incident management policy, the incident management process (plan and prepare, detect and report, assess and decide, respond, learn), and the relationships to other security processes. This article governs the application of ISO/IEC 27035-1 so an organization's incident management operates with the principles and process the standard requires.

## Scope

The standard applies to any organization that wants to manage information security incidents consistently. Within this knowledge base, the article covers the principles (incident management is a process, an information security incident is a planned-for event, incident response is a team activity, incidents are learning opportunities), the five-stage process, and the documentation of incident management. It does not cover the substantive technical response to specific incident types (ransomware, phishing, etc.); readers should consult other resources for those.

## Workflow

1. Establish the incident management policy and scope. Align with the organization's information security policy.
2. Plan and prepare: define incident categories, roles, responsibilities, contact lists, escalation paths, tools, and the incident response plan.
3. Detect and report: implement detection (SIEM, alerting, anomaly detection) and reporting (security operations, end-user reporting). All reports are triaged.
4. Assess and decide: for each reported event, assess whether it is an incident, determine its scope and impact, and decide on the response.
5. Respond: contain, eradicate, and recover from the incident. Document each action with timestamps and decisions.
6. Learn: conduct a post-incident review (lessons learned) within a defined window. Identify root causes, gaps in controls, and improvements. Apply the improvements.
7. Maintain the incident management plan: review and update after each major incident and on a planned cadence.

## Controls and evidence

Incident management evidence includes the policy, the incident management plan, the incident reports, the response records, the post-incident review minutes, and the improvement records. Each incident should be traceable from the initial report through the response to the lessons learned.

## Validation

Validation should confirm the policy and plan are current, incidents are detected and triaged within defined windows, response actions are documented, post-incident reviews produce improvements, and the plan is updated after major incidents. Periodic exercises confirm the process operates as expected.

## Failure correction

Common failure modes: incidents are detected but not triaged (correct: enforce triage for every report); response actions are taken without documentation (correct: document each action with timestamps and rationale); post-incident reviews are skipped or shallow (correct: require a documented review for each significant incident within a defined window); lessons learned are not applied (correct: track improvement actions to closure); the incident management plan is not tested (correct: schedule exercises covering major incident types).

## Limitations

ISO/IEC 27035-1 provides principles and process; it does not prescribe specific detection tools or response techniques. The standard does not guarantee incident outcomes; it ensures incident management is consistent and learning-oriented. Sector regulations may impose specific incident reporting obligations (NIS2, GDPR Article 33, sector-specific regulators).

## Scope note

This article summarizes project-neutral operations use of ISO/IEC 27035-1:2023. It does not assert any specific organization's incident management conformance or claim any certification outcome.

## Canonical sources

- ISO/IEC 27035-1:2023 — Information technology — Information security incident management — Part 1: Principles and process: https://www.iso.org/standard/78973.html
- ISO/IEC 27035-2:2023 — Information security incident management — Part 2: Guidelines to plan and prepare for incident response: https://www.iso.org/standard/78974.html