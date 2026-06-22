> Auto-generated from `Auto Merge Md.md` in the docs repo.

> Auto-generated from `Auto Merge Md.md` in the docs repo.

> Auto-generated from `Auto Merge Md.md` in the docs repo.

> Auto-generated from `Auto Merge Md.md` in the docs repo.

> Auto-generated from `Auto Merge Md.md` in the docs repo.

> Auto-generated from `Auto Merge Md.md` in the docs repo.

> Auto-generated from `Auto Merge Md.md` in the docs repo.

> Auto-generated from `docs/engineering/workflows/AUTO_MERGE_MD.md` in the docs repo.

---
title: "auto-merge-md.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "mike.johnson (DevOps Lead)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023 (Maintainability)"]
related-workflow: ".forgejo/workflows/auto-merge-md.yml"
---

# auto-merge-md.yml — Auto-merge Markdown-only PRs

**Project:** Beetle Studio
**Owner:** Mike Johnson (DevOps Lead)
**Reviewers:** Kirk Beka (CTO), Tom Anderson (Technical Writer)
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Project process), ISO/IEC 25010:2023 (Maintainability)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/auto-merge-md.yml` (2,219 bytes, 1 job)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Auto-merge of PRs whose changed files are 100% `.md` files |
| **Diátaxis form** | Reference |
| **Primary audience** | Mike Johnson, Tom Anderson |
| **Secondary audience** | All engineers who submit documentation PRs |

---

## Purpose

Documentation PRs (typo fixes, link repairs, formatting-only changes) are low-risk and create noise in the review queue. This workflow inspects the set of files in a PR and, if every file ends in `.md`, calls the Forgejo merge API directly. No human review is required.

It is the equivalent of GitHub's `actions/labeler` + auto-merge combo, implemented as a single shell job.

## Trigger

| Event | Types | Filter |
|---|---|---|
| `pull_request` | `opened`, `synchronize`, `reopened` | `github.event.pull_request.changed_files > 0` |

- No path filter. A PR that touches `src/` and `docs/` together will not auto-merge because of the MD-only check inside the job.
- No concurrency group. If a PR is force-pushed, the new run re-evaluates.

## Jobs & Steps

### `maybe-merge` (single job)

| Step | Purpose |
|---|---|
| 1. Auto-merge MD-only PR | 1) list the PR's files via `/pulls/{N}/files?per_page=100`; 2) verify every filename ends in `.md` (POSIX `case` glob); 3) check the PR is not in draft and not already merged; 4) POST to `/pulls/{N}/merge` |

The implementation uses POSIX `sh` only (no bash here-strings), so it works on the default Forgejo Runner image, which is `node:20-bookworm` and does not include `bash` by default.

#### Skip conditions (explicitly coded in the script)

| Condition | Effect |
|---|---|
| Any file in the PR is not `.md` | `echo "...skipping auto-merge"`, `exit 0` |
| `pr.draft == true` | `echo "draft, skip"` |
| `pr.merged == true` | `echo "merged, skip"` |
| Merge HTTP code != 200 | log but do not fail the workflow (`exit 0` at end) |

> **Caveat — `set +e` and `exit 0` at the end:** The job is intentionally non-failing. A 5xx from the merge API will show in the Actions UI as a "green" workflow run with a "merge finished (status N)" message. This is by design — the workflow should not block a PR if the merge daemon is briefly unavailable; a human can re-run the workflow or merge manually.

## Configuration

### Required secrets

| Secret | Used for |
|---|---|
| `secrets.ADMIN_TOKEN` | Bearer for both the `/files` listing and the `/merge` call |

### Environment variables

| Variable | Source |
|---|---|
| `API_TOKEN` | `${{ secrets.ADMIN_TOKEN }}` |
| `API` | hard-coded `http://host.docker.internal:3000/api/v1` |
| `REPO` | `${{ github.repository }}` |
| `PR_NUMBER` | `${{ github.event.pull_request.number }}` |

## Safety Properties

- **No file deletion risk:** the merge call uses `merge_message_field: "auto-merge-md"`, so the merge commit message identifies the workflow as the merger.
- **No force-push:** the merge API call does not pass `force_push: true`.
- **No bypass of branch protection:** if `main` requires reviews, the Forgejo API will return 403. The workflow logs the 403 and exits 0; the PR remains in the queue for human review. (Verify by reading branch protection rules in repo settings.)
- **No risk of merging non-MD content:** the file-list check happens before the merge call. If even one `.cpp` file is in the diff, the workflow exits before the merge attempt.

## Known Limitations

- **Filename only, not content.** A PR titled "fix typo in docs" that renames a file to `src/main.cp` (typo on `.cpp`) would still auto-merge if the new filename happens to end in `.md`. Edge case.
- **`changed_files > 0` check uses the GitHub Actions expression** — on a no-op branch push this evaluates to 0 and the job is skipped.
- **100-file cap.** `/pulls/{N}/files?per_page=100` truncates at 100. A PR with 101+ changed files would be incorrectly identified as MD-only if the first 100 are `.md`. Document a `per_page=200` request as a follow-up.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| PR is not auto-merged but contains only `.md` files | Branch protection requires a review; `ADMIN_TOKEN` lacks bypass | Either grant the token `write:repo, write:issue` scope and a repo-level bypass role, or remove the review requirement for MD-only paths |
| Workflow shows green but PR is still open | Merge returned non-200 (e.g., 422 due to dirty state); the script `exit 0`s and lets a human retry | Re-run the workflow, or merge manually |
| New branches are not picked up | The workflow fires on `opened/synchronize/reopened`; if the branch was never a PR, no event fires | Open the PR; the workflow will run |

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Branch Naming Workflow](./BRANCH_NAMING.md)
- [Style Guide](../../STYLE_GUIDE.md) — section "Documentation-as-code conventions"
- [Project Schedule](../../../PROJECT_SCHEDULE.md) — section "Docs freeze schedule"

### External

- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- Forgejo Actions vs GitHub Actions — https://forgejo.org/docs/latest/user/actions/github-actions/
- POSIX `case` glob semantics — https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_01
- ISO/IEC 12207:2017 §6.3.5 — Project process
- ISO/IEC 25010:2023 — Maintainability subcharacteristic

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Project process). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/auto-merge-md.yml`.*
