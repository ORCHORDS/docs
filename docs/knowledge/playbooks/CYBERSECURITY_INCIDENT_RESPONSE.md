# Cybersecurity Incident Response Playbook

## Trigger

Use this playbook when malicious or unauthorized cybersecurity activity is confirmed or reasonably suspected and coordinated response is required.

## Scope

Apply the process to affected systems, services, identities, data, suppliers, and business processes within the incident boundary. Expand or reduce the boundary as evidence changes.

## Inputs

- detection or report that triggered the response;
- available logs, alerts, telemetry, and asset context;
- current incident contacts and escalation criteria;
- recovery priorities and dependency information.

## Steps

1. **Declare and assign ownership.** Record the incident, appoint a response lead, establish severity, and activate required technical and business roles.
2. **Preserve evidence.** Protect relevant logs, volatile evidence, timestamps, and records before destructive remediation where practicable.
3. **Scope the incident.** Determine affected identities, systems, data, entry points, persistence, lateral movement, and business impact.
4. **Contain.** Select containment actions that reduce harm while considering evidence preservation and service consequences.
5. **Eradicate and remediate.** Remove malicious access or persistence, correct exploited weaknesses, rotate affected credentials, and verify that remediation addresses the identified cause.
6. **Recover.** Restore services in a controlled order, validate integrity, increase monitoring, and confirm that recovery criteria are met.
7. **Communicate.** Coordinate required internal, customer, supplier, regulator, insurer, or authority communications through authorized owners.
8. **Close and learn.** Document evidence, decisions, timeline, root causes, residual risks, and corrective actions; track lessons to completion.

## Escalation

Escalate immediately when the incident may involve significant safety, legal, privacy, financial, availability, or cross-organizational impact, or when the response team cannot establish or contain the scope.

## Completion criteria

Close only when containment and recovery objectives are met, monitoring shows no known active compromise within scope, required notifications are addressed, evidence is retained according to policy, and follow-up actions have accountable owners.

## Sources

- NIST — SP 800-61 Rev. 3, Incident Response Recommendations and Considerations for Cybersecurity Risk Management: https://csrc.nist.gov/pubs/sp/800/61/r3/final
- CISA — Cybersecurity Incident and Vulnerability Response Playbooks: https://www.cisa.gov/topics/cybersecurity-best-practices/executive-order-improving-nations-cybersecurity

## Scope note

This is a project-neutral operational playbook. Legal, reporting, sector, and jurisdiction-specific obligations require separate assessment.
