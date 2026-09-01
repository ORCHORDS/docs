# Support Agent Shift Handover Running Sheet

## Scope

This article governs how the support desk produces and consumes a running sheet during an agent shift handover. The running sheet is the operational document that captures the state of the support desk at the moment of handover: open high-severity cases, queues that are approaching breach, agents who are out of office, escalations in progress, and any incident that requires the incoming shift's attention. The scope covers every shift boundary, including the daily handover, the weekend handover, and the holiday handover.

The discipline follows the service operation practice in ITIL 4, where the shift handover is a structured activity that preserves continuity of service. The running sheet is one of the artefacts that makes the handover auditable; the others are the shift log and the briefing call.

## Workflow or implementation guidance

The running sheet is produced in the final hour of the outgoing shift. The sheet is a structured document with a defined template. The template has placeholders for: open high-severity cases (severity, customer, current state, expected next action), queues approaching breach (queue, current latency, SLA window, mitigation in progress), agents out of office (name, expected return, current case load), escalations in progress (escalation identifier, owner, expected resolution), and any incident requiring attention (incident identifier, current state, expected next update).

The outgoing shift lead populates the running sheet from the operational dashboards. The lead does not invent content; the sheet is a faithful record of the state at the moment of handover. The lead attaches a timestamp to each entry so the incoming shift can confirm the freshness of the data. The lead signs the sheet with their identifier.

The incoming shift lead reviews the running sheet at the start of their shift. The review is not a passive read; it is an active confirmation. The incoming lead asks clarifying questions on each entry, confirms the operational state matches the sheet, and identifies any entry that is stale or unclear. The incoming lead signs the sheet with their identifier and the timestamp of the review.

The running sheet is retained for a defined window. The window is set by the records-of-processing policy: typically the shift duration plus an audit grace period. After the window, the sheet is purged from the operational store. The sheet is exportable to the audit function on request, because the handover is a defined service operation activity.

## Controls

Three controls protect the running sheet. The first is the template enforcement: a sheet that lacks a required field is rejected at the handover tool. The second is the dual-signature requirement: the sheet is valid only when both leads have signed it. The third is the freshness check: the incoming lead confirms that the operational state matches the sheet before signing.

A separate control protects against the unauthorised disclosure. The running sheet carries operational detail that could be sensitive (queue contents, escalations, incidents). The sheet is stored in the operational tool with a separate access role list from the public case store. The sheet is not exportable through the customer-facing export path.

## Validation evidence

Validation evidence is collected continuously. The handover log records the outgoing lead, the incoming lead, the timestamp of the sheet, the timestamp of the review, and the disposition. A periodic tabletop exercise tests the handover under simulated pressure: an incident is in progress, the shift change happens, and the incoming lead is observed to take over the incident correctly. A periodic audit compares the operational state at the moment of handover against the sheet, confirming that the sheet was faithful.

## Failure modes and correction

The most common failure is the sheet being produced hastily at the end of the shift, with stale data. The outgoing lead does not refresh the dashboards before populating the sheet. The correction is the freshness check and the dual-signature requirement.

The second most common failure is the sheet being read passively. The incoming lead reads the sheet, signs it, and discovers an hour later that one of the entries was stale. The correction is the active review and the clarifying question step.

The third most common failure is the sheet carrying more detail than is needed for the handover. The sheet becomes a journal of the outgoing shift, and the incoming lead cannot find the operational priorities. The correction is the template enforcement and the periodic audit of sheet length.

## Limitations

The running sheet discipline assumes that the operational dashboards are accurate and current. Where the dashboards are inaccurate, the sheet inherits the inaccuracy. The organisation should confirm that its dashboards are the source of truth before it commits to the discipline.

The discipline also assumes that the handover includes a synchronous component. Where the handover is purely asynchronous (for example, in a fully remote team across time zones), the running sheet carries more weight and the clarification loop must be tighter. The discipline should be applied with awareness of the team's distribution.

## Canonical sources

- AXELOS, ITIL 4 Service Operation Practices (publisher and title only; AXELOS publications are referenced via https://www.axelos.com/resource-hub/case-studies/itil-4-foundation).
- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- W3C, Technical Report publication conventions, https://www.w3.org/TR/