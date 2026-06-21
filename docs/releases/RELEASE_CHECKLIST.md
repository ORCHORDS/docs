---
title: "Release Checklist"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Release Checklist

**Project:** Beetle Studio  
**Owner:** Sarah Miller (Build & Release Engineer)  
**Reviewers:** Kirk Beka (CTO), Mike Johnson (DevOps), Lisa Martinez (QA Lead)  
**ISO Standards:** ISO/IEC 12207:2017 (release process), ISO/IEC 19770-2:2015 (SWID tags), ISO/IEC 25010:2023 (quality)  
**Version:** 1.0.0  
**Last Updated:** 2026-06-21

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Step-by-step release gates for all Beetle Studio releases |
| **Diátaxis form** | How-to guide |
| **Primary audience** | Sarah Miller, Kirk Beka, Mike Johnson, Lisa Martinez |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This checklist governs every release of Beetle Studio -- from internal builds to public stable releases. Per **ISO/IEC 12207:2017**, the release process is a formal transition activity that moves software from the development environment into an operational state. Every release must pass all gates before the installer is published. No exceptions.
## Contents

- [Release Types & Cadence](#release-types-cadence)
- [Pre-Release Gates](#pre-release-gates)
  - [1. Code & Engineering](#1-code-engineering)
  - [2. Build & Artifacts](#2-build-artifacts)
  - [3. Code Signing](#3-code-signing)
  - [4. Quality Assurance](#4-quality-assurance)
  - [5. Localization & Accessibility](#5-localization-accessibility)
  - [6. Documentation](#6-documentation)
  - [7. Legal & Compliance](#7-legal-compliance)
  - [8. Windows Store (if applicable)](#8-windows-store-if-applicable)
- [Release Execution](#release-execution)
  - [Day-of Release Steps](#day-of-release-steps)
- [Post-Release Validation](#post-release-validation)
- [Hotfix Procedure](#hotfix-procedure)
- [Rollback Procedure](#rollback-procedure)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Release Types & Cadence

| Release Type | Trigger | Cadence | Approver |
|---|---|---|---|
| **Internal Build** | Any merge to `main` | Every CI run | CI (automated) |
| **Alpha** | End of development phase | Per phase milestone | Kirk Beka |
| **Beta** | Feature complete + QA pass | Monthly or per milestone | Kirk Beka |
| **Release Candidate (RC)** | Beta feedback resolved | Per release target | Kirk Beka + Chris Taylor |
| **Stable / Public** | RC sign-off | Per roadmap milestone | Kirk Beka + Mooned Dev |

---

## Pre-Release Gates

Complete all items below before creating a release tag.

### 1. Code & Engineering

- [ ] All planned features for this release are merged to `main`
- [ ] No open critical or high-severity bugs tagged for this release
- [ ] All PRs for this release have at least one approval from a domain lead
- [ ] `CHANGELOG.md` updated with all changes since last release (see [`CHANGELOG_POLICY.md`](./CHANGELOG_POLICY.md))
- [ ] Public API / SDK documentation updated if any API surface changed
- [ ] Plugin SDK documentation updated if OpenFX/plugin API changed

### 2. Build & Artifacts

- [ ] CI pipeline green on the target commit (`main` or release branch)
- [ ] Version number correctly incremented per [`VERSIONING_POLICY.md`](./VERSIONING_POLICY.md)
- [ ] SWID tag data generated with correct product ID, version, and vendor (see [`SWID_TAG_SPEC.md`](./SWID_TAG_SPEC.md))
- [ ] Installer built successfully (Inno Setup or WiX)
- [ ] All target platforms built (Windows x64 minimum; future: macOS, Linux)
- [ ] Build artifacts archived in CI (artifact retention: 90 days for internal, permanent for stable)

### 3. Code Signing

- [ ] All EXE, DLL, and installer files signed with Azure Artifact Signing
- [ ] Signing certificate is valid and not within 30 days of expiry
- [ ] SmartScreen reputation check passes (Windows Defender SmartScreen filter)
- [ ] Signed artifacts verified with `signtool verify /pa`

### 4. Quality Assurance

- [ ] Lisa Martinez (QA Lead) has signed off on the release candidate
- [ ] Automated regression test suite passes (100%)
- [ ] Smoke tests pass on clean install (first-run experience)
- [ ] Smoke tests pass on upgrade install (from previous version)
- [ ] Performance benchmarks within acceptable thresholds (see [`PERFORMANCE_BENCHMARKS.md`](../PERFORMANCE_BENCHMARKS.md))
- [ ] Memory usage under acceptable limits for target project sizes
- [ ] No new critical security vulnerabilities introduced (CVSS ≥ 7.0)

### 5. Localization & Accessibility

- [ ] UI strings extracted and sent for translation (if applicable)
- [ ] Accessibility audit passed (see [`ACCESSIBILITY_COMPLIANCE.md`](../ACCESSIBILITY_COMPLIANCE.md))
- [ ] Keyboard navigation verified for all primary workflows

### 6. Documentation

- [ ] Release notes drafted (human-readable summary for users)
- [ ] Changelog updated and reviewed by Tom Anderson
- [ ] API docs published if SDK/API changed
- [ ] User guide updated for new features
- [ ] Known issues list current

### 7. Legal & Compliance

- [ ] License file updated (current year, correct edition)
- [ ] Privacy policy URL in installer matches current policy
- [ ] Third-party licenses (FFmpeg, Qt6, etc.) correctly attributed
- [ ] Terms of service in-app are current

### 8. Windows Store (if applicable)

- [ ] Store listing assets updated (screenshots, description, keywords)
- [ ] Store submission package built per [`WINDOWS_STORE_SUBMISSION.md`](./WINDOWS_STORE_SUBMISSION.md)
- [ ] Age rating verification completed
- [ ] In-app purchase integration tested in sandbox
- [ ] Privacy manifest uploaded

---

## Release Execution

### Day-of Release Steps

Sarah Miller executes the following:

1. **Create git tag** on the approved commit:
   ```
   git tag -a vX.Y.Z -m "Release vX.Y.Z: <short summary>"
   git push origin vX.Y.Z
   ```

2. **Trigger CI release pipeline** — Forgejo Actions auto-builds on `v*` tag push

3. **Verify build artifacts** — confirm all platform builds exist in CI artifacts

4. **Sign all artifacts** — run signing job against all outputs

5. **Verify signatures** — `signtool verify /pa /v` on all outputs

6. **Run smoke tests** on the signed installer (clean + upgrade)

7. **Upload to distribution channel:**
   - Stable: website download + Windows Store
   - Beta: direct download link + beta program page
   - RC: internal distribution only

8. **Publish release notes** to the website and in-app

9. **Update changelog** on the Forgejo Releases page

10. **Notify team** — post to #releases Slack channel with version, download links, known issues

---

## Post-Release Validation

| Check | Window | Owner |
|---|---|---|
| Installation rate monitoring | 24 hours | Sarah Miller |
| Crash rate monitoring | 24 hours | Lisa Martinez |
| SmartScreen reputation check | 48 hours | Sarah Miller |
| Store submission status (if applicable) | 48 hours | Sarah Miller |
| User feedback triage | 48 hours | Rachel Green |
| Hotfix standby | 48 hours | Kirk Beka |

---

## Hotfix Procedure

For critical bugs in a stable release:

1. **Create hotfix branch:** `hotfix/<description>` from the release tag
2. **Apply fix + test** — Lisa Martinez validates
3. **Version bump:** increment PATCH (e.g., `2.3.1` → `2.3.2`)
4. **Tag and build** — same process as stable release, accelerated timeline
5. **Release notes** — note this is a hotfix for `[Critical Bug]`
6. **Communicate** — notify users via in-app update notification

---

## Rollback Procedure

If a release causes critical issues within 48 hours:

1. **Assess severity** — determine if rollback is necessary
2. **Communicate** — post to website and social media; disable distribution link
3. **Revert CI artifact** — remove from download page and CI artifacts
4. **Tag removal** — remove the broken tag from git (if not yet publicly distributed)
5. **Begin hotfix** — follow hotfix procedure above
6. **Post-mortem** — document root cause; update release checklist if gaps found

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial checklist — aligned with ISO/IEC 12207:2017 release process |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Transition Process), ISO/IEC 19770-2:2015, ISO/IEC 25010:2023*



---

## References

### Internal Documents

- [$title](./../ACCESSIBILITY_COMPLIANCE.md)
- [$title](./../PERFORMANCE_BENCHMARKS.md)
- [$title](././CHANGELOG_POLICY.md)
- [$title](././SWID_TAG_SPEC.md)
- [$title](././WINDOWS_STORE_SUBMISSION.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Sarah Miller | Initial version |
| 1.0.1 | June 2026 | Sarah Miller | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** After every release
- **Reviewer:** Sarah Miller (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type