# github-rulesets-migration-from-branch-protection

**Issue:** Migrating from classic branch protection rules to repository rulesets (auto-migration tool shipped 2026) without losing required reviews, CODEOWNERS enforcement, or status checks
**Date:** 2026-08-12
**Status:** documented

## Context

GitHub has been pushing rulesets as the successor to branch protection rules
since 2023. In 2026 the platform shipped a one-click **automatic migration**
tool that converts existing branch protection rules into rulesets. This KB
covers the migration path, what translates correctly, what breaks, and how to
do it safely.

For how to USE rulesets once migrated, see `github-rulesets-2026.md`. This
article is specifically about the migration.

## Symptom

- After migrating, "Require pull request reviews" no longer enforces the
  required reviewer count — anyone can merge.
- After migrating, CODEOWNERS-based required reviews stopped triggering.
- After migrating, previously-required status checks are no longer required,
  and the branch shows "no required checks."
- After migrating, admins can no longer push directly (they could before).
- The migration tool reports "X rules migrated" but some branches now have
  zero protection.

## The migration path

### Option A: Automatic migration (new in 2026)

Repo → Settings → Branches → "Migrate to rulesets" button.

Or via API:

```bash
# List current branch protection rules first (backup!)
gh api repos/:owner/:repo/branches/main/protection > backup-main-protection.json

# Trigger migration (org-level, applies to all repos)
gh api -X POST orgs/:org/migrations/rulesets \
  --field source="branch_protection"
```

The tool creates one ruleset per branch-protection rule and disables the
original branch protection. Both exist in parallel during migration; the
ruleset wins when both apply.

### Option B: Manual migration (safer for production repos)

1. Read the current branch protection:
   ```bash
   gh api repos/:owner/:repo/branches/main/protection | jq .
   ```
2. Create the equivalent ruleset via the UI or API:
   ```bash
   gh api -X POST repos/:owner/:repo/rulesets \
     --field name="main-branch-protection" \
     --field target="branch" \
     --field conditions[ref_name][include][]="refs/heads/main" \
     --field enforcement="active"
   ```
3. Verify the ruleset behaves correctly on a test branch.
4. Delete the old branch protection rule.

## What translates (and what doesn't)

| Branch protection rule | Ruleset equivalent | Notes |
|---|---|---|
| Require pull request reviews | "Require a pull request before merging" | **Required review count must be re-entered.** The auto-migrator sometimes drops to 0. Verify post-migration. |
| Require review from Code Owners | "Require review from Code Owners" checkbox inside the pull-request rule | Frequently **unchecked** after auto-migration. Re-check it manually. |
| Require status checks to pass | "Require status checks to pass" | **Check names must be re-added.** The migrator lists them but stale/wildcard checks (e.g. `*`) don't carry over. |
| Require branches to be up to date | "Require branches to be up to date before merging" | Carries over cleanly. |
| Require conversation resolution | "Require conversation resolution before merging" | Carries over cleanly. |
| Require signed commits | "Require signed commits" | Carries over cleanly. |
| Require linear history | "Require linear history" | Carries over cleanly. |
| Restrict who can push | "Restrict creations / updates / deletions" | Maps to a different shape. Verify the user/team list transferred. |
| Allow force pushes / deletions | Bypass actors list | Force-push allow-list becomes a bypass actor with `force_push` scope. |
| Do not allow bypassing the above | (no equivalent in classic) | New in rulesets — explicit bypass actors. |

## Gotchas

- **The auto-migrator can silently drop required review counts to 0.** Always
  re-verify `pull_request[row][required_reviewers]` after migration. This is
  the #1 migration bug teams hit.
- **CODEOWNERS enforcement does NOT auto-carry.** The "Require review from
  Code Owners" checkbox inside the pull-request rule must be re-ticked. A repo
  that previously required a CODEOWNERS review may allow any-approver merges
  after migration.
- **Required status checks by display name are brittle.** If a check was
  required by its display name and a renamed/obsoleted job no longer posts
  that exact name, the ruleset blocks merges indefinitely. Prefer the check's
  `job_id`-based name where possible.
- **Admins can bypass rulesets unless you explicitly remove "Bypass list"
  entries.** In classic branch protection, "Do not allow bypassing" was a
  single checkbox. In rulesets, bypass actors are an explicit list — an empty
  list means nobody can bypass. Verify your intent matches.
- **Rulesets are layered, not merged.** If a repo has a ruleset from the org
  AND one from the repo, the most restrictive wins (they don't combine
  permissively). A migrated repo-ruleset plus an existing org-ruleset can
  unexpectedly double-require reviews.
- **Ruleset history is separate from branch-protection history.** Audit-log
  queries for branch-protection events won't show post-migration changes. Use
  `action:ruleset.create` / `ruleset.update` in audit log queries instead.
- **The migration tool creates one ruleset per protected branch.** If you had
  protection on `main`, `develop`, and `release/*`, you get three rulesets.
  Consolidate into a single ruleset with multiple `ref_name` includes to
  reduce sprawl.
- **Rulesets support `enforcement: "evaluate"` (audit mode).** During
  migration, set new rulesets to `evaluate` first to spot violations in audit
  logs before switching to `active`. The auto-migrator uses `active` by
  default — override it.
- **Forks.** Branch protection never applied to forks cleanly. Rulesets have
  the same limitation. If you rely on fork-based contribution, test the merge
  flow on a real fork after migration.

## Post-migration verification script

```bash
REPO="owner/repo"
# For each protected branch, confirm the ruleset still requires N reviews
for branch in main develop; do
  echo "=== $branch ==="
  gh api "repos/$REPO/rules/branches/$branch" \
    | jq '.[] | {name, enforcement, rules: [.rules[] | select(.type=="pull_request") | {type, parameters: .parameters}]}'
done
```

Look for `required_reviewers > 0` and `required_code_owner_reviews: true`. If
either is missing, edit the ruleset before relying on it.

## Diagnostic checklist

- [ ] Exported old branch protection as JSON backup before migrating.
- [ ] Verified required reviewer count carried over (not 0).
- [ ] Verified "Require review from Code Owners" is checked.
- [ ] Verified required status check names are present and not stale.
- [ ] Confirmed bypass-actor list matches intent (empty = strict).
- [ ] Ran in `evaluate` mode for at least one sprint before `active`.
- [ ] Audit-log queries updated to query `ruleset.*` actions.

## References

- Changelog: "Automatically migrate branch protection rules to repository
  rulesets" (2026)
- Related KB: `github-rulesets-2026.md`, `branch-protection-and-codeowners.md`,
  `github-required-status-checks.md`
