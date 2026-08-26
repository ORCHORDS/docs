# Git Notes: Collaborative Annotations Workflow

- Date: 2026-08-22
- Author: example.com
- Status: production

## Attaching Team Metadata to Commits Without Rewriting History

Git commits are immutable once pushed: you cannot add deployment timestamps, review sign-offs, or QA annotations to them without rewriting the SHA and invalidating everyone else's history. Git notes solve this cleanly. A note is a blob stored under `refs/notes/<namespace>` that maps any object SHA (commit, blob, tag) to arbitrary text. The note lives completely outside the commit DAG, so the commit SHA never changes.

Notes are invisible by default in `git log` output, which makes them a low-noise sidecar for machine-readable metadata: deployment manifests, test-result digests, security-scan summaries, or reviewer sign-offs that CI should verify before a release is promoted.

Because notes refs are not fetched or pushed by default, teams must opt in with explicit refspecs. This makes notes safe to experiment with locally before rolling them out to the shared remote.

## Context

Stack: Cloudflare Workers monorepo, GitHub Actions CI, Node 22, pnpm workspaces. Notes are used to record which Workers were deployed at each commit and to surface that data during rollback decisions.

## Writing and Reading Notes

The default namespace is `refs/notes/commits`. Use `--ref` to isolate domains so different tools do not collide.

```bash
# Add a note to HEAD (default namespace)
git notes add -m "QA signed off: @alice 2026-08-22"

# Add a note to a specific commit using a custom namespace
git notes --ref=refs/notes/deployments add -m \
  '{"worker":"api-gateway","env":"production","ts":"2026-08-22T14:00:00Z"}' \
  abc1234

# Amend an existing note (replaces it)
git notes --ref=refs/notes/deployments add -f -m \
  '{"worker":"api-gateway","env":"production","ts":"2026-08-22T14:30:00Z","rollback":false}' \
  abc1234

# Show a note for a commit
git notes --ref=refs/notes/deployments show abc1234

# List all annotated commits in a namespace
git notes --ref=refs/notes/deployments list

# Display notes inline with git log
git log --notes=refs/notes/deployments --format="%H %s%n%N"
```

## Pushing and Fetching Notes Refs

Notes refs are not included in the standard `refs/heads/*` or `refs/tags/*` fetch/push globs. Every participant and every CI job must configure the refspecs explicitly.

```bash
# Push notes to remote
git push origin refs/notes/deployments

# Fetch notes from remote
git fetch origin refs/notes/deployments:refs/notes/deployments

# Persist the refspecs in .git/config so plain git fetch/push picks them up
git config --add remote.origin.fetch \
  '+refs/notes/deployments:refs/notes/deployments'
git config --add remote.origin.push \
  'refs/notes/deployments'
```

For repository-wide defaults, add the refspecs to the repo's shared config (checked-in `.gitconfig` or CI environment bootstrap):

```bash
# CI bootstrap step (run once per runner before any git fetch)
git config --global --add remote.origin.fetch \
  '+refs/notes/*:refs/notes/*'
```

## CI That Reads Notes for Deployment Metadata

The following GitHub Actions workflow reads the deployment note on the merge commit of a release PR and uses it to gate promotion to production.

```yaml
# .github/workflows/promote-to-production.yml
name: Promote to Production

on:
  workflow_dispatch:
    inputs:
      commit_sha:
        description: "Merge commit SHA to promote"
        required: true

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Fetch deployment notes
        run: |
          git fetch origin '+refs/notes/deployments:refs/notes/deployments'

      - name: Read and validate deployment note
        run: |
          NOTE=$(git notes --ref=refs/notes/deployments show \
            "${{ github.event.inputs.commit_sha }}" 2>/dev/null || echo "")
          if [[ -z "$NOTE" ]]; then
            echo "::error::No deployment note found for ${{ github.event.inputs.commit_sha }}"
            exit 1
          fi
          echo "DEPLOY_NOTE=$NOTE" >> "$GITHUB_ENV"
          ROLLBACK=$(echo "$NOTE" | jq -r '.rollback // false')
          if [[ "$ROLLBACK" == "true" ]]; then
            echo "::error::Commit is flagged as a rollback target — cannot promote"
            exit 1
          fi

      - name: Attach promotion note
        env:
          GIT_AUTHOR_NAME: "ci-bot"
          GIT_AUTHOR_EMAIL: "ci@example.com"
          GIT_COMMITTER_NAME: "ci-bot"
          GIT_COMMITTER_EMAIL: "ci@example.com"
        run: |
          PROMOTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
          git notes --ref=refs/notes/deployments add -f -m \
            "$(echo "$DEPLOY_NOTE" | jq ". + {\"promoted_at\": \"$PROMOTED_AT\"}")" \
            "${{ github.event.inputs.commit_sha }}"
          git push origin refs/notes/deployments
```

## Notes and Rebasing

Notes are the Achilles heel of any workflow that rewrites history. When `git rebase` produces a new commit SHA, the original note stays mapped to the old (now-orphaned) SHA. The new commit has no note.

```bash
# After a rebase, copy notes from old SHAs to new SHAs.
# git rebase --notes-ref is NOT a built-in flag; you must do it manually.

OLD_SHA=abc1234
NEW_SHA=$(git rev-parse HEAD)

# Read the old note
OLD_NOTE=$(git notes --ref=refs/notes/deployments show "$OLD_SHA" 2>/dev/null)

if [[ -n "$OLD_NOTE" ]]; then
  git notes --ref=refs/notes/deployments add -f -m "$OLD_NOTE" "$NEW_SHA"
  git notes --ref=refs/notes/deployments remove "$OLD_SHA"
fi
```

Set `notes.rewriteRef` to have Git attempt this automatically for supported operations:

```bash
git config notes.rewriteRef "refs/notes/*"
git config notes.rewrite.rebase true
git config notes.rewrite.amend true
```

This covers `git rebase` and `git commit --amend` but not `git filter-branch` or `git filter-repo`.

## Anti-patterns

- Storing secrets or PII in notes: notes refs can be fetched by anyone with repo read access, same as commits
- Using the default `refs/notes/commits` namespace for machine data: one `git notes add` from a human editor will clobber CI data silently
- Relying on notes surviving a force-push rewrite: SHA remapping is manual; automate it or ban force-pushes on main
- Not adding fetch refspecs in CI: notes will never appear in a fresh clone unless the refspec is explicitly configured
- Appending to notes with `-m` in a loop: each `-m` replaces the entire note; use `-F` with a temp file or pipe if you need structured JSON

## Gotchas

- `git log --notes` only displays notes from `refs/notes/commits` by default; use `--notes=<ref>` for custom namespaces
- `git show <sha>` does not display notes; use `git notes show <sha>`
- Notes are per-object, not per-branch; a cherry-picked commit retains its original note
- GitHub's web UI does not render notes; visibility is CLI and API only
- Merging notes from two remotes with conflicting notes on the same SHA requires a notes merge strategy (`git notes merge --strategy=cat_sort_uniq`)

## Verification

```bash
# Confirm note is attached and readable
SHA=$(git rev-parse HEAD)
git notes --ref=refs/notes/deployments show "$SHA"

# Confirm note survives a push/fetch round-trip
git push origin refs/notes/deployments
git fetch origin '+refs/notes/deployments:refs/notes/deployments'
git notes --ref=refs/notes/deployments show "$SHA"

# Enumerate all annotated SHAs in the namespace
git notes --ref=refs/notes/deployments list | wc -l
```

## Related

- [git-cleanup-2026.md](git-cleanup-2026.md)
- [conventional-commits-2026.md](conventional-commits-2026.md)
- [ci-cd-pipeline-2026.md](ci-cd-pipeline-2026.md)
- [git-reflog-2026.md](git-reflog-2026.md)
- [release-please-semantic-release.md](release-please-semantic-release.md)

## Sources

- https://git-scm.com/docs/git-notes
- https://git-scm.com/docs/gitrepository-layout
- Pro Git Book, Chapter 10.3 — Git References
- GitHub Actions documentation: actions/checkout fetch-depth
