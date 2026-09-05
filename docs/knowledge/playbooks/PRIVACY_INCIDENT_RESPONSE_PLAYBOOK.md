# Privacy Incident Response Playbook

## Purpose

Triage, contain, and remediate a privacy incident involving PII handled by any system or reference architecture described in `orchords-docs`. Aligns with ISO/IEC 27701 § A.7.4.6 (data subject rights) and Article 33 of GDPR (notification of a personal data breach to the supervisory authority) and Article 34 (communication to data subjects).

## Audience

Privacy officer, security incident commander, on-call SRE, legal/compliance contact.

## Pre-conditions

1. ISO/IEC 27701 governance card is current: `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md`.
2. The privacy officer and legal/compliance contact are reachable on the incident channel within 30 minutes during business hours and within 4 hours off-hours.
3. The DPO (Data Protection Officer) is designated and reachable.
4. Inventory of PII-bearing systems is current (per ISO/IEC 27701 § B.8.3.1).
5. Templates for supervisory-authority notification and data-subject notification are pre-drafted and stored in the incident channel pinned messages.

## Procedure

### 1. Detect

A privacy incident is detected through one of:

- Customer report (email, support ticket, web form).
- Internal detection (anomalous data export, intrusion detection, audit-log alarm).
- Vendor notification (subprocessor breach notification ≤ 24 hours per ISO/IEC 27701 § B.8.2.5).
- Third-party disclosure (researcher, journalist).

Open an incident ticket within 30 minutes of detection. Assign an incident commander.

### 2. Classify

Classify the incident along four axes (the matrix determines the response timeline):

| Axis | Possible values |
|---|---|
| Data classes affected | identity, contact, financial, health, behavioral, biometric, location, communications |
| Volume | ≤ 100 / 100–10 000 / 10 000–1 M / > 1 M |
| Recipient scope | internal only / single customer / many customers / public |
| Reversibility | fully reversible / partially reversible / irreversible |

If any axis is "irreversible" OR volume > 1 M OR recipient scope is "public", the incident is escalated to **major** and triggers Articles 33/34 of GDPR within 72 hours.

### 3. Contain

Immediate containment actions (within 4 hours of classification):

1. Revoke any access credentials or API tokens that the suspected attacker held.
2. Quarantine affected systems (network ACL, IAM deny-all).
3. Preserve volatile evidence (memory dump, network connection state, audit log snapshot) before any rebuild.
4. If the breach is in a third-party processor, invoke the DPA breach clause within 4 hours.

### 4. Eradicate

Within 24 hours, identify and remove the attacker's foothold. Document:

- Initial access vector
- Persistence mechanism
- Lateral movement paths
- Data exfiltration paths

### 5. Notify

Notification timeline per GDPR Article 33:

| Recipient | Deadline | Channel |
|---|---|---|
| Supervisory authority (lead) | ≤ 72 hours from detection | online breach-notification form |
| Supervisory authority (other affected member states) | ≤ 72 hours from detection | parallel submission |
| Affected data subjects | "without undue delay" if Article 34 conditions met (high risk to rights) | direct email + public notice |
| Subprocessors and processors in the chain | ≤ 24 hours from classification | per DPA breach clause |

The notification contains:

1. Nature of the breach (categories and approximate number of data subjects, categories and approximate number of records).
2. Name and contact details of the DPO or other contact point.
3. Likely consequences of the breach.
4. Measures taken or proposed to address the breach and mitigate adverse effects.

### 6. Document

Within 5 business days, complete the incident dossier:

1. Detection source and timeline.
2. Containment and eradication actions with timestamps.
3. Notification list with send timestamps.
4. Data-subject-rights handling (if any DSRs are received because of the breach).
5. Root-cause analysis.
6. Remediation actions and owners.

Store the dossier in the privacy incident register. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` for severity "major" or higher.

### 7. Post-incident review

Convene a review meeting within 10 business days. Output:

- Updated threat model for the affected system.
- Updated ISO/IEC 27701 inventory entries.
- New or updated reference architecture card.
- Follow-up remediation tickets with owners and due dates.

## Rollback

The playbook does not roll back; a privacy incident is irreversible in the sense that the data subject's data was exposed. The mitigation is forward-looking: stronger containment, faster notification, more conservative design.

## References

- `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- GDPR Article 33: `https://gdpr-info.eu/art-33-gdpr/`
- GDPR Article 34: `https://gdpr-info.eu/art-34-gdpr/`
- ENISA incident response guide: `https://www.enisa.europa.eu/topics/incident-reporting`
