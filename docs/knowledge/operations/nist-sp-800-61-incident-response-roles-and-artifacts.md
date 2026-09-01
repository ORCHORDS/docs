# NIST SP 800-61 Incident Response Roles and Artifacts

## Purpose

NIST SP 800-61 (initially the Computer Security Incident Handling Guide, with the current publication re-titled to align with the NIST Cybersecurity Framework 2.0 community profile) organizes incident response into preparation, detection and analysis, containment, eradication and recovery, and post-incident activity. This article summarizes the persistent, reusable artifact model and role structure that operations teams use to coordinate incident response in alignment with federal guidance. It is not a substitute for organizational incident response plans.

## Incident lifecycle

NIST's primary improvement over open-ended response playbooks is the explicit lifecycle, which assumes that response activity is iterative rather than linear:

- **Preparation** — baseline training, documentation, tool acquisition, communication plans, and exercises performed during steady-state operations.
- **Detection and analysis** — recognizing that an event has occurred and gathering enough information to classify and prioritize it.
- **Containment, eradication, and recovery** — actions taken to limit impact, eliminate adversary presence, and restore service.
- **Post-incident activity** — review and learning that updates detection, response, and preparation based on what was observed.

The boundaries between phases are not rigid. Containment and eradication often occur in parallel, eradication may need to wait for analysis, and post-incident activity may begin before recovery is complete.

## Roles

NIST deliberately separates the technical handling of the incident from the decision-making about the incident. The persistent roles most operations teams adopt are:

- **Incident commander** — owns the overall response, decisions about scope, and decisions about when to escalate, defer, or close.
- **Technical lead** — owns the investigative and remediation activities; coordinates with engineering and platform teams.
- **Communications lead** — owns internal and external messaging, including status pages, customer-facing communications, and regulatory notifications.
- **Scribe or timeline owner** — owns the time-stamped record of events, decisions, and actions.
- **Security advisor or legal liaison** — advises on legal, regulatory, and contractual considerations; supports breach-notification decisions.

These roles may be combined on small teams, but they should still be identifiable in every active incident. The separation of technical work from incident command is what makes the response survivable under stress.

## Standard artifacts

Four reusable artifacts are central to an incident lifecycle regardless of the supporting tooling:

- **Incident record** — minimum fields include identifier, opening time, severity, system or service affected, current status, commander, and link to the active timeline.
- **Timeline** — time-ordered log of events and decisions, including system events, manual observations, hypothesis changes, and noteworthy comms.
- **Evidence store** — captures such as logs, memory dumps, configurations, and screenshots, tagged with provenance and chain-of-custody notes where chain-of-custody is required.
- **Post-incident report** — recorded shortly after closure; covers summary, timeline highlights, contributing factors, what went well and poorly, and follow-up actions.

These artifacts are also the input to the post-incident activity phase, so the artifacts must be available to the review team.

## Workflow

1. Open an incident record with severity, commander, scope note, and an initial technical hypothesis.
2. Start the timeline immediately. The first entry records the trigger event and any prior similar events.
3. Designate the technical lead and at least one analyst. Do not split the technical lead role.
4. Establish the communications channel and cadence. State which stakeholders will be told what, and at what cadence.
5. Perform investigation in parallel with containment when the latter will not destroy evidence the former needs.
6. Document decisions as they happen, including the rationale and alternatives considered.
7. When the incident closes the incident, mark the record closed, archive the evidence store, and schedule the post-incident review.
8. Conduct the review and write the post-incident report; assign follow-up actions and owners.

In multi-party environments, federated teams can keep their own internal artifacts provided they update the central incident record promptly. Disagreement about scope or cause is normal; the record must capture the reason for the choice made.

## Validation evidence

Effective evidence includes opening and closing timestamps with severity, an audit trail of commander transitions, the timeline with author timestamps, evidence-store contents with metadata, communications transcripts or summaries, and the post-incident report with corrective actions. Quality evidence shows decisions being made deliberately, technical work being separated from command, and follow-up actions being tracked to completion.

## Failure modes

Failure modes include the commander being drawn into technical work and losing command of the overall response, evidence being destroyed by over-hasty containment, communications being improvised at the moment of greatest stress, post-incident reports being written without assigned owners and therefore never completed, and the same root causes recurring across incidents because follow-up actions were not tracked.

## Canonical sources

- NIST SP 800-61 Rev. 3, Incident Response Recommendations and Considerations for Cybersecurity Risk Management — A CSF 2.0 Community Profile: https://csrc.nist.gov/pubs/sp/800/61/r3/final
- NIST Cybersecurity Framework (CSF) 2.0 — Govern / Identify / Protect / Detect / Respond / Recover core: https://www.nist.gov/cyberframework
- NIST SP 800-53 Rev. 5, Security and Privacy Controls — incident response family (IR): https://csrc.nist.gov/pubs/sp/800/53/r5/final

## Scope note

This article summarizes roles and artifacts for incident response alignment with NIST guidance; it is not a legal breach-notification analysis and does not cover regulator-specific notification requirements.
