> Auto-generated from `Security Policy.md` in the docs repo.

> Auto-generated from `SECURITY_POLICY.md` in the docs repo.

> Auto-generated from `docs/SECURITY_POLICY.md` in the docs repo.

---
title: "Security Policy"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Security Policy

**Project:** Beetle Studio  
**Owner:** Kirk Beka (CTO) - architectural security; Maya Rodriguez (Backend) - backend security; Sarah Miller (Build) - signing and distribution  
**Reviewers:** Mooned Dev (CEO)  
**ISO Standards:** ISO/IEC 27001:2022 (information security management)  
**Version:** 1.0.1  
**Last Updated:** 2026-06-20  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Information security objectives, controls, and incident response |
| **Diátaxis form** | Reference |
| **Primary audience** | Kirk Beka, Maya Rodriguez, Sarah Miller, Mooned Dev |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This policy defines the security standards, vulnerability handling procedures, and compliance requirements for Beetle Studio. It applies to all team members, contributors, and third-party integrations.

## Contents

- [Security Objectives](#security-objectives)
- [Secure Development Lifecycle](#secure-development-lifecycle)
  - [Development Security Requirements](#development-security-requirements)
  - [Security-Sensitive Code Areas](#security-sensitive-code-areas)
- [Code Signing & Distribution Security](#code-signing-distribution-security)
- [Data Security](#data-security)
  - [User Data](#user-data)
  - [Local Data](#local-data)
- [Authentication](#authentication)
- [Plugin Security](#plugin-security)
- [Vulnerability Handling](#vulnerability-handling)
  - [Disclosure Policy](#disclosure-policy)
  - [Severity Ratings](#severity-ratings)
- [Security Checks & Verification](#security-checks-verification)
  - [Standards We Verify Against](#standards-we-verify-against)
  - [Verification Layers](#verification-layers)
  - [Verification Levels (ASVS-aligned)](#verification-levels-asvs-aligned)
  - [Penetration Testing](#penetration-testing)
  - [Vulnerability Disclosure](#vulnerability-disclosure)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadre)

---

## Security Objectives

| Objective | Measurement |
|---|---|
| No known critical vulnerabilities in released software | CVSS < 7.0 per release |
| Secure software distribution | All binaries code-signed |
| Secure authentication | Firebase Auth with proper token management |
| Secure data handling | Data encrypted in transit and at rest |
| Incident response | Security incidents responded to within 24 hours |
| Vulnerability disclosure | Reported vulnerabilities triaged within 7 days |

---

## Secure Development Lifecycle

Per **ISO/IEC 27001:2022 Annex A**, security must be built into the software development process.

### Development Security Requirements

| Requirement | Implementation |
|---|---|
| **Secure coding standards** | See [`engineering/TECHNICAL_STANDARDS.md`](../engineering/TECHNICAL_STANDARDS.md) |
| **No hardcoded secrets** | CI checks for credential patterns; secrets in environment variables only |
| **Code review for security** | All security-sensitive changes require Kirk Beka + Maya Rodriguez review |
| **Dependency scanning** | GitHub Dependabot + OWASP dependency check in CI |
| **Static analysis** | Coverity Scan or CodeQL on every PR |
| **Penetration testing** | Annual external pen test before v1.0 launch |

### Security-Sensitive Code Areas

Changes to these areas require mandatory security review:

- Authentication and authorization (Maya Rodriguez)
- Session/token management
- File I/O and path handling
- Plugin loading and sandboxing
- Cloud API communication
- License validation logic

---

## Code Signing & Distribution Security

Per **ISO/IEC 27001:2022 Annex A** (cryptographic controls):

- All executable code must be signed before distribution
- Signing keys stored in Azure Key Vault (HSM-backed)
- Signing access limited to Sarah Miller and Kirk Beka
- Certificate renewal at least 60 days before expiry

See: [`releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md`](../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md)

---

## Data Security

### User Data

| Data Type | Stored | Encryption | Retention |
|---|---|---|---|
| Email / name (Firebase Auth) | Firestore `users/{uid}` | TLS in transit; AES-256 at rest (Firestore default) | Until account deletion; soft-delete 30 days |
| Projects / media (cloud sync, opt-in) | Firebase Storage | TLS in transit; AES-256 at rest | Until account deletion |
| Analytics (opt-in) | BigQuery (anonymized) | TLS in transit; CMEK encryption at rest | 12 months, then auto-purge |
| Crash reports (opt-in) | Firebase Crashlytics | TLS in transit; encrypted at rest | 6 months, then auto-purge |
| Payment info | **Not stored locally** — handled by Microsoft Store (PCI-DSS scope delegated) | TLS via Microsoft Store payment SDK | N/A (Microsoft retains per their ToS) |

### Local Data

| Data Type | Storage Location | Encryption |
|---|---|---|
| Project files | User Documents / AppData | Per-user NTFS ACLs |
| Settings | %APPDATA% | OS file permissions |
| Cache | %LOCALAPPDATA% | Not encrypted (not sensitive) |

---

## Authentication

- Firebase Authentication for all user accounts
- OAuth 2.0 / OpenID Connect for Google sign-in
- Session tokens stored in Windows Credential Manager (encrypted with DPAPI)
- No passwords stored in plain text anywhere

---

## Plugin Security

OpenFX plugins run in the same process as Beetle Studio. Security controls:

- Plugins are code-signed by third-party developers (required for Store distribution)
- Plugins run with the same permissions as Beetle Studio (no sandbox)
- Users can disable plugin loading: **Edit → Preferences → Plugins → Disable Plugin Loading**
- Plugin API exposes limited interfaces - no arbitrary code execution from plugin host

---

## Vulnerability Handling

### Disclosure Policy

We follow a **coordinated vulnerability disclosure** process:

1. **Report:** Security researcher contacts `security@mooned.dev`
2. **Triage:** Kirk Beka triages within 7 days
3. **Fix:** Development team prioritizes fix based on severity
4. **Release:** Fix shipped in next patch or hotfix
5. **Credit:** Researcher credited in release notes (unless anonymous)

### Severity Ratings

| Rating | CVSS Score | Response Time | Example |
|---|---|---|---|
| **Critical** | 9.0-10.0 | 24 hours | Remote code execution |
| **High** | 7.0-8.9 | 7 days | Privilege escalation |
| **Medium** | 4.0-6.9 | Next release | Denial of service |
| **Low** | 0.1-3.9 | Next release | Information disclosure |

---

## Security Checks & Verification

This section enumerates the security checks we run against Beetle Studio, the marketing website (mooned.dev), and the Firebase backend. Each check is anchored to a specific control in one of the standards we follow.

### Standards We Verify Against

| Standard | Scope | Verification |
|---|---|---|
| **ISO/IEC 27001:2022** | Information Security Management System (ISMS) | Annual internal audit + Stage 1/2 certification audit by accredited body |
| **ISO/IEC 27002:2022** | Information security controls (Annex A) | 93 controls checked via ISMS audit; gaps tracked in risk register |
| **ISO/IEC 27034-1:2011** | Application security framework | ASVS verification (see below) feeds 27034 controls |
| **OWASP ASVS 4.0.3** | Application Security Verification Standard | L2 mandatory for all app releases; L3 for security-sensitive features (auth, payment, sync) |
| **OWASP Top 10 2021** | Most common web app risks | Mapped to ASVS; each Top 10 item has a concrete control in [`API_CONTRACT.md`](../backend/API_CONTRACT.md) or [`INFRASTRUCTURE_OVERVIEW.md`](../operations/INFRASTRUCTURE_OVERVIEW.md) |
| **NIST SP 800-218 (SSDF 1.1)** | Secure Software Development Framework | Practice tags (PO, PS, PW, RV) applied to every PR template |
| **CWE Top 25 (2023)** | Most dangerous software weaknesses | Static analysis gates the 25 categories; see CI/CD section below |

### Verification Layers

| Layer | Tool | What It Checks | Standard Mapping | Frequency |
|---|---|---|---|---|
| **SAST (static analysis)** | SonarQube / Semgrep (CWE ruleset) | CWE Top 25, injection, XSS, hardcoded secrets | ASVS V1, V5, V11; SSDF PW.4 | Every PR + nightly |
| **SCA (dependency scan)** | Dependabot + npm-audit + pip-audit (backend) + vcpkg audit (C++) | Known CVEs in third-party packages | ASVS V14; ISO 27002 A.8.8 | Every PR + daily |
| **Secret detection** | Gitleaks + TruffleHog | Committed credentials, API keys, tokens | ASVS V2.10; ISO 27002 A.8.24 | Pre-commit hook + every PR |
| **DAST (dynamic scan)** | OWASP ZAP (baseline + active) | Runtime vulnerabilities on staging web builds | ASVS V1, V13; OWASP Top 10 | Weekly + per release |
| **Container/image scan** | Trivy (Cloud Run images) | OS + library CVEs in deployed images | ISO 27002 A.8.9 | Per build |
| **IaC scan** | Checkov + tfsec | Azure + Firebase config misconfigurations | ISO 27002 A.8.9, A.8.32 | Every PR |
| **License compliance** | FOSSA | Open-source license violations | ISO 27002 A.5.31 | Weekly |

### Verification Levels (ASVS-aligned)

| Level | Scope | Required for |
|---|---|---|
| **ASVS L1** | Baseline - blocks the OWASP Top 10 | All releases |
| **ASVS L2** | Standard - defense in depth, threat-modeled | All releases |
| **ASVS L3** | High-assurance - verified penetration testing | Auth, payment, license enforcement, cloud sync |

### Penetration Testing

| Type | Scope | Frequency | Owner |
|---|---|---|---|
| **External pen test** | Public web (mooned.dev) + cloud APIs | Annual + on major auth change | Third-party firm |
| **Internal pen test** | All infrastructure + internal tools | Annual | Third-party firm |
| **Bug bounty** | Public web + app | Continuous via HackerOne | Community |

### Vulnerability Disclosure

- **Reporting channel:** `security@mooned.dev` + HackerOne program
- **Acknowledgment:** within 48 hours
- **Triage:** within 7 days
- **Public disclosure:** coordinated with reporter, minimum 90 days from report to fix-or-disclose

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial policy - fully aligned with ISO/IEC 27001:2022 |
| 1.0.1 | 2026-06-20 | Kirk Beka - Replaced `?` placeholders in User Data table with concrete encryption + retention details; payment info row now references Microsoft Store delegation (PCI-DSS scope) |

---

*Grounded in: ISO/IEC 27001:2022 - Information Security Management Systems*



---

## References

### Internal Documents

- [`../engineering/TECHNICAL_STANDARDS.md`](../engineering/TECHNICAL_STANDARDS.md) - Secure coding standards
- [`../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md`](../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md) - Signing infrastructure
- [`../backend/API_CONTRACT.md`](../backend/API_CONTRACT.md) - API security controls
- [`../operations/INFRASTRUCTURE_OVERVIEW.md`](../operations/INFRASTRUCTURE_OVERVIEW.md) - Infra controls

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering - Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering - Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Kirk Beka | Initial version |
| 1.0.1 | 2026-06-20 | Kirk Beka | Replaced `?` placeholders in User Data table with concrete encryption + retention details |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Kirk Beka (CTO) - architectural security
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type