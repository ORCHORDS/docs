---
title: "CI/CD Pipeline"
version: "2.0.0"
last-updated: "2026-06-21"
owner: "mike.johnson (DevOps Lead)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023 (Reliability)", "ISO/IEC 19770-2:2015"]
---

# CI/CD Pipeline

**Project:** Beetle Studio
**Owner:** Mike Johnson (DevOps Lead) — pipeline + runners; Sarah Miller (Build & Release Engineer) — release artifact + signing
**Reviewers:** Kirk Beka (CTO), Sarah Miller
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Development & transition processes), ISO/IEC 25010:2023 (Reliability), ISO/IEC 19770-2:2015 (SWID)
**Version:** 2.0.0 — corrected 2026-06-21 (see Change Log)
**Last Updated:** 2026-06-21

> **2026-06-21 correction:** v1.0.0 of this document described a pipeline that did not match the actual Forgejo Actions workflows in `beetle-studio/beetle-studio@.forgejo/workflows/`. v2.0.0 has been rewritten to reflect the **current** 8-workflow state. Earlier references to SonarQube, Trivy, FOSSA, Checkov, Dependabot, Azure Artifact Signing, and the GitHub Release pipeline have been removed — those tools are **not configured** in the project and should not be cited as in-use.

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | The 8 Forgejo Actions workflows in `.forgejo/workflows/`, the build matrix, the runner environment, and the rollback procedure |
| **Diátaxis form** | Reference |
| **Primary audience** | Mike Johnson, Sarah Miller, all engineers |
| **Secondary audience** | Release engineers; security auditors; future maintainers |

---

## Overview

Beetle Studio uses **Forgejo Actions** for all CI/CD. Workflows are written in GitHub Actions YAML syntax (Forgejo Actions is *familiar* but not *compatible* with GitHub Actions — see [Workflows README](./workflows/README.md) for the differences). All workflows live in `.forgejo/workflows/` of the `beetle-studio/beetle-studio` repository. The current pipeline has 8 workflows (see [Workflows Index](./workflows/README.md) for per-workflow documentation).

## Contents

- [Pipeline Architecture](#pipeline-architecture)
- [Workflows](#workflows)
- [Build Artifacts](#build-artifacts)
- [Runners](#runners)
- [Quality Gates](#quality-gates)
- [Rollback Procedure](#rollback-procedure)
- [Security Scans in CI/CD](#security-scans-in-cicd)
- [References](#references)
- [Change Log](#change-log)
- [Review Cadence](#review-cadence)

---

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       FORGEJO ACTIONS                            │
│                                                                  │
│  ┌──────────────┐                                               │
│  │  Pull Request │  ← branch-naming + pr-build + security-scan  │
│  │              │  ← benchmarks (Engine/**) + auto-merge-md     │
│  └──────┬───────┘                                               │
│         │ merge (human)                                          │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │   Push main   │  ← main-build (Windows smoke + lint)         │
│  └──────┬───────┘                                               │
│         │ tag v*.*.*                                             │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │  Release Tag │  ← release-build (Windows, /DNDEBUG, copy    │
│  │              │     to artifacts/)                            │
│  └──────┬───────┘                                               │
│         │ manual: signtool + upload                             │
│         ▼                                                        │
│  ┌──────────────┐                                               │
│  │  Published    │  ← SWID tag + SBOM generated manually        │
│  └──────────────┘                                               │
└──────────────────────────────────────────────────────────────────┘
```

> **Note:** Issue auto-assignment (`auto-assign.yml`) is parallel to the pipeline above and operates on `issues: opened` events, not on PRs.

## Workflows

For per-workflow detail (triggers, jobs, configuration, troubleshooting), see the [Workflows Index](./workflows/README.md). Summary:

| # | Workflow | Trigger | Purpose | Doc |
|---|---|---|---|---|
| 1 | `auto-assign.yml` | `issues: opened` | Auto-assign issues by role keyword | [AUTO_ASSIGN.md](./workflows/AUTO_ASSIGN.md) |
| 2 | `auto-merge-md.yml` | PR opened/sync/reopen | Auto-merge MD-only PRs | [AUTO_MERGE_MD.md](./workflows/AUTO_MERGE_MD.md) |
| 3 | `benchmarks.yml` | PR to `main` on `benchmarks/**` or `src/Engine/**` | Engine benchmarks | [BENCHMARKS.md](./workflows/BENCHMARKS.md) |
| 4 | `branch-naming.yml` | PR opened/sync/reopen (non-docs) | Branch name policy | [BRANCH_NAMING.md](./workflows/BRANCH_NAMING.md) |
| 5 | `main-build.yml` | push to `main` on source files | Smoke build + lint | [MAIN_BUILD.md](./workflows/MAIN_BUILD.md) |
| 6 | `pr-build.yml` | PR to `main`/`develop` on source | Lint + smoke compile | [PR_BUILD.md](./workflows/PR_BUILD.md) |
| 7 | `release-build.yml` | push of `v*` tag | Release build (Windows) | [RELEASE_BUILD.md](./workflows/RELEASE_BUILD.md) |
| 8 | `security-scan.yml` | PR to `main` on source/build | Gitleaks + Semgrep | [SECURITY_SCAN.md](./workflows/SECURITY_SCAN.md) |

## Build Artifacts

| Artifact | Source workflow | Format | Currently produced? |
|---|---|---|---|
| `BeetleStudio.exe` (debug) | `main-build.yml` | Portable executable | Yes — but discarded (not uploaded) |
| `BeetleStudio.exe` (release) | `release-build.yml` | Portable executable | Yes — written to `artifacts/`, not auto-uploaded |
| `artifacts/BUILD_INFO.txt` | `release-build.yml` | Plaintext with tag name | Yes |
| `BeetleStudio-Setup-vX.Y.Z.exe` | (none) | Inno Setup installer | **No** — planned; see [INSTALLER_SPEC.md](../releases/INSTALLER_SPEC.md) |
| `BeetleStudio-vX.Y.Z-portable.zip` | (none) | ZIP | **No** — manual |
| `BeetleStudio-vX.Y.Z-debug.zip` | (none) | Debug symbols | **No** — manual |
| `sbom.cdx.json` | (none) | CycloneDX 1.5 SBOM | **No** — manual; ISO/IEC 19770-2:2015 requires this for releases |
| `swidtag.xml` | (none) | ISO/IEC 19770-2 SWID | **No** — manual; see [SWID_TAG_SPEC.md](../releases/SWID_TAG_SPEC.md) |

> **Honest assessment (2026-06-21):** the pipeline today produces only `BeetleStudio.exe` and `BUILD_INFO.txt`. Every other artifact in the table is a **planned** item, not a current one. A signed installer, SBOM, and SWID tag are tracked as separate work items.

## Runners

| Pipeline | Runner label | Self-hosted? | Notes |
|---|---|---|---|
| `auto-assign.yml` | `ubuntu-latest` | **Yes** (per project convention) | Requires `host.docker.internal:3000` to reach the Forgejo API |
| `auto-merge-md.yml` | `ubuntu-latest` | **Yes** | Same network requirement |
| `benchmarks.yml` | `ubuntu-latest` | **Yes** | `g++` and `cmake` auto-installed |
| `branch-naming.yml` | `ubuntu-latest` | **Yes** | 2-minute timeout |
| `main-build.yml` (build job) | `windows-latest` | **Yes** (moon-pc) | `cmd` shell required |
| `main-build.yml` (lint job) | `ubuntu-latest` | **Yes** | `clang-format` auto-installed |
| `pr-build.yml` | `ubuntu-latest` | **Yes** | 5–8 minute timeouts |
| `release-build.yml` | `windows-latest` | **Yes** (moon-pc) | `cmd` shell required |
| `security-scan.yml` | `ubuntu-latest` | **Yes** | Gitleaks + semgrep auto-installed |

> **Per the [Forgejo Actions basic concepts](https://forgejo.org/docs/latest/user/actions/basic-concepts/), the default runner image is Debian bookworm with Node.js only.** Every other tool (`cmake`, `g++`, `clang-format`, `gitleaks`, `semgrep`, `jq`, `curl`) is installed by the step. If a tool is missing in the log, look for the `apt-get install` step; verify it is succeeding.
>
> **Host networking:** the `auto-assign` and `auto-merge-md` workflows call `http://host.docker.internal:3000/api/v1` to reach the local Forgejo. This assumes the runner is launched with Docker host networking (or `--add-host=host.docker.internal:host-gateway` on Linux DinD). On rootless Podman, the address differs.

## Quality Gates

The following gates exist on PRs to `main`:

| Gate | Tool / Workflow | Blocking? |
|---|---|---|
| Branch name matches policy | `branch-naming.yml` | **Yes — hard fail** |
| All jobs ran (no skip) | any workflow's job being skipped is treated as failure if the path filter should have matched | No (advisory in current state) |
| Lint passes | `pr-build.yml` / `main-build.yml` | No (advisory; `exit 0` at end of step) |
| Compile-check passes | `pr-build.yml` | No (advisory; 5-file limit) |
| Windows smoke build succeeds | `main-build.yml` | Yes for the post-merge `main` build; not on PRs |
| Gitleaks finds no secrets | `security-scan.yml` | No (advisory) |
| Semgrep finds no high-severity issues | `security-scan.yml` | No (advisory; uses `--config auto`) |
| Benchmark regression within tolerance | `benchmarks.yml` | No (advisory; no baseline comparison) |
| Code signed | manual | Yes for release (manual) |
| SWID tag present | manual | Yes for release (planned) |
| SBOM present | manual | Yes for release (planned) |

**Honest assessment (2026-06-21):** today, only **branch naming** is a true hard gate. Everything else is advisory. This is documented as a known gap in [VERSION_HISTORY](#change-log) and the workflow docs themselves.

## Rollback Procedure

If a release artifact (`vX.Y.Z` tag) is published and a critical regression is found:

1. **Revert the source.** Open a hotfix PR from a `hotfix/<id>-<topic>` branch. Follow the hotfix path in [`RELEASE_CHECKLIST.md`](../releases/RELEASE_CHECKLIST.md).
2. **Tag the revert.** Once merged, tag a new release (`vX.Y.Z+1` or `vX.Y.(Z+1)` per SemVer) and push the tag — `release-build.yml` will run again.
3. **Re-sign + re-upload.** Manually run `signtool sign /fd sha256 /a artifacts\BeetleStudio.exe` and re-upload the artifact to the release page.
4. **Notify.** Post a notice in the user-facing release channel (the project's actual chat tool is documented in [`COMMUNITY_MANAGEMENT.md`](../community/COMMUNITY_MANAGEMENT.md); this document does not assume Slack).
5. **Do not delete the bad tag.** Once a tag is in the wild, deleting it breaks reproducibility for users who have already downloaded. Leave it; mark the release as "yanked" in the release notes.

> **Out of scope for the workflow itself:** the rollback is a manual sequence. There is no `release-rollback.yml` workflow today. The release manager (Sarah Miller) executes these steps by hand.

## Security Scans in CI/CD

The two scanners that run today are defined in [`./workflows/SECURITY_SCAN.md`](./workflows/SECURITY_SCAN.md):

| Scanner | Workflow job | Tool | Findings go to |
|---|---|---|---|
| Secret scanner | `gitleaks` | Gitleaks v8.21.2 | Actions log only (advisory) |
| SAST | `semgrep` | Semgrep (public registry, `--config auto`) | Actions log only (advisory) |

**Planned but not yet implemented** (carry-overs from earlier pipeline proposals that were never wired up):

- **SCA for C++ deps:** vcpkg `audit` is not invoked. The project does not yet have a `vcpkg.json` declaring dependencies, so SCA has nothing to scan.
- **Container scanning:** the app is a Windows native binary, not a container. Trivy / Grype are not applicable.
- **DAST:** the app is a desktop binary, not a web service. OWASP ZAP active scan is not applicable.
- **License / copyleft check (FOSSA):** not configured.
- **IaC scan (Checkov):** no Terraform is in this repo.
- **Dependabot / Renovate:** not configured.

These are tracked as separate roadmap items; do not cite them as in-use in other documents.

### Waivers

If a security finding is accepted as risk, the waiver is logged in [`../security/WAIVERS.md`](../security/WAIVERS.md), owned by Maya Rodriguez, reviewed quarterly.

### Severity Tiers (intended, not enforced)

| Severity | Intended action | Currently enforced? |
|---|---|---|
| Critical | Block merge + page `@security-team` + incident | No (advisory) |
| High | Block merge + waiver required to override | No (advisory) |
| Medium | Warn; allow merge; open ticket | No (advisory) |
| Low | Log only | Yes (always) |

The advisory-only state is acknowledged and tracked; converting the scanners to blocking is a future work item.

## References

### Internal Documents

- [Workflows Index](./workflows/README.md) — per-workflow documentation
- [Branching Strategy](./BRANCHING_STRATEGY.md)
- [Build System](./BUILD_SYSTEM.md)
- [Test Strategy](./TEST_STRATEGY.md)
- [Security Policy](../SECURITY_POLICY.md)
- [Security Waivers](../security/WAIVERS.md)
- [Release Checklist](../releases/RELEASE_CHECKLIST.md)
- [Versioning Policy](../releases/VERSIONING_POLICY.md) — Semantic Versioning
- [SWID Tag Spec](../releases/SWID_TAG_SPEC.md) — ISO/IEC 19770-2
- [Installer Spec](../releases/INSTALLER_SPEC.md)
- [Code Signing Certificate Management](../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md)
- [Threat Model (planned)](../security/THREAT_MODEL.md)
- [Style Guide](../STYLE_GUIDE.md)

### External

- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- Forgejo Actions basic concepts — https://forgejo.org/docs/latest/user/actions/basic-concepts/
- Forgejo Actions vs GitHub Actions — https://forgejo.org/docs/latest/user/actions/github-actions/
- Semantic Versioning 2.0.0 — https://semver.org/
- ISO/IEC 12207:2017 §6.3.5 — Development process
- ISO/IEC 25010:2023 — Reliability
- ISO/IEC 19770-2:2015 — Software identification (SWID)
- CycloneDX 1.5 SBOM spec — https://cyclonedx.org/specification/overview/
- Inno Setup — https://jrsoftware.org/isinfo.php

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Development & transition processes), ISO/IEC 25010:2023 (Reliability subcharacteristic), ISO/IEC 19770-2:2015 (SWID). Workflows source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/*.yml`.*

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Mike Johnson | Initial spec — aligned with ISO/IEC 12207:2017 §6.3.5 and ISO/IEC 25010:2023 |
| 1.0.1 | June 2026 | Mike Johnson | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |
| 2.0.0 | 2026-06-21 | kirk.beka (CTO) | **Corrective rewrite** — removed references to GitHub Actions, GitHub Releases, SonarQube, Trivy, FOSSA, Checkov, Dependabot, Azure Artifact Signing, and Qt6 toolchain — none of which are configured in the actual `beetle-studio/beetle-studio@.forgejo/workflows/` files. Re-aligned with the 8 actual workflows. Per-workflow docs moved to [`./workflows/`](./workflows/). Acknowledged the advisory-only state of most scanners. |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Mike Johnson (DevOps Lead)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type
