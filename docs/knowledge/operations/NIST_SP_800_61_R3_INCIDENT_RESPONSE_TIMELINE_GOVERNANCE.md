# NIST SP 800-61 r3 Incident Response Timeline Governance

## Purpose

NIST SP 800-61 r3, "Incident Response Recommendations and Considerations for Cybersecurity Risk Management," updates the previous r2 guidance on incident response with a more flexible, risk-management-aligned approach. The publication organizes guidance around the cyber risk management lifecycle (govern, identify, protect, detect, respond, recover) and provides detailed guidance on incident response preparation, detection, analysis, containment, eradication, and recovery. This article governs the application of the SP 800-61 r3 incident response timeline (the sequence of incident response activities) so the response is executed with the discipline the publication requires.

## Scope

The publication applies to any organization that responds to cybersecurity incidents. Within this knowledge base, the article covers the incident response timeline (preparation; detection; containment, eradication, and recovery; post-incident activity), the relationship between incident response and the broader cybersecurity risk management lifecycle, and the documentation of the response. It does not cover sector-specific incident reporting obligations; readers should overlay their sector requirements.

## Workflow

1. Preparation: build the incident response capability before an incident occurs. Develop the plan, train the team, acquire the tools, and exercise the procedures.
2. Detection: identify suspected cybersecurity events through automated monitoring, user reports, external notifications, and threat intelligence.
3. Analysis: for each detected event, assess whether it is an incident, determine its scope, classify its severity, and document the analysis. Correlate with other events and threat intelligence.
4. Containment: limit the impact of the incident. Short-term containment (isolation, network segmentation) prevents immediate spread; long-term containment (temporary fixes that allow the system to continue running) buys time for full eradication.
5. Eradication: remove the attacker's artifacts, patch the exploited vulnerability, and remove the access.
6. Recovery: restore the system to operation, validate the restoration, and monitor for re-emergence.
7. Post-incident activity: conduct a lessons-learned review, update the incident response plan, address root causes, and share findings with stakeholders as appropriate.

## Controls and evidence

Response evidence includes the preparation records, the detection records, the analysis records, the containment actions, the eradication records, the recovery records, and the post-incident review minutes. Each incident should be traceable through the timeline with timestamps, decisions, and rationale.

## Validation

Validation should confirm preparation is in place (plan, team, tools, exercises), detection operates, analysis is performed promptly, containment and eradication follow the analysis, recovery is validated, and post-incident reviews produce improvements. Periodic exercises confirm the timeline operates as expected.

## Failure correction

Common failure modes: preparation is insufficient (correct: conduct exercises and update the plan); analysis is shallow (correct: require a documented analysis for each significant event); containment is delayed (correct: pre-authorize containment actions for known scenarios); recovery is rushed (correct: validate recovery before returning the system to operation); post-incident reviews are skipped (correct: require a documented review for each significant incident within a defined window).

## Limitations

NIST SP 800-61 r3 provides guidance; it does not prescribe specific tools or response techniques for each incident type. The publication does not guarantee incident outcomes; it ensures the response is systematic and learning-oriented. The publication does not replace sector regulations that mandate specific incident reporting timelines.

## Scope note

This article summarizes project-neutral operations use of NIST SP 800-61 r3. It does not assert any specific organization's incident response conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-61 r3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management: https://csrc.nist.gov/publications/detail/sp/800-61/rev-3/final
- NIST CSF 2.0 — Cybersecurity Framework: https://csrc.nist.gov/publications/detail/sp/800-61/rev-3/final (r3 was published alongside CSF 2.0)