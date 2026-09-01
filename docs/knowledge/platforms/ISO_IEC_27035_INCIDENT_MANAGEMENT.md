# ISO/IEC 27035 Incident Management

## Purpose

ISO/IEC 27035 (multipart, most recently Part 1:2023 and Part 3:2023) provides the authoritative guidance for information security incident management. It replaces the original single-part 27035 with a three-part series that separates concepts and planning (Part 1), guidelines for incident response (Part 2), and guidelines for digital evidence acquisition and handling (Part 3). It is the baseline most commonly invoked when organizations need a vendor-neutral incident-management discipline.

## Scope

The standard covers the full incident lifecycle: principles, policy, preparation, detection, triage, response, recovery, lessons learned, and digital evidence handling. It does not replace regulator-mandated breach-notification timelines, sectoral incident-response regulations, or formal forensic procedures under criminal-law rules.

## Plan structure

ISO/IEC 27035-2 recommends structuring the incident response plan around six phases:

1. **Preparation**: people, process, and tooling readiness before incidents occur.
2. **Detection and reporting**: signals from monitoring and from external reports that an incident may be occurring.
3. **Assessment and decision**: triage, severity assignment, scope, and the response strategy.
4. **Response**: containment, eradication, and recovery actions.
5. **Lessons learned**: post-incident review and program improvement.
6. **Information sharing and coordination**: with internal stakeholders, regulators, partners, and (where appropriate) the wider community.

A common defect is to skip the first and last phases in practice. The standard makes those phases load-bearing.

## Roles

The publication recommends named roles with documented responsibilities:

- **Incident owner**: accountable for the overall response.
- **Incident coordinator**: coordinates people, communication, and tooling.
- **Triage lead**: assigns severity and initial scope.
- **Technical lead**: drives containment, eradication, and recovery.
- **Communications lead**: coordinates internal, customer, regulator, and public messaging.
- **Legal and privacy lead**: oversees legal obligations, including notification timelines and evidentiary requirements.
- **Digital evidence lead**: oversees collection, preservation, and chain of custody.

A single person can hold more than one role, but the responsibilities must be assigned, not implied.

## Severity model

The publication recommends a documented severity scale with thresholds and authority for each level. The scale should be tied to:

- impact on confidentiality, integrity, and availability of information;
- number of affected individuals or systems;
- regulatory implications; and
- reputational and contractual impact.

Severity should be reassessed as the incident evolves; over- and under-severity are both defects.

## Digital evidence

Part 3 addresses acquisition and handling of digital evidence. The key principles are:

- minimize handling of original evidence;
- document the chain of custody;
- preserve evidence integrity (for example, with cryptographic hashing);
- preserve metadata; and
- ensure forensic soundness so that evidence is admissible in appropriate forums.

The customer and the provider should agree on a forensic model — for example, who collects, who preserves, who has access, and how evidence is exchanged — before an incident requires it.

## Engineering workflow

1. Document the incident-management plan, named roles, and the severity scale.
2. Inventory the systems, data flows, and contractual notification obligations that drive severity decisions.
3. Build the detection surface: telemetry, alerts, threat-intel feeds, and external-report intake.
4. Rehearse incident scenarios in tabletop and live-fire exercises, with named role-players.
5. Capture lessons learned for every real incident and every exercise, and feed actions into the plan.
6. Re-review the plan at least annually and after every significant incident or contract change.

## Controls and evidence

- The incident-management plan with named roles and authority levels.
- Detection-to-alert mapping with on-call rotations and runbooks.
- Exercise records with attendees, scenarios, and outcomes.
- Incident records with timeline, severity, decisions, and lessons learned.
- Chain-of-custody records for any digital evidence collected.

## Validation

- A second reviewer confirms the plan is current and the roster is staffed.
- Detection coverage is verified against an authoritative asset inventory.
- At least one exercise per quarter exercises a different phase of the plan.
- Lessons-learned actions have owners and completion dates.

## Failure modes and corrections

- Skipping the preparation phase — correct by staffing on-call, rehearsing, and pre-staging tooling before the first incident.
- Mixing triage severity with response severity — correct by separating "what is happening?" from "what do we do about it?".
- Letting one role do all roles — correct by separating at least incident owner, technical lead, and communications lead.
- Treating digital evidence as an afterthought — correct by planning chain of custody and forensic procedures during preparation, not during the incident.
- Closing the incident without a lessons-learned review — correct by treating the review as a gating step before closure.

## Limitations

- The publication does not specify regulator-mandated timelines; organizations must layer those on top.
- It does not prescribe tooling; tools must be chosen to fit the plan, not the reverse.
- It does not replace law-enforcement-led investigations under criminal-law procedure.
- Part 3 addresses digital evidence but does not override admissibility rules in any specific forum.

## Canonical sources

- ISO/IEC 27035-1:2023 (ISO, primary authority) — Information security incident management — Part 1: Principles and process: https://www.iso.org/standard/78973.html
- ISO/IEC 27035-2:2023 (ISO, primary authority) — Information security incident management — Part 2: Guidelines to plan and prepare for incident response: https://www.iso.org/standard/78974.html

## Scope note

This article summarizes project-neutral incident-management guidance from ISO/IEC 27035. It does not claim that any specific organization has implemented or certified to the standard.