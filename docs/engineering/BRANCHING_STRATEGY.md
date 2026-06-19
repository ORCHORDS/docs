# Branching Strategy

**Project:** Beetle Studio  
**Owner:** Mike Johnson (DevOps Lead)  
**Reviewers:** Kirk Beka (CTO), all engineering leads  
**ISO Standards:** ISO/IEC 12207:2017 (configuration management), ISO/IEC 25010:2023 (maintainability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Git branching model, merge policy, and hotfix flow |
| **Diátaxis form** | Reference |
| **Primary audience** | All engineers |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines Beetle Studio's Git branching model. Per **ISO/IEC 12207:2017**, configuration management -- including branch control -- is a required process that ensures the integrity of configuration items throughout the software lifecycle.
## Contents

- [Branch Types](#branch-types)
  - [1. `main`](#1-main)
  - [2. `feature/<description>`](#2-featuredescription)
  - [3. `release/<version>`](#3-releaseversion)
  - [4. `hotfix/<description>`](#4-hotfixdescription)
- [Branch Diagram](#branch-diagram)
- [Workflow](#workflow)
  - [Feature Development](#feature-development)
  - [Release Process](#release-process)
  - [Hotfix Process](#hotfix-process)
- [Commit Message Convention](#commit-message-convention)
- [Merge Rules](#merge-rules)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Branch Types

### 1. `main`

| Property | Value |
|---|---|
| **Purpose** | Primary integration branch — always buildable and releasable |
| **Protection** | Require PR + 1 approval from domain lead + CI green |
| **Direct pushes** | ❌ Never |
| **Merge type** | Squash merge from feature/hotfix branches; merge commit from release branches |

### 2. `feature/<description>`

| Property | Value |
|---|---|
| **Purpose** | Develop a single feature or improvement |
| **Lifetime** | Days to weeks; must not block `main` for > 1 sprint |
| **Branch from** | `main` |
| **Merge to** | `main` (squash) |
| **Naming** | `feature/<ticket-id>-<short-description>` |

**Example:** `feature/1234-multi-camera-tracks`

### 3. `release/<version>`

| Property | Value |
|---|---|
| **Purpose** | Stabilize a specific release; freeze feature changes |
| **Lifetime** | 1–3 weeks per release cycle |
| **Branch from** | `main` at release commit |
| **Merge to** | `main` (merge commit) + tag created |
| **Naming** | `release/v<MAJOR>.<MINOR>.x` |

**Example:** `release/v2.3.x`

### 4. `hotfix/<description>`

| Property | Value |
|---|---|
| **Purpose** | Emergency fix for a critical bug in a stable release |
| **Lifetime** | Hours to days; must be resolved quickly |
| **Branch from** | `main` (current stable) or release tag |
| **Merge to** | `main` (squash) + release branch if applicable |
| **Naming** | `hotfix/<ticket-id>-<short-description>` |

**Example:** `hotfix/2345-crash-on-project-load`

---

## Branch Diagram

```
                              ┌──────────────┐
                              │  release/    │
                         ┌───►│  v2.3.x     │◄──────┐
                         │    └──────┬──────┘       │
                         │           │ tag v2.3.0  │
                         │           ▼              │
                         │    ┌──────────────┐      │
                         │    │    main      │      │
┌──────────────┐         │    │              │      │
│  feature/    │         │    │              │      │
│  1234-feat   │─────────┼────┤              │      │
└──────────────┘         │    │              │      │
                         │    │              │──────┘
                         │    │              │
                         │    └──────┬──────┘
                         │           │
                         │           ▼
                         │    ┌──────────────┐
                         └───►│  main       │ (HEAD)
                              └──────────────┘
                                   ▲
                         ┌─────────┴─────────┐
                         │  hotfix/        │
                         │  2345-fix       │
                         └─────────────────┘
```

---

## Workflow

### Feature Development

1. **Create branch:** `git checkout -b feature/1234-new-export-format`
2. **Develop:** Commits with conventional commit messages
3. **Keep updated:** Rebase onto `main` regularly (daily for long features)
4. **PR when ready:** Open PR against `main`
5. **Review:** Domain lead reviews + CI passes
6. **Merge:** Squash merge → commits collapsed into one meaningful commit on `main`
7. **Delete:** Feature branch deleted after merge

### Release Process

1. **Create release branch:** When `main` is at feature-complete state for a release
   ```bash
   git checkout -b release/v2.3.x main
   ```
2. **Freeze:** No new features; only bug fixes and release work
3. **QA:** Lisa Martinez (QA Lead) tests the release branch
4. **Fix in release:** Bug fixes land on `release/v2.3.x` and are merged to `main`
5. **Tag:** When ready, tag the release:
   ```bash
   git tag v2.3.0
   git push origin v2.3.0
   ```
6. **Merge back:** Merge `release/v2.3.x` → `main` (merge commit, not squash)
7. **Delete:** Release branch deleted after merge

### Hotfix Process

1. **Create hotfix branch** from the release tag or current `main`:
   ```bash
   git checkout -b hotfix/2345-crash-fix v2.3.0
   # or from main
   git checkout -b hotfix/2345-crash-fix main
   ```
2. **Apply fix** — same PR process as feature
3. **Version bump** — increment PATCH in the same PR
4. **Tag and build** — `git tag v2.3.1` → triggers release workflow
5. **Notify** — post to #releases Slack with hotfix details

---

## Commit Message Convention

All commits must use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer: Tracking: #<issue>]
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `chore`, `security`

---

## Merge Rules

| Branch | Requires | CI | Direct Push |
|---|---|---|---|
| `main` | 1 domain lead approval + PR | ✅ Green | ❌ Never |
| `feature/*` | 1 approval | ✅ Green | Allowed |
| `release/*` | Release manager approval | ✅ Green | ❌ Never |
| `hotfix/*` | 1 approval (fast-track OK) | ✅ Green | Emergency only |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial strategy — aligned with ISO/IEC 12207:2017 §6.3 (Configuration Management) |

---

*Grounded in: ISO/IEC 12207:2017 §6.3 (Configuration Management Process), ISO/IEC 25010:2023 (Maintainability)*


---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Unknown owner | Initial version |
| 1.0.1 | June 2026 | Unknown owner | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Mike Johnson (DevOps Lead)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type