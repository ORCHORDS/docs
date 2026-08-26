# security-incident-response-plan

**Issue:** Defining and operating a security incident response plan (IRP) that satisfies regulatory requirements and produces consistent outcomes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ISO 27001 A.5.24–5.26, SOC 2 CC7.3–7.5, GDPR Art. 33, DORA Art. 17, and NIS2 Art. 23 all require a documented and tested incident response capability. Without a plan, teams improvise under pressure — leading to evidence destruction, missed notification deadlines, and uncoordinated customer communication.

## Pattern / Solution
**Incident lifecycle — six phases:**

```
1. Preparation   → 2. Detection & Analysis   → 3. Containment
        ↑                                              ↓
6. Lessons Learned ← 5. Recovery ← 4. Eradication
```

**Phase 1 — Preparation (pre-incident):**
- Maintain an up-to-date asset inventory and data flow map.
- Define severity levels and response SLAs:

| Severity | Criteria | Initial response | Customer comms |
|---|---|---|---|
| P1 Critical | Data breach / service down / active intrusion | 15 minutes | Within 1 hour |
| P2 High | Significant service degradation / potential breach | 30 minutes | Within 4 hours |
| P3 Medium | Limited impact; no confirmed breach | 4 hours | Status page if visible |
| P4 Low | Near miss / minor anomaly | Next business day | None |

- Pre-authorise the incident commander role to make decisions without committee approval.
- Maintain a war room template (Slack channel name convention, Zoom bridge, shared doc).

**Phase 2 — Detection & Analysis:**
```python
# Incident intake (Slack bot or form)
incident = {
    "id": "INC-2026-042",
    "detected_at": "2026-08-11T14:23:00Z",
    "detected_by": "SIEM alert / customer report / internal discovery",
    "initial_description": "...",
    "severity": "P1",
    "incident_commander": "@security-lead",
    "war_room": "#inc-2026-042"
}
```

**Phase 3 — Containment:**
- Short-term: isolate affected systems (revoke credentials, block IPs, disable accounts).
- Long-term: stable alternative while root cause is fixed.
- Preserve evidence **before** remediation: snapshot disk images, export logs, capture network traffic.

**Phase 4 — Eradication:**
- Remove attacker persistence (backdoors, modified files, rogue admin accounts).
- Patch or mitigate the root cause vulnerability.
- Run a full vulnerability scan after eradication.

**Phase 5 — Recovery:**
- Restore from clean backup or rebuild from IaC.
- Verify system integrity before returning to production.
- Increase monitoring for 30 days post-incident.

**Phase 6 — Post-Incident Review (within 5 business days):**
```
Timeline reconstruction
Root cause (5 Whys)
What went well
What failed
Action items with owners and deadlines
Regulatory notifications completed / outstanding
```

**Regulatory notification checklist:**
- [ ] GDPR SA: 72-hour deadline from awareness
- [ ] GDPR individuals: If high risk, without undue delay
- [ ] DORA (financial entities): Within 4 hours for P1 / major incident
- [ ] NIS2: Within 24 hours (early warning), 72 hours (formal), 1 month (final)
- [ ] Customers per DPA/contract terms

## Gotchas
- The incident commander must have authority to take system-offline decisions without a committee vote — speed matters more than consensus during active intrusion.
- Do not remediate before preserving evidence — courts and regulators may require forensic artifacts.
- Internal Slack/email during the incident may be discoverable; advise team to communicate factually.
- Table-top exercises are required by many frameworks; schedule one annually and after significant architecture changes.
- "Incident" and "breach" are not synonymous — not every incident involves personal data; triage early to separate tracks.

## Related
- `gdpr-breach-notification-72h.md`
- `business-continuity-plan.md`
- `disaster-recovery-rto-rpo.md`
- `audit-log-mandatory.md`
- `dora-incident-response-best-practices-2026.md`
