> Auto-generated from `docs/engineering/workflows/MAIN_BUILD.md` in the docs repo.

---
title: "main-build.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "sarah.miller (Build & Release Engineer)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023 (Reliability)"]
related-workflow: ".forgejo/workflows/main-build.yml"
---

# main-build.yml — Build on Push to main

**Project:** Beetle Studio
**Owner:** Sarah Miller (Build & Release Engineer)
**Reviewers:** Mike Johnson (DevOps Lead), Kirk Beka (CTO)
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Development process), ISO/IEC 25010:2023 (Reliability)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/main-build.yml` (1,467 bytes, 2 jobs)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Build + lint on every push to `main` |
| **Diátaxis form** | Reference |
| **Primary audience** | Sarah Miller, Mike Johnson |
| **Secondary audience** | All engineers; release engineers reading the build artifacts |

---

## Purpose

Provides a fast, repeatable build of `main` to confirm the tip of the integration branch is always releasable. Runs a real MSVC compile of `src/main.cpp` (smoke build) plus a clang-format check across `src/` and `tests/`. This is the canonical "is `main` shippable?" signal that release engineers consult before cutting a tag.

## Trigger

| Event | Filter |
|---|---|
| `push` | `branches: [main]`, `paths: ['src/**', 'tests/**', 'CMakeLists.txt']` |

A push of `docs/...` alone does not trigger this workflow.

## Jobs

### 1. `build-windows`

| Aspect | Value |
|---|---|
| Runner | `windows-latest` |
| Shell | `cmd` (required — `pwsh` and `bash` are not available on the moon-pc self-hosted runner; per CI runbook note in main repo) |

#### Steps

| # | Step | Purpose |
|---|---|---|
| 1 | Checkout | `git clone --depth 1 http://localhost:3000/beetle-studio/beetle-studio.git .` (clones the local instance directly; no auth needed) |
| 2 | Build main.cpp | Calls `vcvarsall.bat x64`, then `cl.exe /std:c++20 /EHsc /O2 /Fe:build\BeetleStudio.exe src\main.cpp` with the Windows desktop subsystem libs linked |
| 3 | Verify binary | Checks that `build\BeetleStudio.exe` exists; if not, `exit /b 1` |

> **Note on `cl.exe` invocation:** This workflow builds **only** `src/main.cpp` to a Windows executable, not the full project. It is a smoke build that proves the toolchain is functional and that the entry-point source compiles. The full CMake-driven build is a planned future improvement (the `cmake/**` path filter is only present in `pr-build.yml`).

#### Linked libraries

The build links against: `user32 gdi32 gdiplus shell32 ole32 comctl32 comdlg32 advapi32 wininet dxgi d3d11 shlwapi dwmapi uxtheme winmm`.

| Library | Subsystem | Why |
|---|---|---|
| `user32` `gdi32` `gdiplus` | Core UI / 2D graphics | Windowing, GDI, GDI+ rendering |
| `shell32` `ole32` `comctl32` | Common controls | Explorer-style UI, COM, theme support |
| `comdlg32` `advapi32` | Dialogs, registry | Open/Save dialogs, Windows registry |
| `wininet` | HTTP client | License-check / cloud features |
| `dxgi` `d3d11` | Direct3D 11 | GPU rendering path |
| `shlwapi` `dwmapi` `uxtheme` | Theming | Desktop Window Manager, visual styles |
| `winmm` | Multimedia | Waveform / audio engine |

### 2. `lint-check`

| Aspect | Value |
|---|---|
| Runner | `ubuntu-latest` |

#### Steps

| # | Step | Purpose |
|---|---|---|
| 1 | Checkout | `actions/checkout@v4` |
| 2 | Check formatting | Installs `clang-format` if missing; runs `clang-format --dry-run --Werror` over up to 100 files under `src/` and `tests/` |

> **Caveat — `|| true` at the end of the step:** Lint failures are advisory. A PR that breaks formatting will not block merge via this workflow. The clang-format check exists to surface format issues in the Actions log; engineers are expected to run `clang-format` locally before pushing.

## Configuration

### Secrets

None. The job does not call any external API.

### Tools (auto-installed)

| Tool | Step | Source |
|---|---|---|
| `cl.exe` (MSVC) | build-windows | Pre-installed on `windows-latest` via Visual Studio 2022 Community |
| `clang-format` | lint-check | `apt-get install -y clang-format` on the ubuntu runner |

## Build Artifacts

The workflow does not currently upload artifacts. The compiled `BeetleStudio.exe` is local to the runner's workspace and discarded when the job ends. This is intentional — release artifacts are produced by `release-build.yml` on a tag.

## Known Limitations

- **Single-file compile.** The build step compiles only `src/main.cpp`; the rest of the project (Engine, Timeline, Effects, Plugins, AI, etc.) is not exercised. A header change in `src/Core/` that breaks `src/Timeline/` will not be caught.
- **No CMake invocation.** The intended path is to use `cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build`. The current direct `cl.exe` call is a placeholder.
- **No tests run.** The `tests/**` path filter is in the trigger, but no test execution step exists. The actual test driver is not yet wired.
- **Lint is advisory.** Format issues do not block merge.
- **No artifact retention.** The exe is not published; release engineers must build locally for verification.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `cl.exe` not found | Visual Studio 2022 Community not installed on the runner | Install VS 2022 Build Tools; the path `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat` is hard-coded |
| Build fails with `fatal error C1083` | Header not found; likely a missing include directory | Add the include path to the `cl.exe` invocation; the smoke build only knows about implicit Windows SDK includes |
| Lint step does nothing | No `.cpp`/`.h` files under `src/` or `tests/` (unlikely on `main`) | The script logs "no source files to lint" and exits 0 |
| Workflow does not run on a push | The push did not touch `src/**`, `tests/**`, or `CMakeLists.txt` | This is intended; docs-only pushes do not require a build |

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Build System](../BUILD_SYSTEM.md) — full CMake target list
- [PR Build Workflow](./PR_BUILD.md) — what the PR pipeline does differently
- [Release Build Workflow](./RELEASE_BUILD.md) — what the tag pipeline produces

### External

- MSVC `/std:c++20` — https://learn.microsoft.com/en-us/cpp/build/reference/std-specify-language-standard-version
- `clang-format` — https://clang.llvm.org/docs/ClangFormat.html
- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- ISO/IEC 12207:2017 §6.3.5 — Development process
- ISO/IEC 25010:2023 — Reliability subcharacteristic

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Development process). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/main-build.yml`.*
