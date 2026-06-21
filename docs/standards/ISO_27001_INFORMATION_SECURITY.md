---
title: "ISO/IEC 27001:2022 — Information Security Management System"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "security"
status: "approved"
iso-refs: ["ISO/IEC 27001:2022", "ISO/IEC 27002:2022"]
---

# ISO/IEC 27001:2022 — Information Security Management System (ISMS)

## Purpose

This document defines the information security controls applicable to Beetle Studio's development, operations, and release processes, based on ISO/IEC 27001:2022 Annex A (93 controls across 4 themes).

## Scope

Applies to:
- Source code repositories and CI/CD pipelines
- Build artifacts and release signing
- Developer workstations and remote access
- Cloud services and infrastructure
- Third-party dependencies and supply chain
- User data handling (telemetry, crash reports, licensing)

---

## Annex A Control Themes Overview

ISO/IEC 27001:2022 restructured controls from 14 domains (2013) into 4 themes with 93 total controls:

| Theme | Controls | Range | Owner |
|-------|----------|-------|-------|
| Organizational | 37 | A.5.1 – A.5.37 | Management / Compliance |
| People | 8 | A.6.1 – A.6.8 | HR / Team Leads |
| Physical | 14 | A.7.1 – A.7.14 | Operations / Facilities |
| Technological | 34 | A.8.1 – A.8.34 | Engineering / DevOps |

---

## A.5 — Organizational Controls (37 controls)

| # | Control | Beetle Studio Application |
|---|---------|--------------------------|
| 5.1 | Policies for information security | Security policy published in docs/SECURITY_POLICY.md |
| 5.2 | Information security roles and responsibilities | Defined in BEETLE_STUDIO_TEAM.md — maya.rodriguez leads security |
| 5.3 | Segregation of duties | Code review required before merge; separate build/release roles |
| 5.4 | Management responsibilities | CTO (kirk.beka) accountable for ISMS |
| 5.5 | Contact with authorities | Incident response contacts documented |
| 5.6 | Contact with special interest groups | Community channels, security mailing lists |
| 5.7 | Threat intelligence | Security scan workflow monitors CVEs; Dependabot-equivalent |
| 5.8 | Information security in project management | Security review gate in PR build pipeline |
| 5.9 | Inventory of information and associated assets | Source repos, build servers, signing keys inventoried |
| 5.10 | Acceptable use of information and associated assets | Developer access policy |
| 5.11 | Return of assets | Offboarding checklist: revoke tokens, return hardware |
| 5.12 | Classification of information | Public (docs), Internal (source), Confidential (keys/tokens) |
| 5.13 | Labelling of information | Classification headers in sensitive documents |
| 5.14 | Information transfer | Encrypted channels for sensitive data (TLS, SSH) |
| 5.15 | Access control | Role-based repo access; team token separation |
| 5.16 | Identity management | Individual Forgejo accounts per team member |
| 5.17 | Authentication information | Personal access tokens; no shared credentials |
| 5.18 | Access rights | Minimum privilege: developers can't push to main |
| 5.19 | Information security in supplier relationships | Third-party library vetting (security-scan.yml) |
| 5.20 | Addressing information security within supplier agreements | License compliance for FFmpeg, DirectX SDK |
| 5.21 | Managing information security in the ICT supply chain | SBOM generation, dependency pinning |
| 5.22 | Monitoring, review and change management of supplier services | Dependency update reviews |
| 5.23 | Information security for use of cloud services | Cloud sync (Firebase) security controls |
| 5.24 | Information security incident management planning | Incident response procedure documented |
| 5.25 | Assessment and decision on information security events | Triage criteria for security findings |
| 5.26 | Response to information security incidents | Patch timeline: Critical=24h, High=72h |
| 5.27 | Learning from information security incidents | Post-incident review process |
| 5.28 | Collection of evidence | Audit log retention; forensic readiness |
| 5.29 | Information security during disruption | Business continuity for build infrastructure |
| 5.30 | ICT readiness for business continuity | Backup/restore procedures (BACKUP_DISASTER_RECOVERY.md) |
| 5.31 | Legal, statutory, regulatory and contractual requirements | License compliance, GDPR for EU users |
| 5.32 | Intellectual property rights | Code ownership, contributor agreements |
| 5.33 | Protection of records | Retention policy for logs, builds, releases |
| 5.34 | Privacy and protection of PII | Minimal telemetry; no PII in crash reports |
| 5.35 | Independent review of information security | Annual security audit |
| 5.36 | Compliance with policies, rules and standards | CI enforcement of coding standards |
| 5.37 | Documented operating procedures | Runbooks for deployment, incident response |

---

## A.6 — People Controls (8 controls)

| # | Control | Beetle Studio Application |
|---|---------|--------------------------|
| 6.1 | Screening | Background verification for contributors with repo access |
| 6.2 | Terms and conditions of employment | NDA, IP assignment, security responsibilities |
| 6.3 | Information security awareness, education and training | Security training for all developers (secure coding) |
| 6.4 | Disciplinary process | Violation escalation path defined |
| 6.5 | Responsibilities after termination or change of employment | Token revocation, access removal on departure |
| 6.6 | Confidentiality or non-disclosure agreements | NDA required for access to signing keys |
| 6.7 | Remote working | Encrypted connections, approved devices only |
| 6.8 | Information security event reporting | Report via security@ channel; no blame culture |

---

## A.7 — Physical Controls (14 controls)

| # | Control | Beetle Studio Application |
|---|---------|--------------------------|
| 7.1 | Physical security perimeters | Build server room access controlled |
| 7.2 | Physical entry | Badge access for infrastructure areas |
| 7.3 | Securing offices, rooms and facilities | Locked cabinets for signing hardware (HSM) |
| 7.4 | Physical security monitoring | CCTV on server room (NEW in 2022) |
| 7.5 | Protecting against physical and environmental threats | UPS, fire suppression for build servers |
| 7.6 | Working in secure areas | Clean desk policy in secure areas |
| 7.7 | Clear desk and clear screen | Auto-lock policy on workstations |
| 7.8 | Equipment siting and protection | Servers in climate-controlled environment |
| 7.9 | Security of assets off-premises | Encrypted laptops for remote developers |
| 7.10 | Storage media | Encrypted drives; secure disposal of old media |
| 7.11 | Supporting utilities | Redundant power for CI infrastructure |
| 7.12 | Cabling security | Network cables in protected conduits |
| 7.13 | Equipment maintenance | Scheduled maintenance for build hardware |
| 7.14 | Secure disposal or re-use of equipment | Wipe/destroy drives before disposal |

---

## A.8 — Technological Controls (34 controls)

| # | Control | Beetle Studio Application |
|---|---------|--------------------------|
| 8.1 | User endpoint devices | Developer workstation hardening guide |
| 8.2 | Privileged access rights | Admin tokens limited to CI; developers use personal tokens |
| 8.3 | Information access restriction | Branch protection; main requires PR review |
| 8.4 | Access to source code | Repository-level permissions per role |
| 8.5 | Secure authentication | Token-based auth; SSH keys for git |
| 8.6 | Capacity management | Docker resource limits (14 CPUs, 32GB RAM) |
| 8.7 | Protection against malware | Security scan in CI (security-scan.yml) |
| 8.8 | Management of technical vulnerabilities | CVE monitoring; automated dependency scanning |
| 8.9 | Configuration management | Reproducible builds via CMake; .forgejo/workflows versioned (NEW) |
| 8.10 | Information deletion | PII purge procedures; log rotation (NEW) |
| 8.11 | Data masking | Telemetry anonymization (NEW) |
| 8.12 | Data leakage prevention | Gitleaks in security-scan.yml; no secrets in code (NEW) |
| 8.13 | Information backup | Git mirroring; database backups (BACKUP_DISASTER_RECOVERY.md) |
| 8.14 | Redundancy of information processing facilities | Multi-region considerations for cloud services |
| 8.15 | Logging | Structured logging in all services (ISO 8601 timestamps) |
| 8.16 | Monitoring activities | CI pipeline monitoring; resource alerts (NEW) |
| 8.17 | Clock synchronization | NTP on all build servers; UTC for logs |
| 8.18 | Use of privileged utility programs | Restricted admin tool access |
| 8.19 | Installation of software on operational systems | Approved software list for build agents |
| 8.20 | Networks security | Firewall rules for Forgejo instance |
| 8.21 | Security of network services | TLS for all API endpoints (dev.mooned.dev) |
| 8.22 | Segregation of networks | Build network isolated from public |
| 8.23 | Web filtering | Content filtering on CI runners (NEW) |
| 8.24 | Use of cryptography | Code signing certificates; TLS 1.3 minimum |
| 8.25 | Secure development life cycle | Security gates at PR, build, release stages |
| 8.26 | Application security requirements | OWASP compliance for any web components |
| 8.27 | Secure system architecture and engineering principles | Least privilege; defense in depth |
| 8.28 | Secure coding | Static analysis in CI; banned function list (NEW) |
| 8.29 | Security testing in development and acceptance | Security scan on every PR |
| 8.30 | Outsourced development | Third-party code review requirements |
| 8.31 | Separation of development, test and production environments | Separate branches; staging before release |
| 8.32 | Change management | PR-based workflow; approval required |
| 8.33 | Test information | No production data in test environments |
| 8.34 | Protection of information systems during audit testing | Audit in isolated environment |

---

## 11 New Controls in 2022 Edition

These controls were added in the 2022 revision (did not exist in 2013):

| # | Control | Theme |
|---|---------|-------|
| 5.7 | Threat intelligence | Organizational |
| 5.23 | Information security for use of cloud services | Organizational |
| 5.30 | ICT readiness for business continuity | Organizational |
| 7.4 | Physical security monitoring | Physical |
| 8.9 | Configuration management | Technological |
| 8.10 | Information deletion | Technological |
| 8.11 | Data masking | Technological |
| 8.12 | Data leakage prevention | Technological |
| 8.16 | Monitoring activities | Technological |
| 8.23 | Web filtering | Technological |
| 8.28 | Secure coding | Technological |

---

## Control Attributes (New in 2022)

Each control now has 5 attributes for filtering and classification:

| Attribute | Values |
|-----------|--------|
| Control type | Preventive, Detective, Corrective |
| Information security properties | Confidentiality, Integrity, Availability |
| Cybersecurity concepts | Identify, Protect, Detect, Respond, Recover |
| Operational capabilities | Governance, Asset management, Protection, etc. |
| Security domains | Governance and ecosystem, Protection, Defence, Resilience |

---

## Implementation Priority for Beetle Studio

### Critical (implement immediately)
- 5.15–5.18: Access control and authentication
- 8.4–8.5: Source code access and secure auth
- 8.7–8.8: Malware protection and vulnerability management
- 8.12: Data leakage prevention (secrets scanning)
- 8.25–8.29: Secure development lifecycle

### High (implement within 30 days)
- 5.1–5.4: Policies and roles
- 5.7: Threat intelligence
- 8.9: Configuration management
- 8.13: Information backup
- 8.28: Secure coding

### Medium (implement within 90 days)
- 5.19–5.22: Supplier security
- 5.24–5.27: Incident management
- 6.1–6.8: People controls
- 7.1–7.14: Physical controls

---

## References

- [ISO/IEC 27001:2022 (ISO official)](https://www.iso.org/standard/27001)
- [ISO/IEC 27002:2022 (Implementation guidance)](https://www.iso.org/standard/75652.html)
- [ISMS.online Annex A Guide](https://www.isms.online/iso-27001/annex-a-2022/)
- [High Table Complete Controls Reference](https://hightable.io/iso-27001-annex-a-controls-reference-guide/)
- [DataGuard Controls Overview](https://www.dataguard.com/iso-27001/annex-a/)
