> Auto-generated from `Branch Naming.md` in the docs repo.

> Auto-generated from `Branch Naming.md` in the docs repo.

> Auto-generated from `docs/engineering/workflows/BRANCH_NAMING.md` in the docs repo.

---
title: "branch-naming.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "mike.johnson (DevOps Lead)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023 (Maintainability)"]
related-workflow: ".forgejo/workflows/branch-naming.yml"
---

# branch-naming.yml — Branch Naming Validation

**Project:** Beetle Studio
**Owner:** Mike Johnson (DevOps Lead)
**Reviewers:** Kirk Beka (CTO), all engineering leads
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Configuration management), ISO/IEC 25010:2023 (Maintainability)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/branch-naming.yml` (922 bytes, 1 job)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Validate PR head-branch names against the project's naming policy |
| **Diátaxis form** | Reference |
| **Primary audience** | Mike Johnson, all engineers |
| **Secondary audience** | Bot maintainers (BADRABBIT, GOODRABBIT, GRAYWOOLF, WHITERABBIT) — must use the allowed prefixes |

---

## Purpose

Enforces the branch naming convention documented in [`../BRANCHING_STRATEGY.md`](../BRANCHING_STRATEGY.md). Catches the common case where an engineer creates a branch like `Kirk/fix-thing` or `chore/update-deps` and the bot fleet is not consistent with the policy.

The check runs on every PR open / sync / reopen, except for paths under `docs/**` and any `.md` file (so that documentation-only PRs from arbitrary branches — including bot maintenance branches — are not blocked by the naming policy).

## Trigger

| Event | Types | Path filter |
|---|---|---|
| `pull_request` | `opened`, `synchronize`, `reopened` | `paths-ignore: ['docs/**', '**.md']` |

## Concurrency

| Group | Behavior |
|---|---|
| `branch-naming-${{ github.event.pull_request.number }}` | `cancel-in-progress: true` |

## Jobs & Steps

### `validate-name`

| Step | Purpose | Notes |
|---|---|---|
| 1. Validate branch name | Read `${{ github.head_ref }}` and test against the policy regex; `exit 1` on mismatch | 2-minute timeout |

The regex (verbatim from the workflow):

```
^(main|develop|release/v[0-9]+\.[0-9]+\.x|feature/[0-9]+-[a-z0-9][a-z0-9-]*|fix/[a-z0-9][a-z0-9-]*|hotfix/[0-9]+-[a-z0-9][a-z0-9-]*)
```

| Allowed pattern | Example | Notes |
|---|---|---|
| `main` | `main` | Default branch |
| `develop` | `develop` | Integration branch |
| `release/v*.*.x` | `release/v2.0.x` | Maintenance branches |
| `feature/<id>-<name>` | `feature/285-analyticstracker` | Numeric ID, then kebab-case |
| `fix/<name>` | `fix/presetmanager-leak` | No ID required |
| `hotfix/<id>-<name>` | `hotfix/450-crash-on-import` | Numeric ID required |

### Explicitly disallowed (the most common mistakes)

| Pattern | Example | Why blocked |
|---|---|---|
| `chore/*` | `chore/update-deps` | Not in regex. The CI rejects with "FAIL — branch 'chore/...' does not match naming policy" |
| `docs/*` | `docs/new-section` | The `docs/**` path-ignore handles most cases, but a branch named `docs/new-section` is also rejected by the regex |
| `<User>/<branch>` | `kirk/fix-thing` | Slash-separated user prefix is not allowed |
| CamelCase or underscores in `<name>` | `fix/PresetManager_Leak` | Regex requires `[a-z0-9][a-z0-9-]*` |
| `<name>` with leading hyphen | `fix/-bad` | Regex requires `[a-z0-9]` as first char |
| Mixed-case feature names | `feature/285-AnalyticsTracker` | Lowercase only in the `<name>` segment |

## Configuration

### Secrets

None.

### Environment variables

| Variable | Source |
|---|---|
| `BRANCH` | `${{ github.head_ref }}` (the source branch for the PR) |

## Failure Messages

The check `exit 1`s with the literal message:

```
FAIL - branch '<branch>' does not match naming policy
Allowed: main, develop, release/v*.*.x, feature/<id>-<name>, fix/<name>, hotfix/<id>-<name>
```

This is the full text the engineer sees in the Actions log.

## Overriding the Check

The check has **no override path** by design. If an emergency requires a non-conforming branch to land, the workflow is an advisory job (it could in principle be deleted), but the bot fleet (BADRABBIT, GOODRABBIT) reads the regex to know which PRs to review and which to skip. A non-conforming branch will land with no automated review and no `feature/`, `fix/`, or `hotfix/` semantic marker.

If the policy needs to be extended (e.g., to allow `release/<name>` for non-numeric tags), edit the regex in `branch-naming.yml` and open a PR. The workflow is small enough that a typo in the regex breaks every PR — review carefully.

## Known Limitations

- **Single regex, no per-team exemptions.** A team that uses `experiment/abc-...` for research cannot be exempted; they would need to add a new pattern.
- **No `release/v*` (no patch level)** — only `release/v[0-9]+\.[0-9]+\.x` is allowed. There is no provision for a one-off `release/foo` branch.
- **Path-ignore is broad.** A PR that changes `src/main.cpp` and `docs/spec.md` together is still checked because the path filter is `paths-ignore` (PR matches if it has at least one file not in the ignore list).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Workflow fails with "FAIL - branch '...' does not match naming policy" | The branch does not match the regex | Rename the branch (`git branch -m <new-name>`) and force-push; or open a new PR from a renamed branch |
| Workflow does not run on a docs-only PR | `paths-ignore` filter excluded it | This is intended; docs PRs from arbitrary branches are not gated |
| Workflow shows a typo'd branch name with weird characters | Terminal escape / clipboard artifact | The `BRANCH` env var is exactly what Forgejo set in `github.head_ref`; copy carefully |

## References

### Internal Documents

- [Branching Strategy](../BRANCHING_STRATEGY.md) — full policy narrative
- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [CONTRIBUTING.md](../../../CONTRIBUTING.md) (in the main repo) — contributor-facing branch rules

### External

- POSIX extended regex (ERE) — https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap09.html
- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- ISO/IEC 12207:2017 §6.3.5 — Configuration management process

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Configuration management). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/branch-naming.yml`.*
