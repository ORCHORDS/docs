# CI/CD Pipeline

**Project:** Beetle Studio  
**Owner:** Mike Johnson (DevOps Lead)  
**Reviewers:** Kirk Beka (CTO), Sarah Miller (Build Engineer)  
**ISO Standards:** ISO/IEC 12207:2017 (development & transition), ISO/IEC 25010:2023 (reliability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | GitHub Actions workflows, automation, and rollback procedures |
| **Diátaxis form** | Reference |
| **Primary audience** | Mike Johnson, Sarah Miller, all engineers |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

## Contents

- [Pipeline Architecture](#pipeline-architecture)
- [Workflows](#workflows)
  - [1. PR Build (`pr-build.yml`)](#1-pr-build-pr-buildyml)
  - [2. Main Build (`main-build.yml`)](#2-main-build-main-buildyml)
  - [3. Release Build (`release-build.yml`)](#3-release-build-release-buildyml)
- [Build Artifacts](#build-artifacts)
- [Environment](#environment)
  - [Runners](#runners)
  - [Caching](#caching)
- [Quality Gates](#quality-gates)
- [Rollback Procedure](#rollback-procedure)
- [Security Scans in CI/CD](#security-scans-in-cicd)
  - [PR Pipeline (runs on every push)](#pr-pipeline-runs-on-every-push)
  - [Nightly Pipeline (scheduled)](#nightly-pipeline-scheduled)
  - [Release Pipeline (gates before publish)](#release-pipeline-gates-before-publish)
  - [SBOM (Software Bill of Materials)](#sbom-software-bill-of-materials)
  - [Security Gate Failures](#security-gate-failures)
  - [Tool Configuration Files](#tool-configuration-files)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        GITHUB ACTIONS                            │
│                                                                  │
│  ┌──────────────┐                                               │
│  │  Pull Request │  ← Every PR → compile + test + lint          │
│  └──────┬───────┘                                               │
│         │ merge                                                  │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │   Push main   │  ← Compile + test + artifacts                │
│  └──────┬───────┘                                               │
│         │ tag v*.*.*                                             │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │  Release Tag │  ← Full release build + sign + publish        │
│  └──────────────┘                                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## Workflows

### 1. PR Build (`pr-build.yml`)

**Trigger:** Every pull request to `main` or `release/*`  
**Purpose:** Validate code before merge

| Stage | Steps | Timeout |
|---|---|---|
| Configure | CMake preset `ci` | 5 min |
| Build | All targets (Debug) | 15 min |
| Unit Tests | `tests` target | 5 min |
| Lint | C++ linter + CMake lint | 3 min |
| Report | Post results to PR | — |

**Required checks to merge:**
- ✅ CMake configure success
- ✅ Build success (all targets)
- ✅ All unit tests pass
- ⚠️ Lint warnings (must be addressed; errors block merge)

### 2. Main Build (`main-build.yml`)

**Trigger:** Every push to `main`  
**Purpose:** Continuous integration — ensure `main` is always releasable

| Stage | Steps | Timeout |
|---|---|---|
| Configure | CMake preset `release` | 5 min |
| Build | All targets (Release) | 20 min |
| Tests | Unit + integration tests | 10 min |
| Artifacts | Package installer + portable build | 10 min |
| Archive | Upload to CI artifacts | 5 min |

**Artifacts retained:** 90 days  
**Notification:** Failure → #ci-alerts Slack channel

### 3. Release Build (`release-build.yml`)

**Trigger:** Push of a git tag matching `v[0-9]+.[0-9]+.[0-9]+`  
**Purpose:** Official release build

| Stage | Steps | Owner |
|---|---|---|
| Validate tag | Verify version matches changelog | CI |
| Configure | CMake preset `release` | CI |
| Build | Full release build | CI |
| Sign | Azure Artifact Signing all outputs | Sarah Miller |
| Verify signatures | `signtool verify` on all artifacts | CI |
| Generate SWID tag | `generate_swid_tag.py` | CI |
| Smoke test | Automated install + launch test | CI |
| Publish | Upload to website + Store (if applicable) | Sarah Miller |
| GitHub Release | Create release + attach artifacts | CI |

---

## Build Artifacts

| Artifact | Source | Format |
|---|---|---|
| `BeetleStudio-Setup-vX.Y.Z.exe` | Release build | Signed Inno Setup installer |
| `BeetleStudio-vX.Y.Z-portable.zip` | Release build | Portable (no install) |
| `BeetleStudio-vX.Y.Z-debug.zip` | Main build | Debug symbols + logs |
| `build-logs.zip` | All builds | CMake + compiler output |

---

## Environment

### Runners

| Pipeline | Runner | Specification |
|---|---|---|
| PR Build | `windows-latest` | Windows Server 2022, 4-core, 16 GB RAM |
| Main Build | `windows-latest` | Windows Server 2022, 8-core, 32 GB RAM |
| Release Build | `windows-latest` | Windows Server 2022, 8-core, 32 GB RAM |

### Caching

| Cache Target | Strategy | TTL |
|---|---|---|
| CMake cache | Keyed on `CMakeLists.txt` + preset | 1 week |
| vcpkg artifacts | Keyed on `vcpkg.json` hash | 1 week |
| Qt6 framework | Pre-built artifact (internal cache) | 1 week |
| Compiler cache | MSVC PDB cache | Per build |

---

## Quality Gates

All gates must pass before the release workflow proceeds:

| Gate | Metric | Threshold |
|---|---|---|
| Build | Exit code | 0 (success) |
| Unit tests | Pass rate | 100% |
| Integration tests | Pass rate | 100% |
| Code signing | Signature verified | ✅ Valid |
| Smoke test | Application launches | ✅ Launched |
| Crash test | Crash in first 60s | 0 crashes |

---

## Rollback Procedure

If CI release artifacts cause critical issues:

1. **Remove the broken tag:** `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`
2. **Remove CI artifacts:** GitHub Actions → Artifacts → Delete
3. **Notify team:** Post to #releases Slack
4. **Create hotfix:** Follow [`releases/RELEASE_CHECKLIST.md`](../releases/RELEASE_CHECKLIST.md) hotfix procedure

---

## Security Scans in CI/CD

Every PR and every nightly build runs the security checks defined in [`SECURITY_POLICY.md`](../SECURITY_POLICY.md#security-checks--verification). This section documents which checks run where and what the gates are.

### PR Pipeline (runs on every push)

| Step | Tool | Gate | Standard |
|---|---|---|---|
| 1. Secret scan | Gitleaks | Must pass (no secrets) | ASVS V2.10, ISO 27002 A.8.24 |
| 2. SAST | Semgrep (CWE + OWASP rulesets) | No new high/critical issues | CWE Top 25, ASVS V5 |
| 3. SCA — backend | npm-audit + pip-audit | No high/critical CVEs | ASVS V14, ISO 27002 A.8.8 |
| 4. SCA — C++ deps | vcpkg audit | No high/critical CVEs | ASVS V14 |
| 5. License check | FOSSA | No copyleft contamination in proprietary code | ISO 27002 A.5.31 |
| 6. IaC scan (if Terraform changed) | Checkov | No high/critical misconfigurations | ISO 27002 A.8.9 |

### Nightly Pipeline (scheduled)

| Step | Tool | Purpose | Standard |
|---|---|---|---|
| 1. Full SAST (deep rules) | SonarQube | Catch what PR scan missed | CWE Top 25 |
| 2. DAST on staging web | OWASP ZAP active scan | Runtime web vulns | ASVS V13, OWASP Top 10 |
| 3. Container scan (deployed images) | Trivy | OS + library CVEs | ISO 27002 A.8.9 |
| 4. Firebase rules test suite | Emulator Suite | Rules regressions | ASVS V2, V4 |
| 5. Dependency freshness | Dependabot digest | Outdated packages | ISO 27002 A.8.8 |

### Release Pipeline (gates before publish)

| Step | Tool | Gate |
|---|---|---|
| 1. All PR pipeline checks | (as above) | All must pass |
| 2. All nightly checks since last release | (as above) | All must pass or have accepted waivers |
| 3. SBOM generation | CycloneDX | Generated and signed |
| 4. Code signing | Azure Artifact Signing | Binary signed |
| 5. Vulnerability attestation | VEX (Vulnerability Exploitability eXchange) | Generated |

### SBOM (Software Bill of Materials)

Per **ISO/IEC 19770-2:2015** + U.S. Executive Order 14028:

- Generated automatically on every release (`sbom.cdx.json`)
- Format: **CycloneDX 1.5**
- Attached to GitHub Release
- Published to internal artifact registry for downstream consumers

### Security Gate Failures

| Severity | Action |
|---|---|
| **Critical** | Block merge immediately. Notify `@security-team` in Slack. |
| **High** | Block merge. Reviewer can override with written justification (creates a tracked waiver). |
| **Medium** | Warn, allow merge. Open ticket automatically. |
| **Low** | Log only, no action. |

Waivers are tracked in `docs/security/WAIVERS.md` (managed by `Maya Rodriguez (Backend)`) and reviewed quarterly.

### Tool Configuration Files

| Tool | Config location |
|---|---|
| Semgrep | `.semgrep.yml` + `semgrep-rules/` |
| Gitleaks | `.gitleaks.toml` |
| SonarQube | `sonar-project.properties` |
| Checkov | `.checkov.yaml` |
| Dependabot | `.github/dependabot.yml` |
| Firebase rules tests | `tests/rules/` |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 12207:2017 §6.3 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.3 (Development Process), ISO/IEC 25010:2023 (Reliability subcharacteristic)*



---

## References

### Internal Documents

- [$title](./../releases/RELEASE_CHECKLIST.md)
- [$title](./../SECURITY_POLICY.md)

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