> Auto-generated from `Semantic Versioning.md` in the docs repo.

> Auto-generated from `Semantic Versioning.md` in the docs repo.

> Auto-generated from `Semantic Versioning.md` in the docs repo.

> Auto-generated from `docs/standards/SEMANTIC_VERSIONING.md` in the docs repo.

---
title: "Semantic Versioning 2.0.0 — Version Numbering Standard"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "engineering"
status: "approved"
iso-refs: ["Semantic Versioning 2.0.0 (semver.org)", "ISO/IEC 19770-2:2015 (SWID tags)"]
---

# Semantic Versioning 2.0.0

## Purpose

This document defines the versioning rules for all Beetle Studio releases, libraries, and APIs, following Semantic Versioning 2.0.0 as specified at semver.org.

Semantic Versioning provides a simple set of rules and requirements that dictate how version numbers are assigned and incremented, communicating meaning about the underlying code changes.

## Scope

Applies to:
- Beetle Studio application releases
- Internal libraries and modules
- Public API versions
- Plugin SDK versions
- Installer packages
- SWID tags (ISO/IEC 19770-2)

---

## Version Format

```
MAJOR.MINOR.PATCH
```

Given a version number `MAJOR.MINOR.PATCH`:

| Component | Increment When | Example |
|-----------|---------------|---------|
| MAJOR | Incompatible API/behavior changes | 1.0.0 → 2.0.0 |
| MINOR | Backward-compatible new functionality | 1.0.0 → 1.1.0 |
| PATCH | Backward-compatible bug fixes | 1.0.0 → 1.0.1 |

---

## Complete Rules (from semver.org)

### Rule 1: Public API Declaration
Software using Semantic Versioning MUST declare a public API. This API could be declared in the code itself or exist strictly in documentation. However it is done, it SHOULD be precise and comprehensive.

### Rule 2: Normal Version Format
A normal version number MUST take the form X.Y.Z where X, Y, and Z are non-negative integers, and MUST NOT contain leading zeroes. X is the major version, Y is the minor version, and Z is the patch version. Each element MUST increase numerically.

### Rule 3: Immutable Releases
Once a versioned package has been released, the contents of that version MUST NOT be modified. Any modifications MUST be released as a new version.

### Rule 4: Major Version Zero (Development)
Major version zero (0.y.z) is for initial development. Anything MAY change at any time. The public API SHOULD NOT be considered stable.

### Rule 5: Initial Public API
Version 1.0.0 defines the public API. The way in which the version number is incremented after this release is dependent on this public API and how it changes.

### Rule 6: Patch Version
Patch version Z (x.y.Z | x > 0) MUST be incremented if only backward-compatible bug fixes are introduced. A bug fix is defined as an internal change that corrects incorrect behavior.

### Rule 7: Minor Version
Minor version Y (x.Y.z | x > 0) MUST be incremented if new, backward-compatible functionality is introduced to the public API. It MUST be incremented if any public API functionality is marked as deprecated. It MAY be incremented if substantial new functionality or improvements are introduced within the private code. It MAY include patch level changes. Patch version MUST be reset to 0 when minor version is incremented.

### Rule 8: Major Version
Major version X (X.y.z | X > 0) MUST be incremented if any backward-incompatible changes are introduced to the public API. It MAY also include minor and patch level changes. Patch and minor versions MUST be reset to 0 when major version is incremented.

### Rule 9: Pre-release Versions
A pre-release version MAY be denoted by appending a hyphen and a series of dot-separated identifiers immediately following the patch version. Identifiers MUST comprise only ASCII alphanumerics and hyphens [0-9A-Za-z-]. Pre-release versions have lower precedence than the associated normal version.

Examples:
```
1.0.0-alpha
1.0.0-alpha.1
1.0.0-0.3.7
1.0.0-x.7.z.92
1.0.0-x-y-z.--
```

### Rule 10: Build Metadata
Build metadata MAY be denoted by appending a plus sign and a series of dot-separated identifiers immediately following the patch or pre-release version. Build metadata MUST be ignored when determining version precedence.

Examples:
```
1.0.0-alpha+001
1.0.0+20130313144700
1.0.0-beta+exp.sha.5114f85
1.0.0+21AF26D3----117B344092BD
```

### Rule 11: Precedence
Precedence MUST be calculated by separating the version into major, minor, patch, and pre-release identifiers in that order. Major, minor, and patch are always compared numerically.

Pre-release precedence:
- Identifiers consisting of only digits are compared numerically
- Identifiers with letters or hyphens are compared lexically in ASCII sort order
- Numeric identifiers always have lower precedence than alphanumeric identifiers
- A larger set of pre-release fields has a higher precedence than a smaller set

Example ordering:
```
1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
```

---

## Beetle Studio Version Scheme

### Release Versions
```
v1.0.0        - First stable release
v1.1.0        - New features (e.g., new codec support)
v1.1.1        - Bug fix
v2.0.0        - Breaking changes (e.g., project file format change)
```

### Pre-release Versions
```
v1.2.0-alpha.1   - First alpha (internal testing)
v1.2.0-alpha.2   - Second alpha
v1.2.0-beta.1    - First beta (beta program)
v1.2.0-rc.1      - Release candidate
v1.2.0-rc.2      - Second release candidate
v1.2.0           - Final release
```

### Build Metadata
```
v1.2.0+build.1234          - CI build number
v1.2.0-rc.1+sha.a1b2c3d    - Git commit hash
```

### Git Tags
```
v1.0.0          - Triggers release-build.yml
v1.1.0-beta.1   - Pre-release (marked as prerelease in Forgejo)
```

---

## What Constitutes a Breaking Change (Major bump)

For Beetle Studio:
- Project file format incompatibility (can't open old projects)
- Plugin SDK API signature changes
- Removal of supported codec/format
- Minimum OS version increase
- CLI argument changes

## What Constitutes New Functionality (Minor bump)

- New effect or filter
- New codec/format support
- New keyboard shortcut
- New UI panel or tool
- New API endpoint in plugin SDK

## What Constitutes a Bug Fix (Patch bump)

- Crash fix
- Rendering artifact correction
- Performance regression fix
- Typo in UI text
- Incorrect color conversion

---

## References

- [Semantic Versioning 2.0.0 (semver.org)](https://semver.org/)
- [SemVer 2.0.0 Specification (markdown)](https://semver.org/spec/v2.0.0.md)
- [ISO/IEC 19770-2:2015 (SWID tags use SemVer)](https://www.iso.org/standard/65666.html)
