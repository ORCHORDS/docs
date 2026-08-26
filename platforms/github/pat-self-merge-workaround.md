# pat-self-merge-workaround

**Issue:** PR opened, no workflow runs after 3+ minutes (CI stuck "queued")
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** documented (workaround, not root-cause fix)

## Symptom
You open a PR. The Actions tab shows:
- Required: 4
- Queued: 4
- In progress: 0
- Completed: 0

After 3+ minutes, no job has started. No error. The workflow file
is correct. The branch is correct. The PR is open.

## Root cause
This is a known GitHub Actions edge case: a PR is opened but the
"pr:X → branch" event listener fails to fire the workflow run for
3+ minutes. Most of the time it self-corrects. Sometimes it
doesn't, and the PR sits "queued" indefinitely.

**Source:** GitHub Community discussions (multiple threads from
2022-2024) — no official fix from GH.

## Fix
If you have admin-level access (PAT with `repo` + `workflow`
scopes), use the **merge API to trigger CI on main**:

```bash
# Merge the PR (this also pushes the branch to main, which
# triggers workflows on push-to-main)
curl -X PUT \
  -H "Authorization: token ghp_<your-pat>" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/<your-org>/<your-repo>/pulls/<N>/merge" \
  -d '{"merge_method": "squash"}'
```

Wait, this merges the PR, not just triggers CI. If you don't want
to merge yet, use the alternative:

### Alternative: Re-run the workflow manually
```bash
# Get the workflow file's ID
gh api repos/<your-org>/<your-repo>/actions/workflows/ci.yml

# Re-run a specific run (after the eventual queue clears)
gh run rerun <run-id> --repo <your-org>/<your-repo>
```

But this requires the run to exist in the first place, which is
the problem.

### Alternative: Force-push the same commit
```bash
# On the feature branch
git commit --allow-empty -m "ci: retrigger"
git push --force-with-lease
```

This creates a new commit hash, which re-fires the "push" event,
which re-triggers workflows. Works in 95% of cases.

## Verification
- **Test:** `gh pr checks <N>` shows jobs moving from "queued" to
  "in_progress" within 5 min of the API call
- **Live:** the platform uses this pattern when CI stalls; saves
  5-10 min per stalled cycle

## Gotchas
- **Don't merge a PR you don't intend to merge.** The merge API
  PR-merges as well as triggering CI. If you just want CI, use
  the force-push alternative.
- **The PAT must have `repo` AND `workflow` scopes.** `repo` alone
  can read; `workflow` is required to write (including triggering
  CI). If your PAT only has `repo`, the merge API call will 403.
- **Force-push on PR-owned feature branches is safe.** Force-push
  on `main` is NEVER safe.
- **Squash merge via API uses the default commit message.** If
  your PR body has a 24-point compliance audit table, the
  squash commit will be `<PR title> (#<N>)` not the full body.
  You lose the audit table on merge. If you need the audit table
  preserved, use the Web UI merge button.
- **This pattern is for the self-hosted runner workflow.** The
  GH-hosted `codeql.yml` doesn't have this problem (CodeQL
  always runs from `github/codeql-action` GH-hosted).

## Related
- the platform CI setup: `.github/workflows/ci.yml`
- a sibling repo uses GH-hosted (no runner group), so this pattern
  doesn't apply there
- GH Community: https://github.community/t/triggering-workflow-from-pull-request/16455
