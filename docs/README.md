---
title: "Beetle Studio — Documentation Index"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Beetle Studio — Documentation Index

**Project:** Beetle Studio
**Owner:** Tom Anderson (Technical Writer) — content; Kirk Beka (CTO) — technical authority
**Reviewers:** Mooned Dev (CEO), all domain leads
**ISO Standards:** ISO/IEC 12207:2017, ISO/IEC 19770-2:2015, ISO/IEC 25010:2023, ISO/IEC 14764:2022, ISO/IEC 27001:2022, ISO/IEC 27002:2022, ISO/IEC 27034-1:2011, ISO 9241, ISO/IEC/IEEE 82079-1:2019, OWASP ASVS 4.0.3, OWASP Top 10 2021, NIST SP 800-218 (SSDF), CWE Top 25
**Version:** 3.4.0
**Last Updated:** 2026-06-21

---

## Contents

- [About This Documentation](#about-this-documentation)
- [Document Map](#document-map)
  - [Meta-Documents](#metadocuments)
  - [Releases & Distribution](#releases-distribution)
  - [Engineering Standards](#engineering-standards)
  - [Engineering Subsystems](#engineering-subsystems)
  - [User Documentation](#user-documentation)
  - [Product & Design](#product-design)
  - [Operations](#operations)
  - [Community](#community)
  - [Marketing](#marketing)
  - [Business Development](#business-development)
  - [Help & Support](#help-support)
  - [Cross-Functional](#crossfunctional)
- [Security & Web Testing](#security-web-testing)
  - [Security](#security)
  - [Desktop UI Test Tools (C++/Qt6 Windows app)](#desktop-ui-test-tools-cqt6-windows-app)
  - [Web Design Testing (`mooned.dev` and any user-facing web)](#web-design-testing-mooneddev-and-any-userfacing-web)
  - [Standards Anchors (Security + Web)](#standards-anchors-security-web)
- [Document Versioning](#document-versioning)
- [Ownership & Review Cadence](#ownership-review-cadence)
- [Contributing](#contributing)

---
## About This Documentation

This `docs/` directory contains all technical and operational documentation for Beetle Studio. Documents are organized by domain and owner, grounded in relevant ISO/IEC standards:

- **ISO/IEC 12207:2017** — Software lifecycle processes
- **ISO/IEC 19770-2:2015** — IT asset management & software identification
- **ISO/IEC 25010:2023** — Software product quality model
- **ISO/IEC 14764:2022** — Software maintenance
- **ISO/IEC 27001:2022** — Information security management
- **ISO/IEC 27002:2022** — Information security controls
- **ISO/IEC 27034-1:2011** — Application security
- **ISO 9241** — Ergonomic requirements (UI/UX & accessibility)
- **ISO/IEC/IEEE 82079-1:2019** — Preparation of information for use
- **ISO/IEC Directives Part 2:2021** — Document structure and drafting rules
- **OWASP ASVS 4.0.3** — Application Security Verification Standard
- **OWASP Top 10 2021** — Most common web app risks
- **NIST SP 800-218 (SSDF 1.1)** — Secure Software Development Framework
- **CWE Top 25** — Most dangerous software weaknesses
- **Diátaxis** — Documentation structure framework (tutorial / how-to / reference / explanation)

All documents in this directory follow the conventions defined in [`STYLE_GUIDE.md`](./STYLE_GUIDE.md), which codifies the rules for headers, structure, naming, tone, and maintenance. If you are writing a new document or editing an existing one, read the Style Guide first.

## Document Map

### Meta-Documents

| Document | Purpose |
|---|---|
| [`STYLE_GUIDE.md`](./STYLE_GUIDE.md) | Canonical reference for all documentation conventions, grounded in ISO/IEC/IEEE 82079-1:2019, ISO/IEC Directives Part 2, and Diátaxis |

### Releases & Distribution
*Owner: Sarah Miller (Build & Release Engineer)*

| Document | Purpose |
|---|---|
| [`releases/VERSIONING_POLICY.md`](./releases/VERSIONING_POLICY.md) | Semantic Versioning scheme, lifecycle stages, branching model |
| [`releases/RELEASE_CHECKLIST.md`](./releases/RELEASE_CHECKLIST.md) | Step-by-step release gate checklist |
| [`releases/CHANGELOG_POLICY.md`](./releases/CHANGELOG_POLICY.md) | Keep a Changelog format, authorship, automation |
| [`releases/INSTALLER_SPEC.md`](./releases/INSTALLER_SPEC.md) | Installer requirements per platform |
| [`releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md`](./releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md) | Certificate lifecycle, Azure Artifact Signing |
| [`releases/WINDOWS_STORE_SUBMISSION.md`](./releases/WINDOWS_STORE_SUBMISSION.md) | Store compliance, submission checklist |
| [`releases/SWID_TAG_SPEC.md`](./releases/SWID_TAG_SPEC.md) | ISO/IEC 19770-2 SWID tag implementation |

### Engineering Standards
*Owners: Mike Johnson (DevOps) & Kirk Beka (CTO)*

| Document | Purpose |
|---|---|
| [`engineering/BUILD_SYSTEM.md`](./engineering/BUILD_SYSTEM.md) | CMake configuration, build targets, artifacts |
| [`engineering/CI_CD_PIPELINE.md`](./engineering/CI_CD_PIPELINE.md) | Forgejo Actions workflows (GitHub Actions–compatible syntax), automation, rollbacks |
| [`engineering/BRANCHING_STRATEGY.md`](./engineering/BRANCHING_STRATEGY.md) | Git branching model and merge policy |
| [`engineering/TECHNICAL_STANDARDS.md`](./engineering/TECHNICAL_STANDARDS.md) | C++ coding standards, API design, RFC process |
| [`engineering/ARCHITECTURE_OVERVIEW.md`](./engineering/ARCHITECTURE_OVERVIEW.md) | System architecture, module boundaries, data flow |
| [`engineering/TEST_STRATEGY.md`](./engineering/TEST_STRATEGY.md) | Test pyramid, coverage targets, bug severity, release test pass |
| [`engineering/BACKUP_DISASTER_RECOVERY.md`](./engineering/BACKUP_DISASTER_RECOVERY.md) | RTO/RPO, backup strategy, disaster recovery playbooks |
| [`operations/INFRASTRUCTURE_OVERVIEW.md`](./operations/INFRASTRUCTURE_OVERVIEW.md) | Azure & Firebase services, access control, IaC, monitoring |

### Engineering Subsystems
*Owners: Domain leads (James Park, Sophie Williams, Daniel Kim, Emma Thompson, Ryan Foster, Alex Chen, Maya Rodriguez)*

| Document | Owner | Purpose |
|---|---|---|
| [`graphics/RENDERING_PIPELINE.md`](./graphics/RENDERING_PIPELINE.md) | James Park | DX12/Vulkan render graph, shader overview |
| [`graphics/SHADER_SPEC.md`](./graphics/SHADER_SPEC.md) | James Park | HLSL shader interface, parameters, adding new shaders |
| [`codecs/FORMAT_SUPPORT_MATRIX.md`](./codecs/FORMAT_SUPPORT_MATRIX.md) | Sophie Williams | Supported codecs, hardware encoders, seeking |
| [`effects/OPENFX_PLUGIN_SDK.md`](./effects/OPENFX_PLUGIN_SDK.md) | Daniel Kim | Plugin API, parameter format, SDK docs |
| [`effects/EFFECTS_LIBRARY.md`](./effects/EFFECTS_LIBRARY.md) | Daniel Kim | Catalog of built-in effects, parameters, GPU cost |
| [`timeline/DATA_MODEL.md`](./timeline/DATA_MODEL.md) | Emma Thompson | Clip/track data structures, undo system |
| [`audio/VST_SDK_INTEGRATION.md`](./audio/VST_SDK_INTEGRATION.md) | Ryan Foster | VST hosting, delay compensation, sync |
| [`ui/COMPONENT_LIBRARY.md`](./ui/COMPONENT_LIBRARY.md) | Alex Chen | Qt6 widget patterns, DPI handling, shortcuts |
| [`backend/API_CONTRACT.md`](./backend/API_CONTRACT.md) | Maya Rodriguez | Firebase API endpoints, auth flow, sync protocol |



### Audio Subsystem

| Document | Owner | Description |
|----------|-------|-------------|
| [Transcriber Pipeline](audio/TRANSCRIBER_PIPELINE.md) | Ryan Foster | v1.3.0 — Demucs vocal separation + Whisper ASR + chapter detection + JSONL streaming |
| [Transcriber Quality Audit](audio/TRANSCRIBER_QUALITY_AUDIT.md) | Ryan Foster | WER/CER measurements across real-world and synthetic audio |
| [VST SDK Integration](audio/VST_SDK_INTEGRATION.md) | Ryan Foster | VST plugin hosting architecture and delay compensation |

### User Documentation
*Owner: Tom Anderson (Technical Writer)*

| Document | Purpose |
|---|---|
| [`user/USER_GUIDE.md`](./user/USER_GUIDE.md) | Comprehensive application manual |
| [`user/KEYBOARD_SHORTCUTS.md`](./user/KEYBOARD_SHORTCUTS.md) | Complete keyboard shortcut reference |
| [`user/QUICK_START.md`](./user/QUICK_START.md) | First project tutorial |

### Product & Design
*Owner: Chris Taylor (Product Manager)*

| Document | Purpose |
|---|---|
| [`product/ROADMAP.md`](./product/ROADMAP.md) | Living product roadmap, feature lifecycle, priority tiers |
| [`product/PRIORITY_FRAMEWORK.md`](./product/PRIORITY_FRAMEWORK.md) | MoSCoW + RICE scoring methodology |

### Operations
*Owner: Amanda Clark (Operations) & Mike Johnson (DevOps)*

| Document | Purpose |
|---|---|
| [`operations/ONBOARDING_GUIDE.md`](./operations/ONBOARDING_GUIDE.md) | First-day, first-week, first-month checklist for new hires |
| [`operations/INFRASTRUCTURE_OVERVIEW.md`](./operations/INFRASTRUCTURE_OVERVIEW.md) | Azure & Firebase services, access control, costs |

### Community
*Owner: Rachel Green (Community Manager)*

| Document | Purpose |
|---|---|
| [`community/COMMUNITY_MANAGEMENT.md`](./community/COMMUNITY_MANAGEMENT.md) | Discord/forum management, feedback triage, community guidelines |

### Marketing
*Owner: Jason Wong (Marketing Lead)*

| Document | Purpose |
|---|---|
| [`marketing/LAUNCH_PLAYBOOK.md`](./marketing/LAUNCH_PLAYBOOK.md) | Pre-launch, launch day, and post-launch marketing playbook |

### Business Development
*Owner: Kevin Brown (Business Development)*

| Document | Purpose |
|---|---|
| [`business/ENTERPRISE_LICENSING.md`](./business/ENTERPRISE_LICENSING.md) | Enterprise licensing tiers, OEM deals, ISO/IEC 19770-2 compliance |

### Help & Support
*Owner: Tom Anderson (Technical Writer)*

| Document | Purpose |
|---|---|
| [`help/TROUBLESHOOTING.md`](./help/TROUBLESHOOTING.md) | Common issues and fixes |
| [`help/FAQ.md`](./help/FAQ.md) | Frequently asked questions |

### Cross-Functional
*Shared ownership*

| Document | Owners | Purpose |
|---|---|---|
| [`SECURITY_POLICY.md`](./SECURITY_POLICY.md) | Kirk Beka, Maya Rodriguez, Sarah Miller | Security requirements and controls |
| [`PERFORMANCE_BENCHMARKS.md`](./PERFORMANCE_BENCHMARKS.md) | James Park, Lisa Martinez, Sophie Williams | Performance targets and measurement |
| [`ACCESSIBILITY_COMPLIANCE.md`](./ACCESSIBILITY_COMPLIANCE.md) | Alex Chen, Nina Patel | WCAG compliance and accessibility audit |
| [`BETA_PROGRAM_GUIDE.md`](./BETA_PROGRAM_GUIDE.md) | Lisa Martinez, Rachel Green | Beta testing program structure |
| [`OPENFX_PLUGIN_GUIDE.md`](./OPENFX_PLUGIN_GUIDE.md) | Daniel Kim, Tom Anderson | Third-party plugin guide for users |

---

## Contents

- [About This Documentation](#about-this-documentation)
- [Document Map](#document-map)
  - [Meta-Documents](#metadocuments)
  - [Releases & Distribution](#releases-distribution)
  - [Engineering Standards](#engineering-standards)
  - [Engineering Subsystems](#engineering-subsystems)
  - [User Documentation](#user-documentation)
  - [Product & Design](#product-design)
  - [Operations](#operations)
  - [Community](#community)
  - [Marketing](#marketing)
  - [Business Development](#business-development)
  - [Help & Support](#help-support)
  - [Cross-Functional](#crossfunctional)
- [Security & Web Testing](#security-web-testing)
  - [Security](#security)
  - [Desktop UI Test Tools (C++/Qt6 Windows app)](#desktop-ui-test-tools-cqt6-windows-app)
  - [Web Design Testing (`mooned.dev` and any user-facing web)](#web-design-testing-mooneddev-and-any-userfacing-web)
  - [Standards Anchors (Security + Web)](#standards-anchors-security-web)
- [Document Versioning](#document-versioning)
- [Ownership & Review Cadence](#ownership-review-cadence)
- [Contributing](#contributing)

---
## Security & Web Testing

The following cross-functional concerns are documented in the indicated sections. The current docs are organized by domain rather than by concern, so these maps point you to the right place.

### Security

| Concern | Where to look |
|---|---|
| **Security policy + objectives** | [`SECURITY_POLICY.md`](./SECURITY_POLICY.md) |
| **Security checks + verification** (SAST, SCA, DAST, secrets, IaC, container, licenses) | [`SECURITY_POLICY.md` -> Security Checks & Verification](./SECURITY_POLICY.md#security-checks--verification) |
| **Cloudflare edge (DDoS, WAF, TLS, headers, rate limiting)** | [`INFRASTRUCTURE_OVERVIEW.md` -> Web Security & Cloudflare](./operations/INFRASTRUCTURE_OVERVIEW.md#web-security--cloudflare) |
| **Firebase Auth, Security Rules, Cloud Functions security** | [`API_CONTRACT.md` -> Firebase Security Rules](./backend/API_CONTRACT.md#firebase-security-rules) |
| **Security scans in CI/CD + SBOM + vulnerability disclosure** | [`CI_CD_PIPELINE.md` -> Security Scans in CI/CD](./engineering/CI_CD_PIPELINE.md#security-scans-in-cicd) |
| **Code signing + distribution security** | [`SECURITY_POLICY.md` -> Code Signing & Distribution Security](./SECURITY_POLICY.md#code-signing--distribution-security) |

### Desktop UI Test Tools (C++/Qt6 Windows app)

| Tool | Purpose | Where to look |
|---|---|---|
| **WinAppDriver** | Microsoft official UI automation — drives the real Windows app via UIA | [`TEST_STRATEGY.md` -> UI Test Tools](./engineering/TEST_STRATEGY.md#ui-test-tools) |
| **FlaUI** | .NET UIA wrapper — fast in-process UI assertions | [`TEST_STRATEGY.md` -> UI Test Tools](./engineering/TEST_STRATEGY.md#ui-test-tools) |
| **PyAutoGUI** | Cross-platform mouse/keyboard/screenshot — ad-hoc repro & engineer-local smoke | [`TEST_STRATEGY.md` -> UI Test Tools](./engineering/TEST_STRATEGY.md#ui-test-tools) |
| **Qt Test (QTest)** | Widget unit tests (already in our stack) | [`TEST_STRATEGY.md` -> Test Types](./engineering/TEST_STRATEGY.md#test-types) |
| **Bug report template** | Expected-vs-actual + before/after image loop, full 8-section template + self-question checklist | [`TEST_STRATEGY.md` -> Bug Investigation: Expected vs Actual + Before/After Loop](./engineering/TEST_STRATEGY.md#bug-investigation-expected-vs-actual--beforeafter-loop) |

### Web Design Testing (`mooned.dev` and any user-facing web)

| Concern | Where to look |
|---|---|
| **Accessibility (WCAG 2.1 AA + axe-core)** | [`ACCESSIBILITY_COMPLIANCE.md` -> Website Design Testing](./ACCESSIBILITY_COMPLIANCE.md#website-design-testing) |
| **Performance (Core Web Vitals, Lighthouse CI, bundle budgets)** | [`PERFORMANCE_BENCHMARKS.md` -> Web Performance (Core Web Vitals)](./PERFORMANCE_BENCHMARKS.md#web-performance-core-web-vitals) |
| **Browser & device compatibility** | [`ACCESSIBILITY_COMPLIANCE.md` -> Website Design Testing](./ACCESSIBILITY_COMPLIANCE.md#website-design-testing) |
| **Visual regression (Percy / Chromatic / Playwright)** | [`ACCESSIBILITY_COMPLIANCE.md` -> Website Design Testing](./ACCESSIBILITY_COMPLIANCE.md#website-design-testing) |

### Standards Anchors (Security + Web)

| Standard / Framework | Where it's verified |
|---|---|
| ISO/IEC 27001:2022 (ISMS) | Annual internal + Stage 1/2 audit |
| ISO/IEC 27002:2022 (Annex A controls) | ISMS audit, 93 controls |
| ISO/IEC 27034-1:2011 (application security) | ASVS verification feeds 27034 |
| OWASP ASVS 4.0.3 | L2 mandatory, L3 for security-sensitive features |
| OWASP Top 10 2021 | Mapped to ASVS + Cloudflare WAF + Firebase rules |
| NIST SP 800-218 (SSDF) | PR template practice tags (PO, PS, PW, RV) |
| CWE Top 25 (2023) | Semgrep + SonarQube static analysis |
| WCAG 2.1 AA | `mooned.dev` web audit (manual + axe-core + pa11y-ci) |
| Core Web Vitals | Lighthouse CI + CrUX field data |

---

## Contents

- [About This Documentation](#about-this-documentation)
- [Document Map](#document-map)
  - [Meta-Documents](#metadocuments)
  - [Releases & Distribution](#releases-distribution)
  - [Engineering Standards](#engineering-standards)
  - [Engineering Subsystems](#engineering-subsystems)
  - [User Documentation](#user-documentation)
  - [Product & Design](#product-design)
  - [Operations](#operations)
  - [Community](#community)
  - [Marketing](#marketing)
  - [Business Development](#business-development)
  - [Help & Support](#help-support)
  - [Cross-Functional](#crossfunctional)
- [Security & Web Testing](#security-web-testing)
  - [Security](#security)
  - [Desktop UI Test Tools (C++/Qt6 Windows app)](#desktop-ui-test-tools-cqt6-windows-app)
  - [Web Design Testing (`mooned.dev` and any user-facing web)](#web-design-testing-mooneddev-and-any-userfacing-web)
  - [Standards Anchors (Security + Web)](#standards-anchors-security-web)
- [Document Versioning](#document-versioning)
- [Ownership & Review Cadence](#ownership-review-cadence)
- [Contributing](#contributing)

---
## Document Versioning

Each document follows [SemVer](./releases/VERSIONING_POLICY.md). Document versions increment on material changes.

| Version | Change |
|---|---|
| `1.0.0` | Initial complete documentation set (June 2026) |
| `2.0.0` | Added 10 new docs: DR, Roadmap, Priority Framework, Onboarding, Infrastructure, Community Management, Launch Playbook, Shader Spec, Effects Library, Enterprise Licensing |
| `3.0.0` | Created `STYLE_GUIDE.md` codifying conventions per ISO/IEC/IEEE 82079-1:2019 + Diátaxis; moved `software-versioning-guide.md` to `releases/VERSIONING_POLICY.md`; added `## Scope & Audience`, `## Overview`, `## Contents` (long docs), and `## Document Maintenance` blocks to all 40 docs; fixed double-encoded UTF-8 mojibake |
| `3.1.0` | Added security + web design testing sections: `## Security Checks & Verification` in `SECURITY_POLICY.md` (ISO/IEC 27001/27002/27034 + OWASP ASVS 4.0.3 + OWASP Top 10 + NIST SSDF + CWE Top 25), `## Web Security & Cloudflare` in `INFRASTRUCTURE_OVERVIEW.md`, `## Firebase Security Rules` in `API_CONTRACT.md`, `## Security Scans in CI/CD` in `CI_CD_PIPELINE.md`, `## Website Design Testing` in `ACCESSIBILITY_COMPLIANCE.md` (WCAG 2.1 AA + Core Web Vitals + browser compat + visual regression), `## Web Performance (Core Web Vitals)` in `PERFORMANCE_BENCHMARKS.md` |
| `3.2.0` | Added UI test tools section to `TEST_STRATEGY.md`: WinAppDriver (Microsoft UI automation for our C++/Win32/Qt6 desktop app), FlaUI (.NET UIA wrapper for fine-grained in-process UI assertions), PyAutoGUI (cross-platform, for ad-hoc repro and engineer-local visual smoke scripts). Each tool has when-to-use, when-NOT-to-use, code sample, and CI integration notes. |
| `3.3.0` | Added `## Bug Investigation: Expected vs Actual + Before/After Loop` to `TEST_STRATEGY.md`. Defines the 5-question self-investigation loop, the full 8-section bug report template, before/after image file conventions, image-aware bug review process for engineers, self-question checklist, anti-patterns, and tracking metrics. Also added a Required subsection to `BETA_PROGRAM_GUIDE.md` Bug Reporting Requirements mandating the template + a quick-template for casual Discord reports. |
| `3.4.0` | Created `tests/ui/` repository scaffolding: WinAppDriver project (C# / .NET 8, NUnit, Appium.WebDriver) with AppDriver session helper, Locators (single source of truth for UIA AutomationIds), BugReport helper, Smoke_NewProjectFlow example, and start-winappdriver.ps1. FlaUI project (C# / .NET 8, FlaUI.Core + FlaUI.UIA3) with AppSession + BugEvidence helpers and Regression_TimelinePanel example. PyAutoGUI smoke + repro_template scripts in Python with requirements.txt. `_ci/ui-tests.yml` Forgejo Actions workflow (GitHub Actions–compatible) wiring both into the CI pipeline. `.gitignore` + per-bug folder layout under `tests/ui/bugs/BUG-XXXX/`. `tests/ui/README.md` ties it all together with the tool selection matrix. |

---

## Contents

- [About This Documentation](#about-this-documentation)
- [Document Map](#document-map)
  - [Meta-Documents](#metadocuments)
  - [Releases & Distribution](#releases-distribution)
  - [Engineering Standards](#engineering-standards)
  - [Engineering Subsystems](#engineering-subsystems)
  - [User Documentation](#user-documentation)
  - [Product & Design](#product-design)
  - [Operations](#operations)
  - [Community](#community)
  - [Marketing](#marketing)
  - [Business Development](#business-development)
  - [Help & Support](#help-support)
  - [Cross-Functional](#crossfunctional)
- [Security & Web Testing](#security-web-testing)
  - [Security](#security)
  - [Desktop UI Test Tools (C++/Qt6 Windows app)](#desktop-ui-test-tools-cqt6-windows-app)
  - [Web Design Testing (`mooned.dev` and any user-facing web)](#web-design-testing-mooneddev-and-any-userfacing-web)
  - [Standards Anchors (Security + Web)](#standards-anchors-security-web)
- [Document Versioning](#document-versioning)
- [Ownership & Review Cadence](#ownership-review-cadence)
- [Contributing](#contributing)

---
## Ownership & Review Cadence

| Owner | Review Frequency |
|---|---|
| Sarah Miller | Every release cycle |
| Mike Johnson | Monthly |
| Kirk Beka | Quarterly |
| Domain leads | On subsystem change |
| Tom Anderson | Monthly |
| Chris Taylor (PM) | Quarterly (roadmap review) |
| Amanda Clark (Operations) | Quarterly |
| Rachel Green (Community) | Monthly |
| Jason Wong (Marketing) | Per campaign |
| Kevin Brown (Business Dev) | Annually |

---

## Contents

- [About This Documentation](#about-this-documentation)
- [Document Map](#document-map)
  - [Meta-Documents](#metadocuments)
  - [Releases & Distribution](#releases-distribution)
  - [Engineering Standards](#engineering-standards)
  - [Engineering Subsystems](#engineering-subsystems)
  - [User Documentation](#user-documentation)
  - [Product & Design](#product-design)
  - [Operations](#operations)
  - [Community](#community)
  - [Marketing](#marketing)
  - [Business Development](#business-development)
  - [Help & Support](#help-support)
  - [Cross-Functional](#crossfunctional)
- [Security & Web Testing](#security-web-testing)
  - [Security](#security)
  - [Desktop UI Test Tools (C++/Qt6 Windows app)](#desktop-ui-test-tools-cqt6-windows-app)
  - [Web Design Testing (`mooned.dev` and any user-facing web)](#web-design-testing-mooneddev-and-any-userfacing-web)
  - [Standards Anchors (Security + Web)](#standards-anchors-security-web)
- [Document Versioning](#document-versioning)
- [Ownership & Review Cadence](#ownership-review-cadence)
- [Contributing](#contributing)

---
## Contributing

To update a document:
1. Edit the file in the corresponding branch
2. Update the document version in the header
3. Add an entry to the document's changelog section
4. Request review from the document owner
5. Merge to `main` after approval

---

## Contents

- [About This Documentation](#about-this-documentation)
- [Document Map](#document-map)
  - [Meta-Documents](#metadocuments)
  - [Releases & Distribution](#releases-distribution)
  - [Engineering Standards](#engineering-standards)
  - [Engineering Subsystems](#engineering-subsystems)
  - [User Documentation](#user-documentation)
  - [Product & Design](#product-design)
  - [Operations](#operations)
  - [Community](#community)
  - [Marketing](#marketing)
  - [Business Development](#business-development)
  - [Help & Support](#help-support)
  - [Cross-Functional](#crossfunctional)
- [Security & Web Testing](#security-web-testing)
  - [Security](#security)
  - [Desktop UI Test Tools (C++/Qt6 Windows app)](#desktop-ui-test-tools-cqt6-windows-app)
  - [Web Design Testing (`mooned.dev` and any user-facing web)](#web-design-testing-mooneddev-and-any-userfacing-web)
  - [Standards Anchors (Security + Web)](#standards-anchors-security-web)
- [Document Versioning](#document-versioning)
- [Ownership & Review Cadence](#ownership-review-cadence)
- [Contributing](#contributing)

---
*Grounded in ISO/IEC 12207:2017, ISO/IEC 19770-2:2015, ISO/IEC 25010:2023, ISO/IEC 14764:2022, ISO/IEC 27001:2022, ISO/IEC 27002:2022, ISO/IEC 27034-1:2011, ISO/IEC/IEEE 82079-1:2019, ISO/IEC Directives Part 2:2021, OWASP ASVS 4.0.3, OWASP Top 10 2021, NIST SP 800-218 (SSDF), CWE Top 25, Diátaxis*


---

## References

### Internal Documents

- [$title](././ACCESSIBILITY_COMPLIANCE.md)
- [$title](././audio/VST_SDK_INTEGRATION.md)
- [$title](././backend/API_CONTRACT.md)
- [$title](././BETA_PROGRAM_GUIDE.md)
- [$title](././business/ENTERPRISE_LICENSING.md)
- [$title](././codecs/FORMAT_SUPPORT_MATRIX.md)
- [$title](././community/COMMUNITY_MANAGEMENT.md)
- [$title](././effects/EFFECTS_LIBRARY.md)
- [$title](././effects/OPENFX_PLUGIN_SDK.md)
- [$title](././engineering/ARCHITECTURE_OVERVIEW.md)
- [$title](././engineering/BACKUP_DISASTER_RECOVERY.md)
- [$title](././engineering/BRANCHING_STRATEGY.md)
- [$title](././engineering/BUILD_SYSTEM.md)
- [$title](././engineering/CI_CD_PIPELINE.md)
- [$title](././engineering/TECHNICAL_STANDARDS.md)
- [$title](././engineering/TEST_STRATEGY.md)
- [$title](././graphics/RENDERING_PIPELINE.md)
- [$title](././graphics/SHADER_SPEC.md)
- [$title](././help/FAQ.md)
- [$title](././help/TROUBLESHOOTING.md)
- [$title](././marketing/LAUNCH_PLAYBOOK.md)
- [$title](././OPENFX_PLUGIN_GUIDE.md)
- [$title](././operations/INFRASTRUCTURE_OVERVIEW.md)
- [$title](././operations/ONBOARDING_GUIDE.md)
- [$title](././PERFORMANCE_BENCHMARKS.md)
- [$title](././product/PRIORITY_FRAMEWORK.md)
- [$title](././product/ROADMAP.md)
- [$title](././releases/CHANGELOG_POLICY.md)
- [$title](././releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md)
- [$title](././releases/INSTALLER_SPEC.md)
- [$title](././releases/RELEASE_CHECKLIST.md)
- [$title](././releases/SWID_TAG_SPEC.md)
- [$title](././releases/VERSIONING_POLICY.md)
- [$title](././releases/WINDOWS_STORE_SUBMISSION.md)
- [$title](././SECURITY_POLICY.md)
- [$title](././STYLE_GUIDE.md)
- [$title](././timeline/DATA_MODEL.md)
- [$title](././ui/COMPONENT_LIBRARY.md)
- [$title](././user/KEYBOARD_SHORTCUTS.md)
- [$title](././user/QUICK_START.md)
- [$title](././user/USER_GUIDE.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog
