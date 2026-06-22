> Auto-generated from `releases/CHANGELOG_POLICY.md` in the docs repo.

> Auto-generated from `docs/releases/CHANGELOG_POLICY.md` in the docs repo.

---
title: "Changelog Policy"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Changelog Policy

**Project:** Beetle Studio  
**Owner:** Sarah Miller (Build & Release Engineer) — format enforcement; Tom Anderson (Technical Writer) — content authorship  
**Reviewers:** Mike Johnson (DevOps Lead), Kirk Beka (CTO)
**Reviewer:** Kirk Beka (CTO), Chris Taylor (Product Manager)  
**ISO Standards:** ISO/IEC 12207:2017, ISO/IEC 14764:2022 (maintenance documentation), Keep a Changelog standard  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Changelog format, authorship, and automation rules |
| **Diátaxis form** | Reference |
| **Primary audience** | All engineers, technical writers, release engineers |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

Every meaningful change to Beetle Studio must be recorded in the changelog. The changelog is a version-controlled, human-readable record of what changed, why, and who made it. Per **ISO/IEC 14764:2022**, maintenance documentation -- including a change log -- is required for all software changes, especially post-release.
## Contents

- [File Location](#file-location)
- [Changelog Categories](#changelog-categories)
  - [Added](#added)
  - [Changed](#changed)
  - [Deprecated](#deprecated)
  - [Removed](#removed)
  - [Fixed](#fixed)
  - [Security](#security)
  - [Performance](#performance)
  - [Documentation](#documentation)
  - [Refactored](#refactored)
  - [Tests](#tests)
- [Entry Format](#entry-format)
  - [Full Entry (for user-facing changes)](#full-entry-for-user-facing-changes)
  - [Added](#added)
  - [Compact Entry (for internal/maintenance changes)](#compact-entry-for-internalmaintenance-changes)
  - [Fixed](#fixed)
  - [Breaking Change Entry (requires special flag)](#breaking-change-entry-requires-special-flag)
  - [Removed](#removed)
- [Version Sections](#version-sections)
- [Who Writes What](#who-writes-what)
- [Automation](#automation)
  - [Conventional Commit Format](#conventional-commit-format)
- [GitHub Releases](#github-releases)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## File Location

```
BEETLE_STUDIO/
├── CHANGELOG.md              ← master changelog (auto-generated + manual)
└── docs/releases/
    └── CHANGELOG_POLICY.md   ← this document
```

`CHANGELOG.md` lives in the repo root and is committed alongside the release tag.

---

## Changelog Categories

Use these sections consistently. Every entry belongs in exactly one section.

### Added
New features added since the last release.

### Changed
Changes to existing functionality (behavioral changes, not bug fixes).

### Deprecated
Features that exist but are marked for removal in a future version. Users should be given notice (at least one MINOR release) before removal.

### Removed
Features that have been removed. No longer available.

### Fixed
Bug fixes. Every confirmed user-facing bug fix should appear here.

### Security
Security-related fixes (vulnerability patches, CVEs, hardening changes).

### Performance
Performance improvements (speed, memory, GPU utilization).

### Documentation
Documentation-only changes (user guide updates, API docs, tutorial content).

### Refactored
Code refactoring that doesn't change behavior — improved internal structure.

### Tests
Test additions, modifications, or fixes (primarily for maintainers).

---

## Entry Format

### Full Entry (for user-facing changes)

```
### Added
- **New timeline track types** — Multi-camera track support added to the timeline.
  Tracking: #1234 | Fixed in: v2.4.0
```

### Compact Entry (for internal/maintenance changes)

```
### Fixed
- Fix playhead jump when scrubbing past 1-hour mark (#1220)
- Fix audio crackling on project load with 20+ audio tracks (#1218)
```

### Breaking Change Entry (requires special flag)

```
### Removed
- **BREAKING** Plugin API method `IBeetleEffect::getParameterCount()` removed.
  Use `IBeetleEffect::getParameters()` instead. Migration guide: docs/effects/MIGRATION.md
  Tracking: #1156 | Deprecated since: v2.2.0 | Removed in: v3.0.0
```

---

## Version Sections

Each released version gets its own top-level section:

```markdown
## [2.3.0] — 2026-06-15

### Added
...

### Fixed
...

---

## [2.2.0] — 2026-05-01

### Added
...
```

Unreleased changes go under a `[Unreleased]` section at the top.

---

## Who Writes What

| Content | Author | Reviewer | When |
|---|---|---|---|
| User-facing feature additions | Chris Taylor (PM) | Kirk Beka | At feature acceptance |
| Bug fixes | Respective engineer | Lisa Martinez | At bug close |
| Breaking changes | Domain lead | Kirk Beka | At change introduction |
| Performance improvements | Respective engineer | James Park | At PR merge |
| Documentation changes | Tom Anderson | — | As needed |
| Security fixes | Kirk Beka or assignee | Kirk Beka | Immediately |

---

## Automation

The changelog is **partially auto-generated** from git commits. The process:

1. Engineers write conventional commit messages (see below)
2. CI runs `git-cliff` or `standard-version` on each tag
3. Auto-generated draft is placed in `[Unreleased]` section
4. Sarah Miller and Tom Anderson review and clean up the draft
5. Manual entries added for context, user impact, and links
6. Approved and committed with the release tag

### Conventional Commit Format

Use this prefix format in commit messages:

```
<type>(<scope>): <short description>

[optional body]

[optional footer: Tracking: #issue | Fixed in: vX.Y.Z]
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `chore`, `security`

**Examples:**
```
feat(timeline): add multi-camera track support
fix(codec): correct frame drop when scrubbing HEVC footage
perf(gpu): reduce VRAM usage during preview playback
security(auth): patch token refresh vulnerability
docs(api): update OpenFX parameter documentation
```

---

## GitHub Releases

Each git tag triggers a GitHub Release. The release body is sourced from the changelog entry for that version. Tom Anderson drafts the release description; Sarah Miller publishes after QA sign-off.

Release description template:
```markdown
# Beetle Studio vX.Y.Z

<short summary paragraph — 2-3 sentences, user-focused>

## What's New
<pulled from CHANGELOG.md Added section>

## Bug Fixes
<pulled from CHANGELOG.md Fixed section>

## Performance
<pulled from CHANGELOG.md Performance section>

## Known Issues
<ul>
  <li>Issue description — tracking link</li>
</ul>

## Upgrading
<if breaking changes: migration instructions>
```

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial policy — aligned with Keep a Changelog 1.1.0 and ISO/IEC 14764:2022 |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Transition), ISO/IEC 14764:2022 §6 (Maintenance Documentation), Keep a Changelog 1.1.0*



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
| 1.0.0 | June 2026 | Sarah Miller | Initial version |
| 1.0.1 | June 2026 | Sarah Miller | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Sarah Miller (Build & Release Engineer) — format enforcement
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type