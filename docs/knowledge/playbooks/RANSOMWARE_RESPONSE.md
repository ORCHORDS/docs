# Ransomware Response Playbook

## Trigger

Use when ransomware, destructive extortion activity, or credible evidence of ransomware deployment is detected or strongly suspected.

## Inputs

- affected-system and identity information;
- security telemetry and available forensic evidence;
- incident-response contacts;
- backup and recovery status;
- legal, communications, insurance, and authority contacts where applicable.

## Steps

1. **Activate incident response.** Assign leadership, record the event, preserve evidence, and establish a secure coordination channel.
2. **Contain spread.** Isolate affected systems and accounts using actions proportionate to the observed propagation risk. Avoid destroying evidence unnecessarily.
3. **Protect recovery assets.** Verify that backups, snapshots, recovery credentials, and management systems are separated from the compromised environment and have not been altered.
4. **Scope the intrusion.** Determine initial access, affected identities and hosts, persistence, exfiltration indicators, lateral movement, and the likely time window of compromise.
5. **Eradicate access.** Remove malicious persistence, close exploited weaknesses, rotate affected credentials, and rebuild systems when integrity cannot be established confidently.
6. **Validate backups before restoration.** Confirm selected recovery data predates or is otherwise free from known compromise and verify integrity before reconnecting restored systems.
7. **Restore in priority order.** Bring back critical services gradually with heightened monitoring and controlled network access.
8. **Coordinate reporting and communications.** Follow applicable legal, regulatory, contractual, law-enforcement, insurer, customer, and stakeholder requirements through authorized owners.
9. **Review and improve.** Document root causes, control gaps, decisions, recovery performance, and actions needed to reduce recurrence and impact.

## Payment decisions

Do not treat payment as a technical recovery control. Any extortion-payment decision requires separate legal, sanctions, risk, executive, and law-enforcement considerations as applicable; payment does not guarantee recovery or deletion of stolen data.

## Completion criteria

The response is complete when active compromise is contained, trusted service is restored, required notifications and evidence handling are addressed, and remediation actions are assigned and tracked.

## Sources

- CISA — StopRansomware Guide: https://www.cisa.gov/stopransomware/ransomware-guide
- NIST — SP 800-61 Rev. 3, Incident Response Recommendations and Considerations for Cybersecurity Risk Management: https://csrc.nist.gov/pubs/sp/800/61/r3/final

## Scope note

This playbook is general cybersecurity guidance. Ransomware events may create jurisdiction-specific legal, sanctions, privacy, notification, and law-enforcement obligations.
