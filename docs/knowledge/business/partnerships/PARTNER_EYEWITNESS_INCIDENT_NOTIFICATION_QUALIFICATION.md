# Partner Eyewitness Incident Notification Qualification

## Scope

This article governs the discipline by which an organization qualifies a partner-reported incident before deciding whether to escalate, notify customers, regulators, or other partners. "Eyewitness" is used here in a deliberate, narrow sense: the partner is reporting an incident that it has directly observed or that has been observed within its own scope of responsibility. The qualification step is the gate between the partner's report and this organization's response, and it is what protects the organization from acting on hearsay, from over-responding to rumours, and from under-responding to material events.

The article draws on the data-classification discipline of IETF RFC 5070 — Incident Object Description Exchange Format (IODEF) — which establishes a structured vocabulary for describing computer-security incidents. IODEF does not bind an organization to a particular notification path, but its categories for incident class, severity, confidence, impact, time, and source are useful for qualifying a partner report. A partner notification that arrives with a clear class, a defined confidence, a stated impact, and an attributable source can be processed at a different speed than one that does not.

The scope is the qualification step and the criteria for that step. The article does not replace the partner's own incident-response process, does not address the technical exchange format for incident data, and does not govern the organization's broader incident-response program.

## Workflow or implementation guidance

1. Receive the partner notification through the agreed channel. The agreed channel is the only channel that triggers the qualification process; notifications arriving through other channels are treated as informal until they are repeated through the agreed channel.
2. Capture the notification as received. Record the time of receipt, the reporting party, the report's content (in the partner's own words where possible), the supporting evidence offered, and any prior context (related incident, ongoing activity, prior notification on the same issue).
3. Classify the report by IODEF-style attributes where they apply. Useful attributes include: event class (where the partner's vocabulary may differ, map it to the receiving organization's vocabulary rather than translating by analogy), confidence (asserted, observed, suspected), impact scope (data categories, subjects affected, systems affected, jurisdictions in scope), time of observation, source attribution, and current status (ongoing, contained, resolved).
4. Apply the qualification criteria. A qualified report is one where (a) the reporting party is attributable, (b) the report describes what was observed rather than what was inferred, (c) the impact scope can be characterized at least to the level needed for the next decision, (d) the report can be cross-checked against available evidence on this side, and (e) the report identifies a contact for follow-up.
5. Distinguish between eyewitness observation and hearsay. Eyewitness means the partner saw, or directly gathered from its own systems, the relevant fact. Hearsay means the partner is repeating a report from a third party. The two require different treatment; the response time should reflect the source.
6. Distinguish between qualified certainty and suspicion. A confirmed compromise with stolen credentials is a different qualification from a partner suspecting unusual activity. The qualification should preserve this distinction rather than collapsing it into a single severity score.
7. Cross-check the report against this organization's own evidence where possible. Logs, threat-intelligence feeds, internal incident records, and customer reports can corroborate or contradict the partner's account. Cross-checking is not delay for its own sake; it is the discipline of not acting on a single source.
8. Decide on the next action based on the qualification. The decision set includes: acknowledge and stand by, escalate internally, open a joint investigation, notify customers or regulators where the qualification warrants, request additional evidence from the partner, or close the report as not material to this organization. The decision should be recorded with the basis for it.
9. Re-qualify as new evidence arrives. A report that was "suspected" yesterday may be "confirmed" today. The register should track the qualification over time, not just the initial classification.
10. Treat the qualification as the basis for the audit trail. The qualification record is what the auditor, regulator, or court will look at when the question is "how did you decide to respond?"

## Controls

The qualification discipline relies on controls that protect it from being bypassed. An attribution control ensures that the reporting party is identified. A vocabulary control ensures that the partner's class names are mapped to the receiving organization's vocabulary with the mapping recorded. A confidence control ensures that uncertainty is preserved in the record. A cross-check control ensures that single-source reports are not treated as confirmed. A timing control ensures that the qualification is performed within an SLA tied to the severity tier. An audit control ensures that the qualification record is retained.

## Validation evidence

Validation evidence includes the captured notification, the IODEF-style classification, the qualification decision and its basis, the cross-check evidence, the cross-source corroboration, the escalation or closure record, any follow-up evidence from the partner, and the qualification-over-time updates. Evidence should be sufficient for an independent reviewer to reconstruct, for any specific report, what was known, when, and how it was qualified.

## Failure modes and correction

Common failure modes include acting on the partner's report without qualification, treating hearsay as eyewitness, collapsing multiple severity levels into a single score, losing the distinction between suspected and confirmed, allowing a single-source report to drive a customer notification without cross-check, and recording the qualification only after the response has already begun. Another failure is the qualification being biased by the partner's seniority or commercial importance rather than by the evidence.

Correction requires re-qualifying the affected report, recording the corrected qualification, and where the prior qualification led to action, reviewing whether the action was warranted and whether it should be unwound or amended. Repeated qualification failures indicate that the discipline has been bypassed and should be escalated to the incident-response governance function.

## Limitations

This article covers the qualification step. It does not address the technical exchange format for incident data (other than the limited use of IODEF-style categories), the broader incident-response process, or the customer or regulator notification rules of any specific jurisdiction. RFC 5070 defines a data format, not a notification policy; this article uses the format's vocabulary but does not bind the organization to its full schema.

## Canonical sources

- IETF — RFC 5070, Incident Object Description Exchange Format (IODEF): https://datatracker.ietf.org/doc/html/rfc5070
- NIST SP 800-61 Rev. 2 — Computer Security Incident Handling Guide (incident-handling context for partner notifications): https://csrc.nist.gov/pubs/sp/800/61/r2/upd1/final
