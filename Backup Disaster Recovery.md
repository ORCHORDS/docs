> Auto-generated from `docs/engineering/BACKUP_DISASTER_RECOVERY.md` in the docs repo.

---
title: "Backup & Disaster Recovery"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Backup & Disaster Recovery

**Project:** Beetle Studio  
**Owner:** Mike Johnson (DevOps Lead)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)  
**ISO Standards:** ISO/IEC 27001:2022 (Annex A: Business Continuity, Operational Security), ISO/IEC 12207:2017 (transition, operations)  
**Version:** 1.0.0  
**Last Updated:** 2026-06-21

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | RTO/RPO targets, backup strategy, and disaster recovery playbooks |
| **Diátaxis form** | Reference |
| **Primary audience** | Mike Johnson, Kirk Beka, Mooned Dev, Amanda Clark |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines Beetle Studio's backup strategy and disaster recovery procedures. Per **ISO/IEC 27001:2022 Annex A**, the organization must have business continuity controls that protect information assets and enable rapid recovery from disruptions.
## Contents

- [Recovery Objectives](#recovery-objectives)
- [Backup Strategy](#backup-strategy)
  - [User Data (Firebase / Cloud)](#user-data-firebase-cloud)
  - [Source Code](#source-code)
  - [Infrastructure Configuration](#infrastructure-configuration)
- [Backup Verification](#backup-verification)
- [Disaster Scenarios & Recovery Procedures](#disaster-scenarios-recovery-procedures)
  - [Scenario 1: Firebase Outage](#scenario-1-firebase-outage)
  - [Scenario 2: GitHub Repository Unavailable](#scenario-2-github-repository-unavailable)
  - [Scenario 3: Build Agent / CI Failure](#scenario-3-build-agent-ci-failure)
  - [Scenario 4: Azure Infrastructure Failure](#scenario-4-azure-infrastructure-failure)
  - [Scenario 5: Data Corruption (Firestore or Storage)](#scenario-5-data-corruption-firestore-or-storage)
  - [Scenario 6: Credential / Key Compromise](#scenario-6-credential-key-compromise)
- [Business Continuity Contacts](#business-continuity-contacts)
- [Post-Incident Review](#post-incident-review)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Recovery Objectives

| Objective | Target | Defined By |
|---|---|---|
| **RTO — Recovery Time Objective** | 4 hours for critical services | Mooned Dev + Kirk Beka |
| **RPO — Recovery Point Objective** | 1 hour for user data | Mooned Dev + Kirk Beka |
| **Recovery Scope** | Core app deployment + cloud services | Kirk Beka |

---

## Backup Strategy

### User Data (Firebase / Cloud)

| Data | Backup Method | Frequency | Retention | Owner |
|---|---|---|---|---|
| Firestore user data | Firebase automatic replication | Continuous | Managed by Firebase | Google Cloud SLA |
| Firebase Auth | Firebase automatic replication | Continuous | Managed by Firebase | Google Cloud SLA |
| Firebase Storage (assets) | Firebase automatic replication | Continuous | Managed by Firebase | Google Cloud SLA |
| Beetle Studio source code | GitHub repo mirroring | On every push | Permanent | Mike Johnson |

Firebase provides built-in replication across availability zones. No additional backup needed for Firestore. However, we maintain a manual monthly export of Firestore data to Azure Blob Storage as a secondary backup.

### Source Code

| Data | Backup Method | Frequency | Retention |
|---|---|---|---|
| GitHub repository | GitHub geo-replication + Azure Blob Storage | On every push | Permanent |
| Forgejo Actions artifacts (workflow run artifacts) | Azure Blob Storage | After every release build | 90 days |
| Build outputs | Azure Blob Storage | After every release | 2 years |

### Infrastructure Configuration

| Data | Backup Method | Frequency | Retention |
|---|---|---|---|
| Infrastructure as Code (Terraform) | GitHub + Azure Blob Storage | On every change | Permanent |
| CI/CD pipeline configs | GitHub | On every change | Permanent |
| Azure Key Vault keys | Azure Key Vault geo-replication | Automatic | Permanent |
| SSL certificates | Azure App Service + Let's Encrypt auto-renew | Automatic | 90 days |

---

## Backup Verification

Per **ISO/IEC 27001:2022**, backups must be tested regularly.

| Backup Type | Verification Frequency | Method | Owner |
|---|---|---|---|
| Firestore export | Monthly | Restore to test project and verify data | Mike Johnson |
| GitHub mirroring | Weekly | Automated integrity check | Mike Johnson |
| Infrastructure IaC | On every PR | Terraform validate + plan | Mike Johnson |
| Release artifacts | Every release | Smoke test on restored artifacts | Sarah Miller |

---

## Disaster Scenarios & Recovery Procedures

### Scenario 1: Firebase Outage

**Impact:** Users cannot authenticate or sync projects.

**Detection:** Azure Monitor alert + Mike Johnson notification.

**Recovery Procedure:**
1. Confirm Firebase status at `status.firebase.google.com`
2. If outage confirmed, notify team in #engineering Slack channel
3. Enable **offline mode** in Beetle Studio (users can continue working locally)
4. Monitor for Firebase recovery
5. Once Firebase is restored, users resume normal cloud sync
6. Post-incident report within 48 hours

**Duration:** **RTO 4h / RPO 1h** as a conservative interim target (pending Firebase Blaze SLA response, expected to land within the next billing cycle). These numbers are picked to align with the worst-case scenario from the *Firestore point-in-time recovery* window (7 days) and assume a regional outage (not a global Google Cloud one). Mike will tighten these once the SLA response is in; if Firebase commits to 99.95%+, RTO can drop to 2h without extra spend.

### Scenario 2: GitHub Repository Unavailable

**Impact:** Developers cannot push/pull code; CI stops.

**Recovery Procedure:**
1. Confirm GitHub status at `githubstatus.com`
2. If GitHub down, activate Azure Blob Storage backup:
   ```bash
   # Clone from Azure Blob Storage backup
   git clone https://azure_storage.blob.core.windows.net/backups/beetle-studio.git
   ```
3. Developers work from local clones
4. Resume normal operations once GitHub is restored
5. Reconcile any offline work via standard Git workflow

### Scenario 3: Build Agent / CI Failure

**Impact:** No release builds possible.

**Recovery Procedure:**
1. Identify failing Forgejo Actions runner (logs in the Actions UI)
2. Restart runner: `cd actions-runner && ./run.sh --reset`
3. If runner is corrupted, provision new runner:
   ```bash
   # Register new runner
   ./config.sh --url https://dev.mooned.dev/beetle-studio/beetle-studio --token <token>
   ./run.sh
   ```
4. Re-trigger failed workflow runs
5. Investigate root cause; update monitoring

### Scenario 4: Azure Infrastructure Failure

**Impact:** Backend services, hosting, or storage unavailable.

**Recovery Procedure:**
1. Check Azure status at `status.azure.com`
2. Activate Azure geo-redundancy — fail over to secondary region:
   ```bash
   # Fail over storage account
   az storage account failover --name beetlesa --resource-group beetle-studio-rg
   ```
3. Update DNS if App Service fails over
4. Verify all endpoints respond in secondary region
5. Notify users of degraded service

### Scenario 5: Data Corruption (Firestore or Storage)

**Impact:** User data is corrupted; cloud sync is unreliable.

**Detection:** Automated integrity checks or user reports.

**Recovery Procedure:**
1. Identify affected user IDs and scope of corruption
2. Restore from last known good backup:
   ```bash
   # Restore Firestore from monthly export
   firestore-cli restore gs://beetle-backup/export_YYYYMMDD
   ```
3. Notify affected users
4. Validate restored data
5. Post-incident report with root cause analysis

### Scenario 6: Credential / Key Compromise

**Impact:** Signing certificate, API keys, or tokens leaked.

**Detection:** Security scan, GitHub secret scanning, or external report.

**Recovery Procedure:**
1. Immediately revoke all potentially compromised credentials
2. Rotate all affected credentials:
   ```bash
   # Rotate Azure credentials
   az ad credential reset --id <app-id>
   # Revoke GitHub OIDC tokens
   gh api /admin/orgs/mooned-dev/actions/oidc-custom-template -X DELETE
   ```
3. Regenerate new signing certificates if compromised
4. Re-sign all release artifacts if signing keys were compromised
5. File incident report (ISO/IEC 27001 requires documented incident management)
6. Notify Microsoft Store team if Store credentials were affected

---

## Business Continuity Contacts

| Role | Name | Contact |
|---|---|---|
| Primary incident commander | Kirk Beka | |
| Secondary incident commander | Mike Johnson | |
| Infrastructure backup | Sarah Miller | |
| Executive escalation | Mooned Dev | |
| Firebase support | Google Cloud Console | |
| Azure support | Azure Portal / CSAM | |

---

## Post-Incident Review

After every significant incident, a post-incident review (PIR) is required within 5 business days. PIR must include:

- Incident timeline
- Root cause analysis
- Impact assessment (users affected, downtime duration)
- Actions taken to resolve
- Preventive actions to avoid recurrence
- Owner and deadline for each preventive action

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial plan — aligned with ISO/IEC 27001:2022 Annex A and ISO/IEC 12207:2017 |

---

*Grounded in: ISO/IEC 27001:2022 Annex A (Business Continuity, Operational Security), ISO/IEC 12207:2017 §6.4 (Transition)*



---

## References

### Internal Documents

_No internal documents referenced._

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Mike Johnson | Initial version |
| 1.0.1 | June 2026 | Mike Johnson | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Mike Johnson (DevOps Lead)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type