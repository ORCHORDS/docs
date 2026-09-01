# MITRE ATT&CK Detection and Engineering Governance

## Purpose

MITRE ATT&CK is a globally accessible, curated knowledge base of adversary tactics and techniques based on real-world observations, maintained by the MITRE Corporation. ATT&CK organizes adversary behavior into tactics (the *why* of an action), techniques (the *how*), procedures (specific implementations), mitigations, detections, and, in the enterprise matrix, groups and software that have been observed using each technique. ATT&CK is the canonical primary authority for adversary-informed defense used by security operations, threat intelligence, and engineering teams across governments and industry.

This article describes a governance pattern for adopting ATT&CK as the backbone of detection engineering, threat intelligence, red-team and purple-team exercises, and adversary-emulation planning. It does not assert that any specific organization has implemented an ATT&CK-aligned program, and it does not replace the MITRE-published ATT&CK content.

## Scope

ATT&CK is currently organized into several matrices, including Enterprise (covering Windows, macOS, Linux, Cloud (AWS, GCP, Azure, Office 365, Azure AD, Google Workspace, Container), Network, and Containers), Mobile (Android and iOS), and ICS (Industrial Control Systems). A program should document:

- which matrix or matrices the organization operates against;
- which platforms are in scope (for example, Windows enterprise endpoints and a specific cloud provider);
- the relationship between ATT&CK and adjacent MITRE resources (MITRE D3FEND for defensive techniques, MITRE ENGAGE for adversary engagement, MITRE Caldera for automation, MITRE Shield for active defense); and
- the relationship between ATT&CK content and the organization's own detection and response capabilities.

The publication is descriptive, not prescriptive; it does not by itself tell an organization which techniques to prioritize.

## Workflow

A reusable ATT&CK-aligned program runs as a cycle.

1. **Scope the program.** Identify the assets and platforms in scope and the matrix or matrices that will be used.
2. **Build the coverage map.** Map current detections, mitigations, and response playbooks to ATT&CK techniques. Maintain the map in a tool that can be updated as content evolves.
3. **Prioritize.** Use threat intelligence and asset criticality to prioritize techniques. A technique that the adversary population of interest uses frequently against the assets in scope should be a higher priority than a technique that is theoretical.
4. **Detect, mitigate, and respond.** For each priority technique, ensure that there is at least one detection source, one mitigation, and one response procedure. Where coverage is weak, plan and execute improvements.
5. **Emulate.** Use ATT&CK content in adversary-emulation exercises (for example, MITRE ATT&CK Evaluations, the Center for Threat-Informed Defense's adversary-emulation plans, or organization-internal red-team plans) to test the coverage map.
6. **Measure.** Track coverage, time-to-detect, time-to-respond, and the gap between observed and tested coverage.
7. **Update on ATT&CK releases.** Subscribe to MITRE's release notes for ATT&CK and update the coverage map and playbooks accordingly.
8. **Reassess.** Periodically reassess priorities and the coverage map in light of new threat intelligence, infrastructure changes, and adversary activity observed in the organization's environment.

## Controls and evidence

An ATT&CK-aligned program produces a structured coverage record. A program should retain the following evidence.

| Element | Typical content | Typical evidence |
|---|---|---|
| Scope | Matrices, platforms, asset classes | Program charter |
| Coverage map | Techniques mapped to detection, mitigation, response | Coverage database, ATT&CK Navigator layer |
| Prioritization | Priority techniques and rationale | Threat intelligence reports, prioritization worksheet |
| Detection sources | Telemetry sources, detection rules, expected artifacts | Detection catalog, SIEM rules, EDR policies |
| Mitigations | Controls in design or operation that reduce exposure | Mitigations catalog, control inventory |
| Response procedures | Runbooks, escalation paths, containment actions | Playbooks, incident reports |
| Emulation plans | Adversary emulation scenarios, expected outcomes | Emulation reports, exercise logs |
| Measurement | KPIs, trends, gaps | Metrics dashboard, review reports |

A program should retain at minimum: the most recent coverage map; the prioritization worksheet; the detection, mitigation, and response items for priority techniques; the latest emulation report; and the schedule for the next reassessment.

## Validation

Validation confirms that the ATT&CK coverage map reflects actual capability. Useful activities include:

- choosing a priority technique, reviewing the detection, mitigation, and response records, and confirming they correspond to deployed capabilities;
- running an adversary emulation against a contained environment and observing whether the priority techniques are actually detected and responded to;
- reviewing telemetry sources for the artifacts the coverage map relies on, and confirming they are collected and retained;
- reviewing the mapping process for consistency across techniques; and
- reviewing ATT&CK release notes for new or deprecated techniques and confirming the map has been updated.

Validation must distinguish covered, partially covered, and unable-to-assess states. A technique marked as detected should not be marked as such only because a rule exists; it should reflect evidence that the rule would fire (or would be expected to fire) under realistic adversary behavior.

## Failure correction

When an ATT&CK-aligned control fails, follow a documented path.

1. Confirm the failure with reproducible evidence.
2. Identify the gap: is it detection, mitigation, response, telemetry, or mapping?
3. Apply the corrective change through the change management process.
4. Verify with new evidence rather than a closed ticket.
5. Update the coverage map, playbooks, and prioritization if the failure is systemic.

Common failure modes include:

- treating ATT&CK as a presentation tool rather than as an engineering artifact;
- mapping techniques to rules without verifying that the rules actually use the relevant telemetry;
- focusing on the most popular techniques in the community without considering the threats actually relevant to the organization;
- failing to update the coverage map when ATT&CK content changes;
- using ATT&CK content in isolation, without a threat-intelligence-driven prioritization; and
- confusing detection rules with detections. A rule that exists but never fires is not a detection.

## Limitations

ATT&CK content reflects observations rather than theoretical completeness. Techniques that have not been observed, that are still emerging, or that are used by less-visible adversary populations may be underrepresented. Programs should pair ATT&CK with internal threat intelligence and with their own telemetry-based discovery of attacker behavior.

The publication also does not specify a particular operational metric or target coverage level. Programs should set their own coverage targets in light of their risk tolerance, their operational capacity, and the threat picture.

## Canonical sources

- MITRE ATT&CK — official knowledge base landing page: https://attack.mitre.org/
- MITRE ATT&CK Enterprise Matrix: https://attack.mitre.org/matrices/enterprise/
- MITRE ATT&CK Design and Philosophy Paper — *Putting the Science in Cyber Threat-Informed Defense*, K. Barnum et al., 2023 (methodology and intended use of ATT&CK): https://www.mitre.org/sites/default/files/2023-11/03_1630-cyber-threat-informed-defense-science.pdf

## Scope note

This article summarizes reusable governance practices derived from MITRE ATT&CK. It is not a substitute for the MITRE-published content, does not assert conformity with any compliance regime, and does not constitute professional advice on the security of any specific environment.
