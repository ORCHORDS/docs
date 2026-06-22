> Auto-generated from `Pr Build.md` in the docs repo.

> Auto-generated from `Pr Build.md` in the docs repo.

> Auto-generated from `docs/engineering/workflows/PR_BUILD.md` in the docs repo.

---
title: "pr-build.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "sarah.miller (Build & Release Engineer)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023 (Reliability)"]
related-workflow: ".forgejo/workflows/pr-build.yml"
---

# pr-build.yml — Build on Pull Request

**Project:** Beetle Studio
**Owner:** Sarah Miller (Build & Release Engineer)
**Reviewers:** Mike Johnson (DevOps Lead), Lisa Martinez (QA Lead)
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Development process), ISO/IEC 25010:2023 (Reliability)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/pr-build.yml` (1,817 bytes, 2 jobs)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Lint + smoke compile on every PR to `main` or `develop` |
| **Diátaxis form** | Reference |
| **Primary audience** | Sarah Miller, Mike Johnson, all engineers |
| **Secondary audience** | QA engineers; release engineers reading the smoke build signal |

---

## Purpose

Same lint + smoke-compile gate as `main-build.yml`, but scoped to pull requests. Acts as the early-warning signal that a PR is likely to break the build. Like `main-build.yml`, both jobs are **advisory** — they always exit 0 even on lint or compile failure, so the workflow is informational rather than gating.

## Trigger

| Event | Filter |
|---|---|
| `pull_request` | `branches: [main, develop]`, `paths: ['src/**', 'include/**', 'tests/**', 'CMakeLists.txt', 'cmake/**', '**.cpp', '**.h', '**.hpp', '**.c', '**.cc']` |

PRs that touch only `docs/**` or `.md` files do not trigger this workflow (handled separately by `auto-merge-md.yml`).

## Concurrency

| Group | Behavior |
|---|---|
| `pr-build-${{ github.event.pull_request.number }}` | `cancel-in-progress: true` — only the latest push runs |

## Jobs

### 1. `lint`

| Aspect | Value |
|---|---|
| Runner | `ubuntu-latest` |
| Timeout | 5 minutes |

#### Steps

| # | Step | Purpose |
|---|---|---|
| 1 | Checkout | `actions/checkout@v4`, `fetch-depth: 1` |
| 2 | Check formatting | Installs `clang-format`; runs `clang-format --dry-run --Werror` on up to 200 files matching `*.cpp`, `*.h`, `*.hpp` under `src/`, `tests/`, `include/` |

The job is wrapped in `set +e` and ends with `exit 0`, so format errors appear in the log but do not block the PR.

### 2. `compile-check`

| Aspect | Value |
|---|---|
| Runner | `ubuntu-latest` |
| Timeout | 8 minutes |

#### Steps

| # | Step | Purpose |
|---|---|---|
| 1 | Checkout | `actions/checkout@v4`, `fetch-depth: 1` |
| 2 | Smoke build | Installs `g++` and `cmake` if missing; runs `g++ -std=c++20 -fsyntax-only -Isrc -Iinclude <file>` on the first 5 `.cpp` files found under `src/`, `tests/`, `include/` |

The compile is **syntax-only** (no codegen) and is restricted to 5 files. This is intentionally cheap — a full compile of all engine code on every PR would burn CI minutes. The tradeoff is that a header change in `src/Core/` that breaks `src/Effects/` will not be caught unless the changed file is among the first 5 enumerated.

Like `lint`, the job is wrapped in `set +e` and exits 0 regardless of compile errors.

## Configuration

### Secrets

None.

### Tools (auto-installed)

| Tool | Step | Source |
|---|---|---|
| `clang-format` | lint | `apt-get install -y clang-format` |
| `g++` | compile-check | `apt-get install -y g++ cmake` |
| `cmake` | compile-check | same |

## Path-Filter Behavior

The `paths:` list is an OR — a PR matches if **any** changed file matches any of the patterns. This means a PR that renames a file to `notes.txt` and also changes `src/main.cpp` will still trigger the workflow. A pure `notes.txt` change will not.

The pattern list:

| Pattern | Matches |
|---|---|
| `src/**` | Anything under `src/` |
| `include/**` | Public headers |
| `tests/**` | Test code |
| `CMakeLists.txt` | Top-level CMake |
| `cmake/**` | CMake modules |
| `**.cpp` `**.h` `**.hpp` `**.c` `**.cc` | Any C/C++ source file anywhere in the tree |

The dual listing (`src/**` AND `**.cpp`) is belt-and-suspenders; the glob patterns would already cover the source-tree files.

## Known Limitations

- **Advisory only.** Lint and compile errors are surfaced in the log but do not block the PR. There is no current "required check" enforcement via branch protection.
- **5-file compile limit.** A 50-file PR that breaks compile in file 6 will not be caught. The limit exists to keep the job under 8 minutes.
- **Linux compile, MSVC build.** The compile runs on `g++` against a Linux runner. MSVC-specific code (`__declspec`, `#pragma comment`, etc.) may parse differently. The actual Windows build happens in `main-build.yml` after merge.
- **No header-only changes tested.** A PR that adds a new method declaration to a widely-included header is unlikely to be among the first 5 `.cpp` files, so the syntax check will not exercise it.
- **No dependencies.** No vcpkg install step; if the project requires Boost or FFmpeg, the compile will fail with "header not found" — expected, advisory, but may surprise new contributors.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Workflow does not run | Path filter excluded the change | Verify the diff touches one of the configured patterns |
| Lint step produces no output | No `.cpp`/`.h`/`.hpp` files under the listed directories | This is normal for header-only or test-only PRs |
| Compile step shows "header not found" | The project has external dependencies not declared in any workflow | Add a vcpkg / FetchContent step; this is a known gap |
| Job times out at 8 minutes | Compile of 5 files took too long; usually a template-heavy header chain | Reduce the limit to 3 files; or bump `timeout-minutes` to 12 |
| CI shows green but `main` is broken | The 5-file limit and the lack of full-tree compile mean a regression in file 6+ will pass PR but break `main` | Increase the file limit; or add a separate full-tree compile job in `main-build.yml` |

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Main Build Workflow](./MAIN_BUILD.md) — the post-merge counterpart
- [Build System](../BUILD_SYSTEM.md) — full CMake target list
- [Test Strategy](../TEST_STRATEGY.md)

### External

- `clang-format` — https://clang.llvm.org/docs/ClangFormat.html
- `g++ -fsyntax-only` — https://gcc.gnu.org/onlinedocs/gcc/Syntax-Checking.html
- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- ISO/IEC 12207:2017 §6.3.5 — Development process
- ISO/IEC 25010:2023 — Reliability subcharacteristic

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Development process). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/pr-build.yml`.*
