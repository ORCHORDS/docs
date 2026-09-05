---
title: "Data Loss Prevention Response Playbook"
owner: "Data Protection Officer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Data Loss Prevention Response Playbook

## Trigger

Use this playbook when a data loss prevention (DLP) system detects, blocks, or alerts on the unauthorized transfer, storage, or exposure of sensitive data, or when a confirmed or suspected data exfiltration event requires coordinated containment and notification.

## Scope

Apply the process to data in motion (email, web upload, APIs, file transfer), data at rest (file shares, databases, object stores, endpoints), and data in use (endpoint copy/paste, clipboard, printing, screen capture), across all jurisdictions and data classifications covered by the organization's data inventory.

## Inputs

- DLP alert, rule match, and event context;
- affected user, system, channel, and destination;
- data classification and content category;
- legal and regulatory obligations for the affected data;
- asset and identity inventories.

## Steps

1. **Triage and classify the alert.** Confirm the alert reflects actual sensitive data exposure; classify severity by data category (PII, PHI, PCI, secrets, intellectual property), record count, destination, and user risk profile.
2. **Preserve evidence.** Snapshot the affected artifact, log records, system state, network metadata, and timestamps before any containment action that could alter the evidence.
3. **Contain the channel.** Block the transmission, quarantine the message, isolate the endpoint, revoke active sessions, suspend the account, or remove the destination document, selecting the minimum action that prevents continued exposure.
4. **Scope the exposure.** Determine what data was exposed, to whom, for how long, and whether exposure was authorized; identify all recipients and downstream systems.
5. **Notify stakeholders.** Engage Legal, Compliance, Privacy, Security, Customer Success, and Executive leadership per the documented escalation matrix; preserve privileged communications where counsel directs.
6. **Assess regulatory obligations.** Evaluate breach notification thresholds under applicable regimes (GDPR Art. 33/34, HIPAA Breach Notification Rule, GLBA, state breach notification laws, sectoral rules); record the analysis with the responsible legal owner.
7. **Contain and remediate.** Apply compensating controls: revoke credentials, rotate secrets, patch exploited weaknesses, tighten DLP rules, and update access permissions.
8. **Communicate externally as required.** Issue regulator notifications within statutory windows, customer notifications with required content, and supplier or partner notifications where downstream exposure is possible.
9. **Recover and restore.** Restore affected systems from trusted backups; validate data integrity; confirm that legitimate access is restored only after policy controls are re-applied.
10. **Close and learn.** Document root cause, decisions, timeline, regulatory analysis, and corrective actions; update DLP rules, training, and data handling procedures.

## Escalation

Escalate to the DPO, Legal, and Executive leadership when:
- exposure affects regulated data above statutory thresholds;
- exposure involves more than a defined record count or specific data category;
- the alert indicates insider threat or systemic control failure;
- a vendor or partner is involved in the exfiltration path.

## Evidence

- DLP alert and rule identifiers;
- preserved artifacts, logs, and timestamps;
- triage and classification notes;
- legal analysis and notification decisions;
- containment, remediation, and recovery actions.

## Completion Criteria

The response is considered complete when:
- exposure is contained and data is no longer at risk through the identified path;
- legal and regulatory obligations are assessed and notifications issued where required;
- affected credentials, secrets, and access are reset or revoked;
- corrective actions are documented and tracked to closure.

## Exceptions

Document deviations with the approver, scope, expiration, compensating controls, and review schedule. Maintain an exception register accessible to audit.

## Related Documents

- [NIST SP 800-53 Rev. 5 Access Control Family](../reference/NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
- [ISO 27701 Privacy Information Management](../reference/ISO_27701_PRIVACY_INFORMATION_MANAGEMENT.md)
- [GDPR Article 33 Breach Notification](../reference/GDPR_ARTICLE_33_BREACH_NOTIFICATION.md)
- [Data Classification Review](../reference/DATA_CLASSIFICATION_REVIEW.md)
- [Sensitive Data Discovery Review](../reference/SENSITIVE_DATA_DISCOVERY_REVIEW.md)
