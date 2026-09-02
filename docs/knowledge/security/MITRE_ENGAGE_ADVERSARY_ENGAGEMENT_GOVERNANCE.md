# MITRE Engage Adversary Engagement Governance

## Purpose

Govern the application of MITRE Engage, MITRE's adversary engagement framework (the successor to MITRE Shield), so that active defense planning is deliberate: engagement activities planned against adversary behaviors with defined goals, and the deception/engagement matrix used as a design tool rather than ad-hoc honeypot deployment.

## Scope

Applies to adversary engagement planning for the studio's environments: deception, disruption, and engagement activities. Covers Engage matrix usage, activity planning, and engagement safety. Does not cover detection engineering (ATT&CK governs that) or incident response execution.

## Workflow

1. Start from engagement goals: Engage's top-level goals (Prepare, Expose, Affect, Collect, Understand) frame what an engagement activity is for; activities without goals are noise with legal exposure.
2. Map adversary behaviors from ATT&CK: the adversary TTPs observed or expected in the environment drive which Engage activities apply — engagement targets behaviors, not general curiosity.
3. Design activities per the Engage matrix: the matrix's approaches (e.g., decoys, lures, defensive deception) with their constituent activities selected against the mapped behaviors.
4. Bound the engagement deliberately: scope (systems, networks), duration, escalation triggers, and abort conditions defined before deployment; unbounded deception infrastructure becomes unmonitored attack surface.
5. Plan the operational safety review: legal, privacy, and operational approvals for engagement activities — deception touching user data or third-party systems carries obligations beyond security.
6. Instrument for collection: every engagement activity produces observable telemetry feeding detection; an unobserved decoy is a liability without benefit.
7. Feed results into the defense loop: engagement outcomes (exposed behaviors, collected intelligence) update the ATT&CK-based detection coverage and threat model.

## Controls and evidence

- Engagement goal statements per activity or campaign.
- ATT&CK behavior-to-Engage activity mapping.
- Engagement boundary documentation: scope, duration, escalation, abort.
- Safety review approvals (legal/privacy/operational).
- Telemetry configuration per engagement activity.
- Outcome records feeding detection updates.

## Validation

- Confirm each deployed engagement activity has a stated goal and mapped adversary behavior.
- Confirm telemetry from engagement activities reaches detection tooling.
- Confirm the safety review record exists for each activity class.

## Failure correction

- **Ungoaled engagement deployed** → pause the activity, document the goal or retire it; goal-less deception accumulates risk without direction.
- **Decoy without monitoring** → instrument immediately or remove; unmonitored decoys are the classic engagement own-goal.
- **Engagement outcome not feeding detection** → transfer the intelligence to the detection engineering workflow with a ticket.

## Limitations

- Engage is a planning framework, not a product; implementation uses tooling chosen separately.
- Adversary engagement carries legal and ethical boundaries that vary by jurisdiction; the safety review is not optional process overhead.
- Effectiveness attribution is hard: adversary behavior changes have many causes; treat engagement outcomes as intelligence, not proof.

## Scope note

This article is part of the security leaf. Cross-reference: `MITRE_ATTCK_DETECTION_AND_ENGINEERING_GOVERNANCE.md`, `ENISA_THREAT_LANDSCAPE_ANNUAL_ASSESSMENT_GOVERNANCE.md`, and `ITIL_4_MONITORING_AND_EVENT_MANAGEMENT_PRACTICE_GOVERNANCE.md` (operations leaf).

## Canonical sources

- MITRE Engage — Adversary Engagement Framework: https://engage.mitre.org/
- MITRE Engage — Matrix: https://engage.mitre.org/matrix/
- MITRE ATT&CK — Enterprise Matrix: https://attack.mitre.org/matrices/enterprise/
- MITRE Shield (archived predecessor): https://shield.mitre.org/
- NIST SP 800-160 Vol 3 — Systems Security Engineering: https://csrc.nist.gov/pubs/sp/800/160/vol-3/final
