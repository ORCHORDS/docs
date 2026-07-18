---
title: "Changelog Policy"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Changelog Policy

**Project:** Mr.Orchords  
**Owner:** Mr.Orchords (Build & Release Engineer)  
**Reviewers:** Mr.Orchords (CTO), Mr.Orchords (Technical Writer)  
**ISO Standards:** ISO/IEC 12207:2017 (transition), ISO/IEC 25010:2023 (functional suitability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Keep a Changelog format, release notes template, and version codenames |
| **Diátaxis form** | Reference |
| **Primary audience** | Mr.Orchords, Mr.Orchords, Mr.Orchords, Mr.Orchords |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This policy defines how Mr.Orchords's changelog is formatted and maintained. We follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/). Per **ISO/IEC 12207:2017 §6.4**, the transition process includes communicating changes to users -- a clear changelog is a required communication artifact.
## Contents

- [What Goes in the Changelog](#what-goes-in-the-changelog)
  - [What Gets Logged](#what-gets-logged)
  - [What Does NOT Get Logged](#what-does-not-get-logged)
- [Format](#format)
  - [Structure](#structure)
  - [Change Categories](#change-categories)
  - [Version Headers](#version-headers)
  - [Example Entry](#example-entry)
- [Release Notes Template](#release-notes-template)
  - [Patch Release (X.Y.Z)](#patch-release-xyz)
  - [Minor Release (X.Y.0)](#minor-release-xy0)
  - [Major Release (X.0.0)](#major-release-x00)
- [Version Codenames](#version-codenames)
- [The Changelog Process](#the-changelog-process)
  - [For Feature PRs](#for-feature-prs)
  - [For Bug Fix PRs](#for-bug-fix-prs)
  - [When Cutting a Release](#when-cutting-a-release)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## What Goes in the Changelog

### What Gets Logged

- **New features** — anything users can do that they couldn't before
- **Improvements** — meaningful performance or quality gains
- **Bug fixes** — anything that was broken and now works
- **Breaking changes** — anything that requires user action after upgrade
- **Security fixes** — vulnerabilities patched
- **Deprecations** — features or APIs that will be removed in a future version
- **Known issues** — bugs we're aware of but haven't fixed yet

### What Does NOT Get Logged

- Refactoring with no user-visible effect
- Documentation-only changes
- CI/CD pipeline changes
- Test additions/changes
- Internal developer tooling

---

## Format

### Structure

```
CHANGELOG.md
├── Unreleased (changes since last release)
│   ├── Added
│   ├── Changed
│   ├── Deprecated
│   ├── Removed
│   ├── Fixed
│   └── Security
├── [2.3.1] — 2026-06-15
│   ├── Fixed
│   └── Changed
├── [2.3.0] — 2026-06-10
│   ├── Added
│   └── Fixed
└── [2.2.0] — 2026-05-28
    ├── Added
    └── Changed
```

### Change Categories

| Category | When to Use | Example |
|---|---|---|
| **Added** | New user-visible functionality | "GPU-accelerated color wheels for real-time color grading" |
| **Changed** | Changes to existing functionality | "Timeline zoom now uses `Ctrl+Scroll` instead of `Alt+Scroll`" |
| **Deprecated** | Features to be removed in a future version | "`File > Export > Legacy Format` is deprecated; use H.264 instead" |
| **Removed** | Features removed in this version | "Support for Windows 10 version 1809" |
| **Fixed** | Bug fixes | "Fixed crash when trimming 4K ProRes clip on integrated GPU" |
| **Security** | Vulnerability fixes | "Fixed path traversal vulnerability in project file loading (CVE-2026-XXXX)" |

### Version Headers

| Header Format | When |
|---|---|
| `[X.Y.Z] — YYYY-MM-DD` | Stable release |
| `[X.Y.Z-beta.N] — YYYY-MM-DD` | Beta release |
| `Unreleased` | Work in progress |

### Example Entry

```markdown
## [2.3.1] — 2026-06-15

### Fixed
- Fixed timeline stuttering when playing 4K H.265 with 3+ effects (#1284)
- Fixed audio sync drift after 10 minutes of continuous playback (#1277)
- Fixed crash on project open when project path contains non-ASCII characters (#1291)

### Changed
- Export dialog now remembers last-used settings per project (#1265)

### Security
- Updated FFmpeg to 7.1.2 to patch CVE-2026-1234 (#1292)
```

---

## Release Notes Template

For each release, Mr.Orchords writes release notes using this template:

### Patch Release (X.Y.Z)

```markdown
## What's New in Mr.Orchords X.Y.Z

### Bug Fixes
[Copy "Fixed" items from changelog]

### Improvements
[Copy "Changed" items from changelog]

### Security
[Copy "Security" items from changelog]

**Full Changelog:** [View on GitHub](https://dev.orchords.com/mr-orchords/mr-orchords/blob/main/CHANGELOG.md)
```

### Minor Release (X.Y.0)

```markdown
## What's New in Mr.Orchords X.Y

### Headline Feature
[1-2 sentence description of the biggest feature]

### New Features
[Copy "Added" items from changelog, expanded with screenshots]

### Improvements
[Copy "Changed" items]

### Bug Fixes
[Copy "Fixed" items]

### Breaking Changes
[Any breaking changes, with migration instructions]

**Full Changelog:** [View on GitHub](https://dev.orchords.com/mr-orchords/mr-orchords/blob/main/CHANGELOG.md)
```

### Major Release (X.0.0)

A dedicated launch post by Mr.Orchords + Mr.Orchords with full feature walkthroughs, videos, and migration guides.

---

## Version Codenames

Major releases get a codename for internal use:

| Version | Codename | Theme |
|---|---|---|
| 1.0 | Firefly | First light — initial public release |
| 2.0 | Aurora | First major update after 1.0 |
| 3.0 | Nebula | Major architecture shift |

Codenames are chosen by the team at release planning time and retired when the next major version ships.

---

## The Changelog Process

### For Feature PRs

1. **Update CHANGELOG.md** in the same PR — don't wait until release
2. Write the entry for the **user**, not the developer:
   - ❌ "Refactored TimelineViewModel to use MVVM"
   - ✅ "Timeline now scrolls 60% smoother on high-DPI displays"
3. Reference the issue number: `(#1234)`
4. If the change is a new feature, add a one-line "What's New" summary for the release notes

### For Bug Fix PRs

1. Link to the original bug report issue
2. Describe the user-facing impact of the bug, not the code fix
3. If the bug was reported by a user, acknowledge them in the changelog: "Thanks @username for reporting!"

### When Cutting a Release

1. Mr.Orchords collects all changelog entries since the last release
2. Mr.Orchords writes release notes using the templates above
3. Changelog version header is updated from `Unreleased` to `[X.Y.Z] — YYYY-MM-DD`
4. Release notes are published to the Store and GitHub Releases

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial policy — aligned with Keep a Changelog 1.1.0 and ISO/IEC 12207:2017 |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Transition Process), ISO/IEC 25010:2023 (Functional Suitability), Keep a Changelog 1.1.0, Semantic Versioning 2.0.0*



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
| 1.0.0 | June 2026 | Mr.Orchords | Initial version |
| 1.0.1 | June 2026 | Mr.Orchords | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On each release
- **Reviewer:** Mr.Orchords (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type