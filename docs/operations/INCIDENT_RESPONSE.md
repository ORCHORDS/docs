---
title: "Incident Response Plan"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "mike.johnson (DevOps Lead) — operations; maya.rodriguez (Backend Lead) — security"
status: "approved"
iso-refs: ["ISO/IEC 27001:2022 Annex A.5.24-26", "ISO/IEC 27035-1:2016", "NIST SP 800-61r2"]
---

# Incident Response Plan

**Project:** Beetle Studio
**Owner:** Mike Johnson (DevOps Lead) — operations lead; Maya Rodriguez (Backend Lead) — security lead
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO), Amanda Clark (Operations Manager — for HR / legal escalation)
**ISO Standards:** ISO/IEC 27001:2022 Annex A.5.24 (Information security incident management planning), A.5.25 (Assessment of security events), A.5.26 (Response to incidents), ISO/IEC 27035-1:2016 (Principles and process), NIST SP 800-61r2 (Computer Security Incident Handling Guide)
**Version:** 1.0.0
**Last Updated:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | How the Beetle Studio team responds to a confirmed or suspected security incident affecting the desktop application, the cloud backend, or the development / release pipeline |
| **Diátaxis form** | Process / runbook |
| **Primary audience** | Mike Johnson, Maya Rodriguez, Kirk Beka, Mooned Dev |
| **Secondary audience** | On-call engineers; PR / marketing for external comms |

---

## Purpose

Establish a single playbook for incident response. The intent is to minimize mean-time-to-detect (MTTD), mean-time-to-respond (MTTR), and the blast radius of any single incident, and to comply with ISO/IEC 27001:2022 Annex A.5.24.

The plan is deliberately short. Detail lives in the linked runbooks.

## Definitions

| Term | Definition |
|---|---|
| **Event** | Any observable occurrence in a system or network. May be benign or suspicious. |
| **Alert** | An event that has been triaged by automated tooling and raised a notification. |
| **Incident** | An alert (or set of alerts) that has been confirmed to be a real security or availability issue requiring response. |
| **Severity** | The impact of the incident (Sev1 = critical, Sev2 = major, Sev3 = minor). Drives the response cadence. |
| **Incident Commander (IC)** | The single person who owns the response; not necessarily the technical lead. |
| **Comms Lead** | The person who owns external communications (status page, social media, customer-facing). |

## Severity Tiers

| Severity | Definition | Example | Response time |
|---|---|---|---|
| **Sev1** | Production outage, active exploitation, data exfiltration, code-signing cert compromise | Auto-update channel is serving a malicious package | 15 minutes |
| **Sev2** | Significant degradation; partial outage; suspected but unconfirmed compromise | License-check endpoint returning 500s for 10% of requests | 1 hour |
| **Sev3** | Minor impact; single-user issue; or a confirmed low-severity security finding | Single user reports crash on import; one-off CVE in a low-impact dep | 4 hours |
| **Sev4** | Informational; no immediate impact | Anomalous login attempt that was rate-limited | Next business day |

## Roles and On-Call

| Role | Primary | Backup | Notes |
|---|---|---|---|
| Incident Commander | Mike Johnson (DevOps) | Kirk Beka (CTO) | Owns the response, not the fix |
| Security Lead | Maya Rodriguez (Backend) | Kirk Beka (CTO) | Owns triage, threat assessment, evidence |
| Engineering Lead | (rotating per asset) | (domain lead) | Owns the fix |
| Comms Lead | Jason Wong (Marketing) | Mooned Dev (CEO) | Owns external comms |
| HR / Legal | Amanda Clark (Operations) | — | Owns HR / legal escalation if insider or regulator involved |

> **On-call:** the team does not currently run a 24/7 on-call rotation. Sev1 / Sev2 incidents during off-hours are escalated to the IC's mobile phone via the alert routing. Sev3 / Sev4 are handled next business day.

## Incident Phases (NIST SP 800-61r2 model)

### 1. Preparation

- Maintain this plan, the threat model, and the contact list.
- Quarterly tabletop exercise (a calendar reminder; see [`OPERATIONS/INFRASTRUCTURE_OVERVIEW.md`](../operations/INFRASTRUCTURE_OVERVIEW.md) for the cadence).
- Annual disaster recovery drill (failover to backup Azure region; see [`engineering/BACKUP_DISASTER_RECOVERY.md`](../engineering/BACKUP_DISASTER_RECOVERY.md)).

### 2. Detection and Analysis

| Source | What it tells us |
|---|---|
| Azure Monitor alerts | Backend service health, error rate spikes |
| Firebase Crashlytics | New crashes from a release |
| Gitleaks / Semgrep CI | A new secret or vulnerability in a PR |
| User reports (security@, support) | End-user-observed incidents |
| Threat intel feeds | CVE announcements for deps |

The first responder (often whoever is paged) confirms the alert is a real incident and assigns a severity. If severity is **Sev1 or Sev2**, declare the incident (see step 3).

### 3. Containment, Eradication, and Recovery

The IC calls a **war room** in the project chat. War room members:

- IC (chair)
- Security Lead
- Engineering Lead for the affected asset
- Comms Lead (for Sev1 / Sev2)

The war room uses the standard runbook for the affected asset:

| Asset | Runbook |
|---|---|
| Cloud endpoint (Firebase / Azure) | See [`operations/INFRASTRUCTURE_OVERVIEW.md`](../operations/INFRASTRUCTURE_OVERVIEW.md) §"Incident Playbooks" |
| Auto-update channel | See [`engineering/CI_CD_PIPELINE.md`](../engineering/CI_CD_PIPELINE.md) §"Rollback Procedure" |
| Code-signing cert | See [`releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md`](../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md) §"Compromise Response" |
| Source code in repo | Branch protection + git reflog recovery; see [`engineering/BACKUP_DISASTER_RECOVERY.md`](../engineering/BACKUP_DISASTER_RECOVERY.md) |
| Cloud database (Firestore) | Restore from backup; see [`engineering/BACKUP_DISASTER_RECOVERY.md`](../engineering/BACKUP_DISASTER_RECOVERY.md) |

The war room tracks decisions in a shared incident document (template at the end of this file). The IC ensures that all actions are timestamped.

### 4. Post-Incident Activity

- **Within 48 hours:** a draft post-mortem is circulated to war-room members.
- **Within 7 days:** the post-mortem is published internally; an exec-summary is shared with the leadership.
- **Within 30 days:** action items are scheduled in the backlog.

The post-mortem template:

```markdown
# Incident Post-Mortem: <short title>

**Date:** YYYY-MM-DD
**Severity:** SevN
**Duration:** <first alert → resolution>
**IC:** <name>
**Affected assets:** <list>
**Customer impact:** <description>

## Summary
<2-3 sentences>

## Timeline (UTC, ISO 8601)
- 2026-MM-DDTHH:MM:SSZ — <event>
- ...

## Root cause
<1-2 paragraphs>

## What went well
- ...

## What went poorly
- ...

## Action items
- [ ] <action> — <owner> — <due date>
- ...

## Lessons learned
<distilled insights, fed into THREAT_MODEL.md>
```

## Communication Templates

### Internal (war room declaration)

```
INCIDENT DECLARED — SevN — <one-line description>
IC: <name>
War room: <chat channel link>
Affected: <asset list>
Latest status: <one-line>
```

### External (status page)

```
[Investigating] <one-line description>. We are aware of the issue and are
investigating. Updates every 15 minutes.
```

```
[Identified] <root cause, in plain English>. We are working on a fix.
Estimated time to resolution: <ETA>.
```

```
[Resolved] <one-line summary>. The fix has been deployed. A full post-mortem
will be published at <URL> within 7 days.
```

> **Plain English:** do not use internal jargon in customer-facing comms. Have a non-engineer (Jason Wong / Mooned Dev) read the message before posting.

## Evidence Handling

Per ISO/IEC 27002:2022 A.5.28:

- **Logs, screenshots, and artefacts** are preserved in the incident document, not in personal files.
- **Chain of custody** is recorded if law enforcement or external counsel may be involved.
- **Retention:** incident documents are kept for 3 years (1 year for Sev3 / Sev4, 3 years for Sev1 / Sev2).

## Insurance and Legal

- **Cyber insurance:** TBD — not yet procured. Amanda Clark (Operations) is the point of contact.
- **Legal counsel:** TBD. Amanda Clark maintains the engagement letter.
- **Regulator notification:** if a Sev1 incident involves personal data, the legal team (via Amanda Clark) decides whether GDPR / CCPA / state-level breach-notification laws apply. Decision must be made within 72 hours of the incident declaration per GDPR Art. 33.

## Tabletop Exercise Cadence

| Exercise | Frequency | Owner | Last run |
|---|---|---|---|
| Cloud endpoint compromise | Annual | Maya Rodriguez | TBD |
| Code-signing cert compromise | Annual | Sarah Miller + Maya Rodriguez | TBD |
| Source repo compromise | Annual | Kirk Beka + Mike Johnson | TBD |
| Dependency CVE (critical) | Annual | Mike Johnson | TBD |

## References

### Internal Documents

- [Security Policy](../SECURITY_POLICY.md)
- [Security Waivers](../security/WAIVERS.md)
- [Threat Model](../security/THREAT_MODEL.md)
- [Vulnerability Disclosure](../security/VULNERABILITY_DISCLOSURE.md)
- [Infrastructure Overview](../operations/INFRASTRUCTURE_OVERVIEW.md)
- [Backup and Disaster Recovery](../engineering/BACKUP_DISASTER_RECOVERY.md)
- [CI/CD Pipeline](../engineering/CI_CD_PIPELINE.md)
- [Code Signing Certificate Management](../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md)

### External

- ISO/IEC 27001:2022 Annex A.5.24 — Information security incident management planning
- ISO/IEC 27001:2022 Annex A.5.25 — Assessment of security events
- ISO/IEC 27001:2022 Annex A.5.26 — Response to incidents
- ISO/IEC 27035-1:2016 — Information security incident management — Principles and process
- NIST SP 800-61r2 — Computer Security Incident Handling Guide — https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r2.pdf
- SANS Incident Handler's Handbook — https://www.sans.org/white-papers/33901/
- GDPR Art. 33 (Breach notification) — https://gdpr-info.eu/art-33-gdpr/

---

*Grounded in: ISO/IEC 27001:2022 Annex A.5.24-26, ISO/IEC 27035-1:2016, NIST SP 800-61r2. Reviewed by Kirk Beka (CTO) and Mooned Dev (CEO) on 2026-06-21.*
