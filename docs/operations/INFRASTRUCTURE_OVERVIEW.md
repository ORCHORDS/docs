# Infrastructure Overview

**Project:** Beetle Studio  
**Owner:** Mike Johnson (DevOps Lead)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)  
**ISO Standards:** ISO/IEC 27001:2022 (Annex A: Operational Security), ISO/IEC 12207:2017 (development infrastructure)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Azure and Firebase services, access control, costs, and monitoring |
| **Diátaxis form** | Reference |
| **Primary audience** | Mike Johnson, Kirk Beka, Mooned Dev |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes Mooned Dev's cloud and development infrastructure -- the Azure services, Firebase services, and internal tooling that power Beetle Studio. Per **ISO/IEC 27001:2022 Annex A**, operational security requires that infrastructure be documented, access-controlled, and monitored.
## Contents

- [Cloud Infrastructure — Azure](#cloud-infrastructure-azure)
  - [Resource Groups](#resource-groups)
  - [Azure Services](#azure-services)
  - [Azure Blob Storage Containers](#azure-blob-storage-containers)
- [Firebase Services](#firebase-services)
  - [Firebase Project Structure](#firebase-project-structure)
- [Infrastructure as Code](#infrastructure-as-code)
- [Access Control](#access-control)
  - [Azure](#azure)
  - [Firebase](#firebase)
- [Monitoring & Alerting](#monitoring-alerting)
- [Cost Estimates (Monthly)](#cost-estimates-monthly)
- [Web Security & Cloudflare](#web-security-cloudflare)
  - [Why Cloudflare](#why-cloudflare)
  - [Cloudflare Configuration](#cloudflare-configuration)
  - [WAF Custom Rules (skeleton)](#waf-custom-rules-skeleton)
  - [Security Headers (origin side)](#security-headers-origin-side)
  - [Origin Protection](#origin-protection)
  - [Cloudflare Workers (planned)](#cloudflare-workers-planned)
  - [Monitoring & Alerts](#monitoring-alerts)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Cloud Infrastructure — Azure

### Resource Groups

| Resource Group | Purpose | Environment |
|---|---|---|
| `beetle-studio-prod` | Production Beetle Studio services | Production |
| `beetle-studio-staging` | Staging / pre-production | Non-production |
| `beetle-studio-shared` | Shared infra (CI runners, monitoring) | Shared |

### Azure Services

| Service | Tier | Purpose | Access |
|---|---|---|---|
| **Azure App Service** | S1 | Static website hosting (mooned.dev) | Public |
| **Azure Blob Storage** | Standard | CI artifacts, release builds, backups | Restricted |
| **Azure Key Vault** | Standard | Secrets, signing certificates | Admin only |
| **Azure Monitor / Log Analytics** | — | Infrastructure monitoring and alerting | Mike Johnson + Kirk Beka |
| **GitHub Actions** | SaaS | CI/CD pipelines | All engineers |
| **Azure VM (CI Runners)** | D2s_v3 | Self-hosted GitHub Actions runners | Mike Johnson |

### Azure Blob Storage Containers

| Container | Access | Contents |
|---|---|---|
| `beetle-releases` | Private (signed URLs) | Release installers, portable builds |
| `beetle-builds` | Private | CI artifacts (90-day retention) |
| `beetle-backups` | Private | Source code mirrors, Firestore exports |
| `beetle-website` | Public | Static website assets |

---

## Firebase Services

| Service | Plan | Purpose | Access |
|---|---|---|---|
| **Firebase Authentication** | Blaze (pay-as-you-go) | User authentication (email, Google OAuth) | All engineers (read); Maya Rodriguez (admin) |
| **Firestore** | Blaze | User data, project metadata | All engineers (read); Maya Rodriguez (admin) |
| **Firebase Storage** | Blaze | Cloud sync of project assets | All engineers (read); Maya Rodriguez (admin) |
| **Firebase Cloud Functions** | Blaze | Backend business logic, API endpoints | Maya Rodriguez (deploy); Mike Johnson (monitoring) |
| **Firebase Hosting** | Spark (free) | Landing pages | Jason Wong (manage) |
| **Firebase Crashlytics** | Free | Crash reporting | Lisa Martinez (admin); all engineers (read) |
| **Firebase Performance** | Free | Performance monitoring | Lisa Martinez (admin) |

### Firebase Project Structure

```
beetle-studio-prod (Firebase project)
├── Authentication
│   ├── Email/password
│   └── Google OAuth
├── Firestore
│   ├── /users/{userId}
│   └── /users/{userId}/projects/{projectId}
├── Storage
│   └── /users/{userId}/projects/{projectId}/assets/
└── Cloud Functions
    ├── /api/v1/sync
    ├── /api/v1/license/validate
    └── /api/v1/analytics/event
```

---

## Infrastructure as Code

All infrastructure is defined in code:

```
infrastructure/
├── terraform/
│   ├── main.tf                 ← core resources
│   ├── storage.tf             ← blob containers
│   ├── keyvault.tf            ← secrets and keys
│   └── monitoring.tf           ← log analytics, alerts
└── scripts/
    ├── provision_runner.sh    ← CI runner setup
    └── backup_firestore.sh   ← nightly backup
```

- Changes require a PR reviewed by Mike Johnson or Kirk Beka
- Terraform state is stored in Azure Blob Storage with versioning enabled
- No manual changes to production infrastructure — all changes go through Terraform

---

## Access Control

### Azure

| Role | Who | Access Level |
|---|---|---|
| **Owner** | Mooned Dev | Full access to all resources |
| **Contributor** | Mike Johnson, Kirk Beka | Full deploy and config access |
| **DevOps Engineer** | Mike Johnson | Deploy, monitor, configure |
| **Read-Only** | All engineers | View only; no deploy |
| **No Access** | Default | No Azure portal access |

### Firebase

| Role | Who | Access Level |
|---|---|---|
| **Owner** | Mooned Dev | Full Firebase console |
| **Admin** | Maya Rodriguez | All Firebase services |
| **Developer** | All engineers | Read-only Firestore + Auth |
| **QA** | Lisa Martinez | Crashlytics + Performance only |

---

## Monitoring & Alerting

| What | Tool | Who Gets Alerted |
|---|---|---|
| Azure resource health | Azure Monitor + email | Mike Johnson |
| GitHub Actions failures | GitHub notification → Slack #ci-alerts | Mike Johnson |
| Firebase function errors | Firebase Console + email | Maya Rodriguez |
| Firebase function latency | Firebase Performance + PagerDuty | Maya Rodriguez |
| Release crash rate (first 24h) | Crashlytics → Slack #releases | Lisa Martinez |
| Cloud storage quota | Azure Monitor | Mike Johnson |

---

## Cost Estimates (Monthly)

| Service | Estimated Cost | Notes |
|---|---|---|
| Azure App Service | ~$50/month | Static site; minimal |
| Azure Blob Storage | ~$20/month | ~500 GB storage |
| Azure Key Vault | ~$3/month | Minimal secrets |
| Azure VM (CI Runner) | ~$150/month | D2s_v3, always-on |
| Firebase Blaze (projected) | ~$100/month | Based on user growth |
| **Total** | **~$323/month** | At current scale |

---

## Web Security & Cloudflare

The marketing site (`mooned.dev`) and any user-facing web apps are fronted by **Cloudflare** for DDoS protection, WAF, and edge caching. This section documents the Cloudflare configuration and the security controls we apply at the edge.

### Why Cloudflare

| Capability | What it gives us | Standard Mapping |
|---|---|---|
| **DDoS protection** (L3/L4/L7) | Automatic mitigation, no capacity planning | ISO 27002 A.5.30 |
| **Web Application Firewall (WAF)** | Managed ruleset + custom rules block OWASP Top 10 | ASVS V13; OWASP Top 10 |
| **TLS 1.3** | Encrypted in transit, modern cipher suites | ISO 27002 A.8.24 |
| **Rate limiting** | Per-IP and per-endpoint throttling | ISO 27002 A.5.31 |
| **Bot management** | Bad bot blocking, allow-list for known good bots | ISO 27002 A.5.31 |
| **Edge caching** | Reduced origin load, faster TTFB | Performance (Core Web Vitals) |
| **DNSSEC** | Signed DNS records, prevents spoofing | ISO 27002 A.8.21 |

### Cloudflare Configuration

| Setting | Value | Why |
|---|---|---|
| **Plan** | **Business** | Need WAF + advanced rate limiting (managed ruleset), Workers Unbound for the auth pre-check, and 100% uptime SLA. Pro is cheaper but lacks the WAF custom ruleset tier and the Bot Management add-on; Business covers everything in the launch spec. Locked 2026-06-20 by Mooned Dev (CEO) - confirm with Mike Johnson before next billing cycle. |
| **SSL/TLS mode** | Full (strict) | Origin pulls must be authenticated |
| **HSTS** | Enabled, max-age 1 year, includeSubDomains, preload | HSTS header sent to all clients |
| **Minimum TLS version** | 1.2 (target: 1.3 only) | Block legacy clients |
| **HTTP/3** | Enabled | Performance |
| **DNSSEC** | Enabled | DNS integrity |
| **Caching level** | Standard, with explicit purge on deploy | Predictable invalidation |

### WAF Custom Rules (skeleton)

| Rule | Expression | Action |
|---|---|---|
| Block SQL injection attempts | URI contains `union select` or `; drop` | Managed WAF |
| Block known bad user-agents | `cf.client.bot` is false AND `http.user_agent` matches `(?i)(sqlmap\|nikto)` | Block |
| Rate limit login endpoint | Rate > 10 per minute AND URI contains `/login` | Challenge |
| Geo-fence admin endpoints | URI contains `/admin` AND `ip.geoip.country` not in `{"US","MY","GB"}` | Block |

### Security Headers (origin side)

Sent on every response from the origin; Cloudflare passes them through. See [API_CONTRACT.md Security Requirements](../backend/API_CONTRACT.md#security-requirements) for the full list.

| Header | Value |
|---|---|
| `Content-Security-Policy` | `default-src 'self'; ...` (strict, no unsafe-inline) |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=()` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` |

### Origin Protection

- **Cloudflare Tunnel** (preferred) or **Origin CA certificate** — origin only accepts connections from Cloudflare IP ranges
- **IP allowlist** on Azure App Service blocks direct origin access
- **Azure WAF** as a second layer on the Application Gateway

### Cloudflare Workers (planned)

Edge logic for:
- A/B testing on landing pages
- Bot scoring before origin hit
- Custom auth flows (e.g. license validation cache)

### Monitoring & Alerts

| Alert | Condition | Channel |
|---|---|---|
| WAF blocks spike | `> 100 blocked requests in 5 min` | PagerDuty |
| Origin 5xx spike | `> 1% error rate over 5 min` | PagerDuty |
| TLS handshake failures | `> 0.5% over 10 min` | Slack |
| Rate limit triggers | `> 50 challenges per minute` | Slack |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial overview — aligned with ISO/IEC 27001:2022 Annex A and ISO/IEC 12207:2017 |

---

*Grounded in: ISO/IEC 27001:2022 Annex A (Operational Security), ISO/IEC 12207:2017 §6.3 (Development Infrastructure)*



---

## References

### Internal Documents

- [$title](./../backend/API_CONTRACT.md)

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