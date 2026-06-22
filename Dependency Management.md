> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `Dependency Management.md` in the docs repo.

> Auto-generated from `docs/engineering/DEPENDENCY_MANAGEMENT.md` in the docs repo.

---
title: "Dependency Management"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "sarah.miller (Build & Release Engineer) — deps + reproducibility; kirk.beka (CTO) — policy"
status: "draft"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023 (Maintainability)", "ISO/IEC 19770-2:2015"]
---

# Dependency Management

**Project:** Beetle Studio
**Owner:** Sarah Miller (Build & Release Engineer) — dependency declarations + reproducibility; Kirk Beka (CTO) — policy approval
**Reviewers:** Mike Johnson (DevOps Lead), all engineering leads
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Configuration management), ISO/IEC 25010:2023 (Maintainability), ISO/IEC 19770-2:2015 (Software identification)
**Version:** 1.0.0
**Last Updated:** 2026-06-21

> **Status note (2026-06-21):** this document is a **draft**. The repo currently references vcpkg in `cmake/Dependencies.cmake` but does not yet ship a `vcpkg.json` manifest. The decision to commit fully to vcpkg (vs. Conan vs. CMake `FetchContent` vs. system packages) is pending. Until a `vcpkg.json` (or equivalent) lands, dependencies are not reproducible and this document is informational.

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Declared third-party dependencies, the package manager(s) in use, version pinning, and the SBOM/SVID provenance chain |
| **Diátaxis form** | Reference |
| **Primary audience** | Sarah Miller, Mike Johnson, all engineers who add or upgrade dependencies |
| **Secondary audience** | Security auditors; future maintainers |

---

## Purpose

Establish a single source of truth for every third-party C/C++ library Beetle Studio depends on, the version pinned, the license, and the source of truth. The intent is reproducible builds, license compliance, and the ability to answer "what versions ship in release vX.Y.Z?" from the SWID tag and the SBOM.

## Current State (2026-06-21)

The repo currently declares the following third-party dependencies in `cmake/Dependencies.cmake`:

| Package | Source | Version constraint | License (per official) | Notes |
|---|---|---|---|---|
| Qt6 (Core, Widgets, Multimedia) | Qt Project | `>= 6.5` (no upper bound) | LGPL v3 / GPL v2 / Commercial | GUI framework |
| FFmpeg | FFmpeg project | (not pinned) | LGPL v2.1+ / GPL v2+ (build-config dependent) | Codec pipeline |
| Vulkan SDK | Khronos | (not pinned) | Apache 2.0 | Optional rendering backend |
| DirectX 12 | Microsoft | (Windows SDK) | EULA (Microsoft) | Provided by Windows SDK; no vcpkg entry |
| WASAPI | Microsoft | (Windows SDK) | EULA (Microsoft) | Provided by Windows SDK; no vcpkg entry |

> **Gap:** the project does **not** currently ship a `vcpkg.json` manifest in the repo root. The comment in `cmake/Dependencies.cmake` states "manifest mode: vcpkg.json in repo root", but the file is missing. This is a known issue tracked separately; until it lands, the build is not reproducible — the developer is expected to have Qt6 / FFmpeg / Vulkan installed at the version that happens to work.

> **Note on Qt:** Qt6 is dual-licensed (LGPL / GPL / Commercial). Per the project's open-source posture, we distribute Beetle Studio under GPL — see [LICENSE](../LICENSE) (TBD) and [`docs/business/ENTERPRISE_LICENSING.md`](../business/ENTERPRISE_LICENSING.md) for the commercial-relink path. The exact license pinning for Qt should match the license of the final binary.

## Package Manager: vcpkg (Recommended)

**Decision pending** — the recommended path is vcpkg in manifest mode:

1. Add a `vcpkg.json` at the repo root declaring every dep with an explicit version range and the `builtin-baseline` (commit SHA) for reproducibility.
2. Run `vcpkg install` as the first step of every CI job. Pin the vcpkg binary version in `vcpkg-configuration.json`.
3. Use the vcpkg toolchain file (`-DCMAKE_TOOLCHAIN_FILE=/path/to/vcpkg.cmake`) for CMake.

A first-pass `vcpkg.json` would look like:

```json
{
  "name": "beetle-studio",
  "version-string": "unversioned",
  "builtin-baseline": "<commit-sha>",
  "dependencies": [
    "qt6-base",
    "qt6-widgets",
    "qt6-multimedia",
    "ffmpeg",
    "vulkan"
  ]
}
```

> **Unverified:** the exact vcpkg port names (`qt6-base` vs `qt6`) and the correct `builtin-baseline` SHA should be confirmed by running `vcpkg x-history` for each port at the time of pinning. The above is illustrative.

## Package Manager Alternatives Considered

| Option | Pros | Cons | Decision |
|---|---|---|---|
| **vcpkg (manifest mode)** | Microsoft-backed, large port catalog, works with CMake toolchain, single binary cache | Binary cache size, occasional long build times for some ports | **Recommended** |
| **Conan 2.x** | Mature, profiles for cross-platform, package recipes in Python | Separate CLI + recipe language; learning curve; weaker Qt support | Considered, not adopted |
| **CMake `FetchContent`** | Zero external dependency; just a CMake function | No central package metadata; no SBOM out of the box; license tracking manual | Considered, not adopted |
| **System packages (apt, vcpkg system, MSYS2)** | Easy for contributors on Linux | Not reproducible on Windows; version drift between contributors | Not adopted |
| **Vendored sources** | Total reproducibility | Bloats the repo; security patches lag upstream | Not adopted (consider for small libs) |

## Versioning Policy

| Dep | Pin strategy | Rationale |
|---|---|---|
| Qt6 | `>= 6.5.0 < 7.0.0` (SemVer caret) | Major versions bring binary-incompatible changes; minor versions are API-stable |
| FFmpeg | `>= 6.0 < 7.0` (project uses SemVer since 4.4) | Same |
| Vulkan | `>= 1.3` (header-only) | Vulkan is backward-compatible at the API level; ABI breaks are signalled via headers |
| DirectX 12 | Windows SDK 10.0.22621.0+ (Windows 11 22H2) | Tied to Windows SDK; upgrade with the Windows build env |
| WASAPI | (Windows SDK) | Tied to Windows SDK |

> **Unverified:** the actual version floor for Qt6 and FFmpeg should be confirmed by running a test build and noting the minimum version that compiles.

## License Compliance

Per `docs/security/WAIVERS.md` policy and the project license:

| License | Acceptable for inclusion? | Notes |
|---|---|---|
| MIT, BSD, Apache 2.0, Zlib | Yes | Permissive; OK for any distribution |
| LGPL v2.1+ | Yes (with dynamic linking) | LGPL allows proprietary linking only if the user can re-link the LGPL portion. Distribute the Qt DLLs unmodified. |
| LGPL v3 | Yes (with dynamic linking) | Same as above; v3 adds the "anti-tivoization" clause — verify Windows builds don't lock the binary. |
| GPL v2, GPL v3 | Conditional | Compatible only if Beetle Studio itself is GPL. If the project license is not GPL, GPL deps are **forbidden**. |
| AGPL | **No** | Network-copyleft is incompatible with the distribution model. |
| SSPL, Commons Clause, BUSL | **No** | Source-available but not OSI-approved; treat as proprietary. |
| Unlicensed | **No** | Cannot legally distribute. |

A scanner should run on every release to verify that no new copyleft contamination has slipped in. A future job should add `reuse lint` or `scancode-toolkit` to the release pipeline.

## Software Bill of Materials (SBOM)

Per ISO/IEC 19770-2:2015 and the planned `releases/SWID_TAG_SPEC.md` workflow, every release should include a CycloneDX 1.5 SBOM. The SBOM should list:

- Direct dependencies (name, version, license, source URL)
- Transitive dependencies (the full closure)
- PURL identifiers (https://github.com/package-url/purl-spec)
- Checksum (SHA-256) of the artifact the dep was built from

The `cyclonedx-cpp` tool (https://github.com/CycloneDX/cyclonedx-cpp) is the recommended generator; it integrates with CMake.

> **Status:** SBOM generation is **not** yet automated. A `scripts/generate_sbom.sh` and a step in `release-build.yml` are planned but not implemented.

## Security

- **SCA:** no automated dependency vulnerability scan is run today. The `security-scan.yml` workflow has no SCA job. **This is a known gap.**
- **Advisories:** engineers are expected to monitor the GitHub Advisory Database (https://github.com/advisories) for Qt, FFmpeg, and Vulkan advisories.
- **Patching cadence:** critical CVEs should be patched within 7 days; high within 30 days; medium within the next minor release.

> **TODO:** add `vcpkg audit` to `security-scan.yml` and a Dependabot (or Renovate) configuration file (`.github/dependabot.yml` or equivalent) to automate CVE detection.

## Reproducible Builds

The intent is for a release build to be byte-identical given the same source + same vcpkg cache + same compiler version. Steps to achieve this:

1. Pin the vcpkg `builtin-baseline` to a specific commit SHA.
2. Pin the MSVC version (record the exact VS 2022 build number in the release notes).
3. Use `/Zi` (or `/Z7`) for PDB generation; do not include build paths in the PDB (set `/PDBSOURCEPATH` correctly).
4. Set the source timestamp in a deterministic way (env `SOURCE_DATE_EPOCH`).
5. Strip the linker `/INCREMENTAL` flag.
6. Use the same Qt / FFmpeg / Vulkan build for every release on a given branch.

## Adding a New Dependency

1. Open an issue describing the dep, the license, the version range, and the rationale.
2. Get approval from Sarah Miller (Build) + Maya Rodriguez (Security).
3. Add the port name + version to `vcpkg.json` (when it exists) or to `cmake/Dependencies.cmake` for now.
4. Run a build to verify the dep compiles and links.
5. Update the dependency table at the top of this document.
6. Update the SBOM (manual) once the SBOM script exists.

## References

### Internal Documents

- [Build System](./BUILD_SYSTEM.md)
- [CI/CD Pipeline](./CI_CD_PIPELINE.md)
- [Release Checklist](../releases/RELEASE_CHECKLIST.md)
- [Versioning Policy](../releases/VERSIONING_POLICY.md)
- [SWID Tag Spec](../releases/SWID_TAG_SPEC.md)
- [Security Policy](../SECURITY_POLICY.md)
- [Security Waivers](../security/WAIVERS.md)
- [Threat Model (planned)](../security/THREAT_MODEL.md)
- [Enterprise Licensing](../business/ENTERPRISE_LICENSING.md)

### External

- vcpkg manifest mode — https://learn.microsoft.com/en-us/vcpkg/concepts/manifest-mode
- vcpkg GitHub — https://github.com/microsoft/vcpkg
- CycloneDX 1.5 spec — https://cyclonedx.org/specification/overview/
- ISO/IEC 19770-2:2015 — https://www.iso.org/standard/65666.html
- SPDX license list — https://spdx.org/licenses/
- Open Source Initiative licenses — https://opensource.org/licenses/
- PURL spec — https://github.com/package-url/purl-spec
- GitHub Advisory Database — https://github.com/advisories
- Reuse compliance tool — https://reuse.software/
- Scancode Toolkit — https://github.com/nexB/scancode-toolkit

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Configuration management), ISO/IEC 25010:2023 (Maintainability), ISO/IEC 19770-2:2015 (Software identification). Source-of-truth: `beetle-studio/beetle-studio@cmake/Dependencies.cmake` and (planned) `vcpkg.json`.*
