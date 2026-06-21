---
title: "CI/CD Workflows — Overview"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "mike.johnson (DevOps Lead)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023"]
---

# CI/CD Workflows — Overview

**Project:** Beetle Studio
**Owner:** Mike Johnson (DevOps Lead)
**Reviewers:** Kirk Beka (CTO), Sarah Miller (Build & Release Engineer)
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Development process), ISO/IEC 25010:2023 (Reliability, Maintainability, Security)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Index of the 8 Forgejo Actions workflows in `beetle-studio/beetle-studio/.forgejo/workflows/` |
| **Diátaxis form** | Reference |
| **Primary audience** | All engineers, release engineers, security auditors |
| **Secondary audience** | New maintainers; future operators of the CI fleet |

---

## Forgejo Actions vs GitHub Actions

The workflows in this repo are written in **GitHub Actions YAML syntax** and run on **Forgejo Actions** runners. Per the [Forgejo Actions reference](https://forgejo.org/docs/latest/user/actions/reference/) and the [known list of differences](https://forgejo.org/docs/latest/user/actions/github-actions/), the following caveats apply:

| Aspect | GitHub Actions | Forgejo Actions |
|---|---|---|
| Default runner image | Ubuntu 22.04 / 24.04 with broad toolchain | **Debian bookworm with Node.js only** — every tool (`cmake`, `g++`, `clang-format`, `gitleaks`, `semgrep`, `jq`, `curl`, `apt-get`) must be installed by the step |
| Hosted runner labels | `ubuntu-latest`, `windows-latest`, `macos-latest` (always present) | **Self-hosted by default** — `ubuntu-latest` and `windows-latest` resolve only if the operator has registered a runner with those labels; otherwise the job will queue indefinitely |
| `github.*` context subkeys | All present | Some subkeys are missing (e.g., `github.event.pull_request.changed_files` is present, but some `github.event.*` subkeys are not) |
| `permissions:` on job | Supported | **Ignored** — use repo-level permissions on the token instead |
| `continue-on-error:` on job | Supported | **Ignored** — use `if: always()` or `if: failure()` on the next step |
| OIDC token | `permissions: id-token: write` | **`enable-openid-connect: true`** at the workflow level |
| Marketplace | `actions/checkout@v4`, etc. | **Same syntax works** if the action lives in a public git repo; for actions that need network, the runner must be online |
| Container support | `runs-on: ubuntu-latest` + Docker | Same, but LXC is also supported (`runs-on: [self-hosted, lxc]`) |

In practice, the workflows in this repo:
- Always use `runs-on: ubuntu-latest` or `runs-on: windows-latest` and assume the runner is registered with those labels.
- Always `apt-get install` the tools they need.
- Avoid `permissions:` and `continue-on-error:` at the job level.

> **Tip:** if a workflow queues and never starts, the runner label is missing. Check `https://dev.mooned.dev/-/admin/runners` for registered labels.

## Workflow Index

| # | Workflow | Trigger | Purpose | Doc |
|---|---|---|---|---|
| 1 | `auto-assign.yml` | `issues: opened` | Auto-assign issues by role keyword | [AUTO_ASSIGN.md](./AUTO_ASSIGN.md) |
| 2 | `auto-merge-md.yml` | `pull_request: opened/synchronize/reopened` | Auto-merge `.md`-only PRs | [AUTO_MERGE_MD.md](./AUTO_MERGE_MD.md) |
| 3 | `benchmarks.yml` | `pull_request` to `main` on `benchmarks/**` or `src/Engine/**` | Build + run engine benchmarks | [BENCHMARKS.md](./BENCHMARKS.md) |
| 4 | `branch-naming.yml` | `pull_request` opened/synchronize/reopened (non-docs) | Validate branch name policy | [BRANCH_NAMING.md](./BRANCH_NAMING.md) |
| 5 | `main-build.yml` | `push` to `main` on `src/**`/`tests/**`/`CMakeLists.txt` | Smoke build on `main` | [MAIN_BUILD.md](./MAIN_BUILD.md) |
| 6 | `pr-build.yml` | `pull_request` to `main`/`develop` on source files | Lint + smoke compile on PRs | [PR_BUILD.md](./PR_BUILD.md) |
| 7 | `release-build.yml` | `push` of `v*` tag | Release build on Windows | [RELEASE_BUILD.md](./RELEASE_BUILD.md) |
| 8 | `security-scan.yml` | `pull_request` to `main` on source/build files | Gitleaks + Semgrep | [SECURITY_SCAN.md](./SECURITY_SCAN.md) |

## Required Status Checks (Branch Protection)

The `main` branch has the following workflows registered as **required** (a PR cannot merge without them passing):

| Check | Workflow | Severity on fail |
|---|---|---|
| `Security Scan / semgrep (pull_request)` | `security-scan.yml` | Advisory (no fail) |
| `Security Scan / gitleaks (pull_request)` | `security-scan.yml` | Advisory (no fail) |
| `PR Build / compile-check (pull_request)` | `pr-build.yml` | Advisory (no fail) |
| `PR Build / lint (pull_request)` | `pr-build.yml` | Advisory (no fail) |
| `Benchmarks / benchmark (pull_request)` | `benchmarks.yml` | Advisory (no fail) |
| `Branch Naming / validate-name (pull_request)` | `branch-naming.yml` | **Hard fail — block merge** |
| `Auto-Merge MD / maybe-merge (pull_request)` | `auto-merge-md.yml` | Success means the workflow ran, not that the merge happened |

> **Note:** the lint, compile-check, semgrep, and gitleaks jobs all `exit 0` regardless of findings, so they always report `success` to branch protection. They are listed as required because the workflow should at least run; the human review is the actual gate. The only true hard-fail today is `Branch Naming / validate-name`.

## Pipeline Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       FORGEJO ACTIONS                            │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │  Open Issue  │ ──▶ │ auto-assign  │     │  Open PR     │     │
│  └──────────────┘     └──────────────┘     └──────┬───────┘     │
│                                                   │              │
│                                                   ▼              │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ pull_request: branch-naming (HARD GATE)                  │    │
│  │ pull_request: pr-build (lint + compile, advisory)        │    │
│  │ pull_request: security-scan (gitleaks + semgrep, advisory)│   │
│  │ pull_request: benchmarks (if benchmarks/ or Engine/**)   │    │
│  │ pull_request: auto-merge-md (if .md only)                │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                  │                               │
│                                  ▼ merge                         │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ push main: main-build (smoke build + lint)               │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                  │                               │
│                                  ▼ tag v*                        │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ push tag v*: release-build (Windows, /DNDEBUG, artifacts)│    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Concurrency Model

Workflows that operate on PRs use `concurrency.cancel-in-progress: true` keyed on the PR number, so a force-push cancels the prior in-flight run. This applies to:

- `branch-naming.yml`
- `pr-build.yml`
- `security-scan.yml`
- `benchmarks.yml`

`auto-merge-md.yml` does not declare a concurrency group (a re-evaluation is fast and cheap). `auto-assign.yml` does not (fires once per `opened`).

`main-build.yml` and `release-build.yml` do not (pushes are sequential).

## Adding a New Workflow

1. Add the YAML to `.forgejo/workflows/<name>.yml` with the standard `name:`, `on:`, `jobs:` shape.
2. Use a branch named `feature/<id>-workflow-<name>` or `fix/<name>` — `chore/*` is rejected by `branch-naming.yml`.
3. Document the workflow in this directory: copy the template at `docs/engineering/workflows/TEMPLATE.md` (if it exists) or follow the structure of any existing per-workflow doc.
4. Update the index table above.
5. If the workflow should be a required check, add it to branch protection via `https://dev.mooned.dev/beetle-studio/beetle-studio/settings/branches`.

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Branching Strategy](../BRANCHING_STRATEGY.md)
- [Build System](../BUILD_SYSTEM.md)
- [Test Strategy](../TEST_STRATEGY.md)
- [Security Policy](../../SECURITY_POLICY.md)

### External

- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- Forgejo Actions basic concepts — https://forgejo.org/docs/latest/user/actions/basic-concepts/
- Forgejo Actions vs GitHub Actions — https://forgejo.org/docs/latest/user/actions/github-actions/
- Forgejo Actions troubleshooting — https://forgejo.org/docs/latest/user/actions/troubleshooting/
- ISO/IEC 12207:2017 §6.3.5 — Development process
- ISO/IEC 25010:2023 — Quality model

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Development process), ISO/IEC 25010:2023. Workflows source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/*.yml`.*
