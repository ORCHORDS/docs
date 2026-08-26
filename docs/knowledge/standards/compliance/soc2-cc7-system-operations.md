# soc2-cc7-system-operations

**Issue:** SOC 2 CC7 system operations monitoring and incident response requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CC7 requires organizations to detect and respond to threats to availability, security, and processing integrity through monitoring, vulnerability management, and documented incident response.

## Pattern / Solution
CC7.1 — Vulnerability management:
- Monthly vulnerability scans on all systems in scope
- Critical vulnerabilities remediated within 30 days, high within 90 days
- Track remediation in a risk register or ticketing system
- Annual penetration test by qualified third party

CC7.2 — Monitoring for anomalies:
- SIEM aggregating logs from: servers, network devices, applications, authentication systems
- Alerts defined for: failed logins (>5 in 10 min), privilege escalation, data exfiltration patterns
- Alerts reviewed daily; on-call rotation documented

CC7.3 — Evaluation of security events:
- Triage all alerts within 4 hours during business hours
- P1 (critical) incidents: 1-hour response time, executive notification within 2 hours

CC7.4 — Incident response:
- Written incident response plan (IRP) reviewed annually
- Post-incident review (PIR) completed within 5 business days for P1/P2 incidents
- Evidence: PIR reports, incident tickets, alert history

CC7.5 — Recovery:
- Recovery time objective (RTO) and recovery point objective (RPO) defined per system
- Disaster recovery test annually with documented results

## Gotchas
- Auditors ask for evidence of alert review — logging without review is not sufficient
- All incidents must be logged even if determined to be false positives
- Monitoring gaps (e.g., unmonitored dev systems that touch production data) are findings
- Change log and incident log must be reconcilable — unexplained changes become incidents

## Related
- `soc2-cc6-logical-access-controls.md`
- `soc2-cc8-change-management.md`
- `security-incident-response-plan.md`
