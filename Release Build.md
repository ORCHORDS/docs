> Auto-generated from `Release Build.md` in the docs repo.

> Auto-generated from `Release Build.md` in the docs repo.

> Auto-generated from `docs/engineering/workflows/RELEASE_BUILD.md` in the docs repo.

---
title: "release-build.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "sarah.miller (Build & Release Engineer)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 19770-2:2015", "ISO/IEC 25010:2023 (Reliability)"]
related-workflow: ".forgejo/workflows/release-build.yml"
---

# release-build.yml — Build on Version Tag

**Project:** Beetle Studio
**Owner:** Sarah Miller (Build & Release Engineer)
**Reviewers:** Mike Johnson (DevOps Lead), Kirk Beka (CTO)
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Development process), ISO/IEC 19770-2:2015 (Software identification / SWID), ISO/IEC 25010:2023 (Reliability)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/release-build.yml` (1,470 bytes, 1 job)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Build + verify a tagged release on Windows |
| **Diátaxis form** | Reference |
| **Primary audience** | Sarah Miller, Mike Johnson |
| **Secondary audience** | Release manager; all engineers cutting release branches |

---

## Purpose

Produces a release-grade `BeetleStudio.exe` for any tag matching `v*` (any string starting with `v`). Runs on `windows-latest` with the MSVC 2022 toolchain, links the same subsystem libraries as `main-build.yml`, but adds `/DNDEBUG` and an `artifacts/` packaging step.

This is the workflow that produces the binary that gets code-signed, hashed, and uploaded to the website and the Microsoft Store.

## Trigger

| Event | Filter |
|---|---|
| `push` | `tags: ['v*']` |

There is no path filter. A tag push fires the workflow even if the diff at the tag is purely a docs change — but in practice the release process (per `RELEASE_CHECKLIST.md`) requires a green `main` before tagging, so the diff is always meaningful.

## Jobs

### `build-release`

| Aspect | Value |
|---|---|
| Runner | `windows-latest` |
| Shell | `cmd` |

#### Steps

| # | Step | Purpose |
|---|---|---|
| 1 | Checkout | `git clone --depth 1 --branch %GITHUB_REF_NAME% http://localhost:3000/beetle-studio/beetle-studio.git .` |
| 2 | Build Release | Calls `vcvarsall.bat x64`, then `cl.exe /std:c++20 /EHsc /O2 /DNDEBUG /Fe:build\release\BeetleStudio.exe src\main.cpp` with the standard Windows desktop libraries |
| 3 | Verify release binary | Checks `build\release\BeetleStudio.exe` exists; logs `dir` of the binary; `exit /b 1` on missing |
| 4 | Package artifacts | Copies the exe to `artifacts\BeetleStudio.exe`; writes `artifacts\BUILD_INFO.txt` with the tag name |

> **Note on `cl.exe` invocation:** This is the same single-file compile as `main-build.yml`. The release build does not invoke CMake or the full target list. The release manager must rely on `main-build.yml` (and the intended-but-not-yet-implemented full CMake build) to have validated the integration before tagging. Tag-time verification is restricted to "does this specific entry-point compile in Release mode?".

#### Differences from `main-build.yml`

| Aspect | main-build.yml | release-build.yml |
|---|---|---|
| Trigger | `push` to `main` | `push` of `v*` tag |
| Defines | (debug) | `/DNDEBUG` |
| Output dir | `build\` | `build\release\` |
| Artifact | none | `artifacts\BeetleStudio.exe` + `artifacts\BUILD_INFO.txt` |
| Lint job | yes | no |
| Concurrency | none | none |

## Tag Format

The workflow fires for **any** tag starting with `v`, but the project convention (per [`VERSIONING_POLICY.md`](../../releases/VERSIONING_POLICY.md)) is Semantic Versioning 2.0.0:

| Tag | Interpreted as |
|---|---|
| `v1.2.3` | Major 1, Minor 2, Patch 3 |
| `v2.0.0` | Major 2, Minor 0, Patch 0 — breaking change |
| `v2.0.0-rc.1` | Pre-release (the workflow will still build it; pre-release is a tag, not a separate workflow trigger) |
| `v2` | Truncated — not allowed by SemVer; the workflow will still build it (matches `v*`); the release manager should reject it manually |

The workflow does not currently validate that the tag is a proper SemVer string. Validation happens manually during the release process.

## Configuration

### Secrets

None used by the workflow itself. The **code-signing** and **upload** steps are not yet in the workflow — they are performed manually by Sarah Miller using `signtool` and the artifact registry. The intended future state is to add a `sign` step using `secrets.CODE_SIGN_CERT_PFX` and `secrets.CODE_SIGN_CERT_PASSWORD` secrets.

### Tools (auto-installed)

| Tool | Source |
|---|---|
| `cl.exe` (MSVC 2022) | Pre-installed on `windows-latest` |

## Build Artifacts

| File | Purpose |
|---|---|
| `artifacts/BeetleStudio.exe` | The release binary, copied from `build/release/` |
| `artifacts/BUILD_INFO.txt` | Human-readable provenance (`Release vX.Y.Z packaged`) |

The workflow does not currently upload these artifacts to the Forgejo release page. Manual upload by Sarah Miller is required. A future improvement: add `actions/upload-artifact@v4` (Forgejo-compatible) and `actions/github-release@v2` (or a Forgejo release API call).

## SWID Tag and SBOM

Per `releases/SWID_TAG_SPEC.md`, every release should also include:
- A SWID tag file (`swidtag.xml`) conforming to ISO/IEC 19770-2:2015
- A CycloneDX 1.5 SBOM (`sbom.cdx.json`)

Neither is currently produced by this workflow. They are generated manually by Sarah Miller. Add to a follow-up: a step that runs `scripts/generate_swid_tag.py` and `scripts/generate_sbom.sh` and copies outputs into `artifacts/`.

## Known Limitations

- **Single-file compile only.** Same as `main-build.yml`. A release tag that breaks full-tree compile will still produce an `exe` (from `src/main.cpp` only) and pass this workflow.
- **No code signing.** Manual step performed by Sarah Miller.
- **No artifact upload.** Manual step.
- **No SWID / SBOM generation.** Manual step.
- **No version-embedded metadata.** The exe does not carry the version as a resource; the version lives in `BUILD_INFO.txt` only.
- **No installer packaging.** Per `releases/INSTALLER_SPEC.md`, releases are supposed to ship as an Inno Setup installer. This workflow produces a portable exe, not the installer. A follow-up should add a step invoking `iscc.exe` on `installer/BeetleStudio.iss`.
- **No rollback step.** A bad release tag is not auto-undone. The rollback procedure in `CI_CD_PIPELINE.md` is manual.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Workflow did not fire on a tag push | The tag did not start with `v` | Re-tag with the correct prefix; or update the workflow's `tags:` list |
| `cl.exe` not found | VS 2022 Community not installed on runner | Install VS 2022 Build Tools; verify the `vcvarsall.bat` path |
| Build succeeds but `artifacts\` is empty | The `copy` step failed silently | Check the source path `build\release\BeetleStudio.exe`; the verify step should have caught this |
| Release exe is too small (< 5 MB) | Static link stripped; missing subsystem | Verify the `cl.exe` command line includes the full library list |
| Tag was pushed but the workflow shows a 5xx on the `git clone` step | Forgejo host was momentarily unavailable | Re-run the workflow (it will re-clone and re-build) |

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Release Checklist](../../releases/RELEASE_CHECKLIST.md)
- [Versioning Policy](../../releases/VERSIONING_POLICY.md) — SemVer
- [SWID Tag Spec](../../releases/SWID_TAG_SPEC.md) — ISO/IEC 19770-2
- [Installer Spec](../../releases/INSTALLER_SPEC.md) — Inno Setup target
- [Code Signing Certificate Management](../../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md)

### External

- Semantic Versioning 2.0.0 — https://semver.org/
- ISO/IEC 19770-2:2015 (SWID tags) — https://www.iso.org/standard/65666.html
- CycloneDX 1.5 SBOM spec — https://cyclonedx.org/specification/overview/
- Inno Setup — https://jrsoftware.org/isinfo.php
- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- ISO/IEC 12207:2017 §6.3.5 — Development process
- ISO/IEC 25010:2023 — Reliability subcharacteristic

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Development process), ISO/IEC 19770-2:2015 (SWID). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/release-build.yml`.*
