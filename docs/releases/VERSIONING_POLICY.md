# Software Versioning & Progression — Team Reference Guide

**Project:** Beetle Studio  
**Owner:** Sarah Miller (Build & Release Engineer) — primary; Mike Johnson (DevOps) — CI integration  
**ISO Standards:** ISO/IEC 12207:2017 (lifecycle processes), ISO/IEC 19770-2:2015 (software identification), ISO/IEC 25010:2023 (quality model)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Semantic Versioning scheme, lifecycle stages, and branching model |
| **Diátaxis form** | Reference |
| **Primary audience** | All engineers, release engineers, technical writers |
| **Secondary audience** | Future maintainers and reviewers of this document |

---

## Overview

Version numbers aren't just labels -- they communicate *meaning*. When a user sees `v2.3.1`, they should immediately know the product is mature, what changed since the last version, and whether it's a feature release or a bug-fix patch. This document defines the SemVer scheme Beetle Studio follows.

## Contents

- [Why This Matters](#why-this-matters)
- [ISO Standards That Inform Our Approach](#iso-standards-that-inform-our-approach)
  - [ISO/IEC 12207:2017 — Software Life Cycle Processes](#isoiec-122072017-software-life-cycle-processes)
  - [ISO/IEC 19770-2:2015 — IT Asset Management (SWID Tags)](#isoiec-19770-22015-it-asset-management-swid-tags)
  - [ISO/IEC 25010:2023 — Software Product Quality Model](#isoiec-250102023-software-product-quality-model)
- [Our Versioning Scheme: Semantic Versioning 2.0.0](#our-versioning-scheme-semantic-versioning-200)
  - [Format](#format)
  - [When to Increment Each Part](#when-to-increment-each-part)
  - [Golden Rules](#golden-rules)
- [How a Version Progresses — The Lifecycle](#how-a-version-progresses-the-lifecycle)
  - [Detailed Stage Definitions](#detailed-stage-definitions)
- [Branch & Release Model](#branch-release-model)
  - [Rules](#rules)
- [What Ships With Each Release](#what-ships-with-each-release)
- [Versioning in Practice — Examples](#versioning-in-practice-examples)
- [Quick Reference Card](#quick-reference-card)
- [Related Documents](#related-documents)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

## Why This Matters

When a user sees `v2.3.1`, the version should immediately communicate:
- This is a mature product (major version >= 1)
- It gained new backward-compatible features since `v2.x`
- It's a bug-fix patch, not a feature release

That semantic clarity is what ISO standards like **Semantic Versioning (SemVer)** and **ISO/IEC 19770** are built around. We follow these so our dependencies, CI/CD pipeline, and release notes all speak the same language.

---

## ISO Standards That Inform Our Approach

### ISO/IEC 12207:2017 — Software Life Cycle Processes

The foundational standard for how software progresses through its lifecycle. Key concepts we adopt:

| Concept | What It Means | How We Use It |
|---|---|---|
| **Configuration Item** | Any artifact that gets tracked (source, docs, build output) | Every release artifact is a CI with a version tag |
| **Baseline** | A stable snapshot at a lifecycle milestone | `main` branch = our baseline after each release |
| **Change Control** | Formal process for approving modifications | PR reviews + release checklist gate every publish |

### ISO/IEC 19770-2:2015 — IT Asset Management (SWID Tags)

Particularly **ISO/IEC 19770-2** (Software Identification Tag / SWID tags). This standard defines how software identifies itself to enterprise IT asset management systems. When Beetle Studio ships:
- SWID tag data is embedded in our installer metadata
- Version info is parseable by enterprise IT tools (Intune, SCCM, etc.)
- This is required for Windows Store and enterprise distribution

See [`releases/SWID_TAG_SPEC.md`](./releases/SWID_TAG_SPEC.md) for the full specification.

### ISO/IEC 25010:2023 — Software Product Quality Model

Version quality is part of our overall product quality posture. Per **ISO/IEC 25010:2023**, we treat version releases as a mechanism to deliver:
- **Functional Suitability** — new features ship in MINOR releases
- **Reliability** — bug fixes ship in PATCH releases
- **Compatibility** — we maintain backward compatibility within MAJOR versions
- **Maintainability** — clean versioning enables easier regression management

---

## Our Versioning Scheme: Semantic Versioning 2.0.0

We follow [SemVer 2.0.0](https://semver.org/) — the industry-standard model that aligns with ISO asset management principles.

### Format

```
MAJOR.MINOR.PATCH[-prerelease][+build]
```

**Examples:** `1.0.0` · `2.3.1` · `3.0.0-alpha.1` · `2.4.0+20250619`

### When to Increment Each Part

| Increment | Trigger | Examples |
|---|---|---|
| **MAJOR** (`X.0.0`) | Breaking change to the public API, SDK contract, or file format | Dropping legacy codec support; removing a plugin API method |
| **MINOR** (`x.Y.0`) | New backward-compatible feature | New timeline track type; added FFmpeg filter; new export preset |
| **PATCH** (`x.y.Z`) | Backward-compatible bug fix | Fix timeline seek glitch; patch memory leak in playback; hotfix encoder crash |

### Golden Rules

1. **Once released, a version never changes.** If you find a bug in `2.3.1`, you ship `2.3.2` — not a stealth fix in the same build.
2. **MAJOR = 0 is pre-stable.** During initial development (`0.y.z`), anything can break. We won't ship our first `1.0.0` until we're production-ready.
3. **Pre-release labels for internal/beta builds.** `2.4.0-beta.1` is explicitly unstable — users opt in at their own risk.
4. **Build metadata (`+sha`) for CI artifacts.** `2.3.1+abc1234` tells you exactly which commit produced the binary.

---

## How a Version Progresses — The Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│  0.y.z  ─── Initial Development ──── Not stable        │
└──────────────────────┬──────────────────────────────────┘
                       │ First public beta / tech preview
                       ▼
┌─────────────────────────────────────────────────────────┐
│  1.0.0-alpha/beta  ─── API Locked, Testing ─── Stable? │
└──────────────────────┬──────────────────────────────────┘
                       │ Release candidate passes QA
                       ▼
┌─────────────────────────────────────────────────────────┐
│  1.0.0  ─── First Stable Release ─── Production Use   │
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ PATCH     │  │ MINOR    │  │ MAJOR    │
   │ Bug fixes │  │ New feat │  │ Breaking │
   │ +0.0.1    │  │ +0.1.0   │  │ +1.0.0   │
   └──────────┘  └──────────┘  └──────────┘
```

### Detailed Stage Definitions

#### 1. `0.y.z` — Pre-release Development
- Active development, no public API stability guarantee
- Version starts at `0.1.0`, increments MINOR with each meaningful addition
- **Team:** Internal builds only, no external distribution

#### 2. `1.0.0-alpha/beta` — Feature Freeze & QA
- Public API is locked (no more breaking changes without major bump)
- Focus shifts to stability, bug fixes, documentation
- **Team:** Closed beta testers, gathering feedback

#### 3. `1.0.0` — Stable Release
- Ready for production use
- **Team:** Tagged release on `main`, signed installer built, release notes published

#### 4. `x.y.z` — Maintenance Loop
- `PATCH` for every confirmed bug
- `MINOR` for approved feature additions (planned per sprint)
- `MAJOR` only for architecturally breaking decisions (announced well in advance)

---

## Branch & Release Model

```
main ──────────────────── (always releasable)
 │          │      │      │
 │          │      │      ▼
 │          │      │    v2.4.0  ← tag + CI build + publish
 │          │      │
 │          │      ▼
 │          │    v2.3.2  ← patch hotfix tag
 │          │
 │          ▼
 │        v2.3.0  ← feature release tag
 │
 ▼
v2.2.0  ← previous stable release tag
```

### Rules
- **`main`** is always buildable and releasable
- Every merge to `main` that changes the product **must** increment version
- Version bump in same PR as the feature/fix — no separate "version bump PRs"
- Hotfix branches: `hotfix/<description>` → PR → squash merge to `main` → tag immediately

See [`engineering/BRANCHING_STRATEGY.md`](./engineering/BRANCHING_STRATEGY.md) for the full branching model.

---

## What Ships With Each Release

Per ISO/IEC 19770-2, each release should carry:

| Artifact | Required | Notes |
|---|---|---|
| **Installer / binary** | ✅ | Signed, reproducible build |
| **SWID tag data** | ✅ | Product name, unique product ID, version, vendor |
| **Changelog** | ✅ | Every change since last release (see [`releases/CHANGELOG_POLICY.md`](./releases/CHANGELOG_POLICY.md)) |
| **Release notes** | ✅ | Human-readable summary for users |
| **API docs** | ✅ | If SDK/public API changed |
| **License file** | ✅ | Current year, correct edition |

---

## Versioning in Practice — Examples

| Scenario | Old Version | New Version | Reason |
|---|---|---|---|
| Fixed timeline playhead jump bug | `2.3.1` | `2.3.2` | Bug fix, no API change |
| Added GPU-accelerated color wheels | `2.3.1` | `2.4.0` | New feature, backward compatible |
| Removed legacy plugin API method | `2.3.1` | `3.0.0` | Breaking API change |
| Internal test build | `2.4.0` | `2.4.0-alpha.1` | Pre-release, not for distribution |
| CI artifact from commit `abc123` | `2.3.1` | `2.3.1+abc1234` | Build metadata |

---

## Quick Reference Card

> **New feature?** → `MINOR +1`, reset PATCH to 0  
> **Bug fix only?** → `PATCH +1`  
> **Breaking anything?** → `MAJOR +1`, reset MINOR/PATCH to 0  
> **Internal build?** → add `-alpha.N` or `-beta.N`  
> **CI artifact?** → add `+githash`  
> **Released version stays frozen** — never edit a tag

---

## Related Documents

- Release Checklist — [`releases/RELEASE_CHECKLIST.md`](./releases/RELEASE_CHECKLIST.md)
- Changelog Policy — [`releases/CHANGELOG_POLICY.md`](./releases/CHANGELOG_POLICY.md)
- SWID Tag Specification — [`releases/SWID_TAG_SPEC.md`](./releases/SWID_TAG_SPEC.md)
- CI/CD Pipeline — [`engineering/CI_CD_PIPELINE.md`](./engineering/CI_CD_PIPELINE.md)
- Branching Strategy — [`engineering/BRANCHING_STRATEGY.md`](./engineering/BRANCHING_STRATEGY.md)

---

*Grounded in: ISO/IEC 12207:2017, ISO/IEC 19770-2:2015, ISO/IEC 25010:2023, Semantic Versioning 2.0.0*


---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Unknown owner | Initial version |
| 1.0.1 | June 2026 | Unknown owner | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On SemVer major revision
- **Reviewer:** Sarah Miller (Build & Release Engineer) — primary
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type