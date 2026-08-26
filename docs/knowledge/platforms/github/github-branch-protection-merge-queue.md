# github-branch-protection-merge-queue

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) protects `main` with legacy branch protection rules (Settings → Branches). The team wants to enforce merge queue, require specific CI checks by exact job name, restrict who can bypass, and enforce review from mobile PRs — but the legacy branch protection UI does not expose merge queue configuration cleanly, the bypass list is global rather than per-ruleset, and the "Require branches to be up to date" checkbox stalls the queue because every PR needs a manual rebase before merge. Several required status checks are silently ignored because they are listed under the wrong context name.

## Context

GitHub Rulesets (repo or org level, Settings → Rules → Rulesets) supersede legacy branch protection rules and expose merge queue, deployment branch filtering, and per-bypass-actor configuration in a single unified surface. For example project, a single `main` protection ruleset replaces all legacy branch protection settings and enables merge queue without the legacy UI's limitations. This article covers ruleset configuration, merge queue setup, required check wiring, and bypass actor management.

## Ruleset vs. legacy branch protection

| Feature | Legacy branch protection | Rulesets |
|---|---|---|
| Merge queue support | Limited / separate | Native, per-ruleset |
| Bypass actors | Repository-level only | Per-ruleset (role, team, app, user) |
| Org-level enforcement | Org required workflows (separate) | Org-level rulesets |
| Multiple rule sets | No (one per branch pattern) | Yes, rules stack |
| Import/export | No | JSON export/import |
| REST/GraphQL management | Yes | Yes (newer API) |
| Status: as of 2026 | Not deprecated, but feature-frozen | Recommended path |

Rulesets stack additively — a branch can match multiple rulesets. The strictest applicable rule wins for any given constraint (e.g. if two rulesets both require reviews, the higher count applies).

## Creating the main protection ruleset

Via GitHub UI (Settings → Rules → Rulesets → New ruleset → New branch ruleset):

```
Ruleset name:     main-protection
Enforcement:      Active
Target branches:  Include by name → main
                  (do NOT use wildcards if merge queue is needed)
```

Key toggle groups and their recommended settings for example project:

| Rule group | Setting | Value |
|---|---|---|
| Restrict deletions | Enabled | Prevents `git push origin :main` |
| Require linear history | Enabled | Enforces squash-merge via queue |
| Require merge queue | Enabled | See queue config below |
| Require deployments | Optional | Add production env gate |
| Require signed commits | Enabled if using Sigstore | |
| Require a pull request before merging | Enabled | |
| → Required approvals | 1 | |
| → Dismiss stale reviews on push | Enabled | |
| → Require review from code owners | Enabled | |
| Require status checks | Enabled | |
| → Require branches up to date | Disabled | Queue handles this |
| Block force pushes | Enabled | |

## Required status checks configuration

Status check contexts must match the **exact workflow/job name pair** as it appears in the Actions UI. For a job named `build` in a workflow file named `ci.yml`, the context is `build` (job name only, not file name). For a reusable workflow, the context is `caller-job / called-job`.

```
Required status checks:
  ✓ lint
  ✓ typecheck
  ✓ test
  ✓ build
  ✓ Deploy (staging)        ← matrix job: includes environment suffix
```

The check must report on the `merge_group` event (not just `pull_request`) or the queue will eject PRs with "Required check not found":

```yaml
on:
  pull_request:
  merge_group:    # REQUIRED for merge-queue-gated checks
```

"Require branches to be up to date before merging" should be **off** when merge queue is active — the queue builds a merge group that is already up-to-date; the checkbox would require an additional rebase on the base branch before entering the queue, which is redundant and confusing.

## Merge queue configuration

In the ruleset "Require merge queue" section:

| Setting | Recommended value | Notes |
|---|---|---|
| Merge method | Squash | One commit per PR on main |
| Build concurrency | 3 | Adjust based on CI runner capacity |
| Min PRs to merge | 1 | Don't wait for batches |
| Max PRs per merge | 5 | Cap batch size to limit blast radius |
| Wait time (minutes) | 5 | Wait up to 5 min for more PRs before merging a batch of 1 |
| Status check timeout (min) | 30 | Must exceed worst-case CI duration |
| "Only merge non-failing PRs" | Enabled | Eject individually failing PRs |

Merge queue is only available on rulesets targeting explicit branch names. Wildcard branch patterns (e.g. `*`, `release/*`) do not support merge queue in the ruleset UI.

## Bypass list

Bypass actors are configured per-ruleset and can be: role (admin, maintain), team, GitHub App, or specific user. Unlike legacy branch protection, bypass is not repo-wide — each ruleset has its own bypass list.

```
Bypass list for main-protection ruleset:
  Role: Repository admin           (emergency hotfixes)
  App:  github-actions[bot]        (auto-merge from trusted workflows)
  Team: example project-release-engineers     (release process bypass)
```

Bypass actors can merge without passing required checks or going through the merge queue. Keep the bypass list minimal and audit it quarterly. GitHub Apps in the bypass list can be used from workflows (`GITHUB_TOKEN` from a GitHub App installation), which is the preferred pattern for auto-merge automation.

## Mobile PR review enforcement

GitHub's mobile app supports PR reviews but has historically allowed approval without seeing the full diff on large PRs. Rulesets enforce the same review requirements regardless of review surface. No additional mobile-specific configuration exists — the ruleset's "Required approvals" and "Dismiss stale reviews on push" settings apply to reviews submitted from mobile identically to web or API reviews.

To further enforce review quality regardless of platform, enable "Require review from code owners" — CODEOWNERS assignments ensure that domain-specific reviewers approve changes in their area, which a mobile review must still satisfy.

```
# .github/CODEOWNERS
/workers/           @example project-app/backend-team
/src/               @example project-app/frontend-team
/.github/workflows/ @example project-app/platform-team
```

## Anti-patterns

- Mixing legacy branch protection rules and rulesets on the same branch — they stack but have separate bypass lists and UIs, making audit hard. Migrate fully to rulesets.
- Setting "Require branches to be up to date" AND "Require merge queue" — the rebase requirement is redundant and causes confusion (the queue already does this).
- Using `*` as the ruleset branch pattern when merge queue is needed — wildcard patterns don't support queue.
- Listing required checks by workflow file name (`ci.yml / build`) — the context is the job name only (`build`) unless it is a reusable workflow call.
- Granting bypass to individual user accounts — prefer teams or roles so bypass membership is managed through team membership rather than per-user updates.
- Setting status check timeout shorter than actual CI duration — PRs are ejected from the queue with "timeout" even though CI would have passed if given more time.

## Gotchas

- Rulesets apply to pushes **and** the merge queue's temporary validation branches (`gh-readonly-queue/main/...`). Required checks must fire on `merge_group` events or the queue's temp branch commits never satisfy the ruleset.
- The GitHub mobile app shows merge queue status but cannot add a PR to the queue from mobile as of mid-2026 — users must use the web UI or `gh pr merge --auto`.
- Org-level rulesets are additive on top of repo-level rulesets. An org admin can unknowingly add a required check that breaks the repo's merge queue if the check doesn't support `merge_group`.
- Ruleset export/import uses JSON. The exported JSON omits bypass actor IDs — after import, re-add bypass actors manually.
- A ruleset set to "Evaluate" (not "Active") logs would-be violations without enforcing — useful for testing new checks before enforcement, but easy to forget to switch to Active.

## Verification

```bash
# List rulesets via GitHub CLI
gh api repos/example project-app/example project/rulesets --jq '.[].name'

# Check which rules apply to main
gh api repos/example project-app/example project/rules/branches/main \
  --jq '[.[] | {type, ruleset_source_type}]'

# Verify merge queue status on a PR
gh pr view 123 --json mergeQueueEntry \
  --jq '.mergeQueueEntry | {state, position, estimatedTimeToMerge}'
```

Push a commit to a draft PR targeting `main` and verify:
1. Required checks fire on `pull_request` event.
2. Mark PR ready for review, add to merge queue — confirm checks also fire on `merge_group` event.
3. Merge queue timeline shows "Added → Checks running → Merged" sequence.
4. Attempt a direct push to `main` without bypass — confirm rejection with ruleset name in error message.

## Related

- `github-merge-queue-mechanics.md`
- `github-rulesets-2026.md`
- `github-rulesets-migration-from-branch-protection.md`
- `github-required-status-checks.md`
- `github-auto-merge.md`
- `github-actions-concurrency-groups.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/merging-a-pull-request-with-a-merge-queue
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
