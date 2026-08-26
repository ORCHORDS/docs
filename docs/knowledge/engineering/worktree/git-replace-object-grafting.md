# Git Replace Object Grafting for History Surgery

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You imported a legacy codebase mid-project and want CI tools like `git log`, coverage archaeology, and blame to treat it as one continuous history — without rewriting existing commits and invalidating open PRs or deployed tag SHAs.

## Context
Cloudflare Workers monorepos often begin as a migration from a Pages site or an older Node server; the true project history lives in a different repository. `git replace` creates a ref under `refs/replace/` that causes Git to substitute one object for another in traversal commands, effectively grafting two histories together without altering any object's SHA. This is transparent to all read operations but requires explicit `--push-option` or a separate ref push to share with CI.

## How git replace works
A replace ref maps `<original-SHA>` → `<replacement-SHA>`. When Git traverses history and encounters the original, it silently uses the replacement instead. The original objects are unchanged on disk; the substitution only applies when `GIT_NO_REPLACE_OBJECTS` is unset.

```bash
# Verify the two repos share no common ancestor
git log --oneline origin/main | tail -1
# e.g. a1b2c3d (root commit of new repo)

git log --oneline legacy/main | tail -1
# e.g. f9e8d7c (root commit of legacy repo)

# Fetch legacy history into the new repo as a remote
git remote add legacy git@github.com:example-org/example-repo.git
git fetch legacy

# Create the graft: make the new root's parent the legacy tip
git replace --graft a1b2c3d f9e8d7c

# Confirm the synthetic parentage
git log --oneline --graph legacy/main..HEAD | head -10
```

## Sharing replace refs with CI
Replace refs are stored under `refs/replace/` and are not pushed by default. GitHub Actions and Cloudflare Workers CI pipelines must be told to fetch and push them explicitly.

```yaml
# .github/workflows/history-aware-ci.yml
name: History-Aware CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history required for replace traversal

      - name: Fetch replace refs
        run: |
          git fetch origin '+refs/replace/*:refs/replace/*'

      - name: Verify grafted history depth
        run: |
          DEPTH=$(git rev-list --count HEAD)
          echo "Total visible commits: $DEPTH"
          # Fail if replace refs are missing and history looks truncated
          if [ "$DEPTH" -lt 100 ]; then
            echo "::error::Replace refs may not have been fetched — history too shallow"
            exit 1
          fi
```

```bash
# Push replace refs to origin so all collaborators share the view
git push origin 'refs/replace/*'
```

## Practical grafting scenarios

### Linearising a detached import commit
When you `git commit --allow-empty "Import legacy codebase"` and then add files, that import commit has no parent. Graft the legacy tip as its parent so blame flows back through the old code.

```bash
IMPORT_SHA=$(git log --oneline --diff-filter=A -- 'workers/**' | tail -1 | awk '{print $1}')
LEGACY_TIP=$(git rev-parse legacy/main)
git replace --graft "$IMPORT_SHA" "$LEGACY_TIP"
```

### Replacing a broken merge commit
A previous merge was made with `-s ours` and discarded all changes from one side. Replace the broken merge object with a corrected one produced by `git commit-tree`:

```bash
CORRECT_TREE=$(git merge-tree --write-tree HEAD feature/correct-merge | head -1)
NEW_MERGE=$(git commit-tree "$CORRECT_TREE" \
  -p main -p feature/correct-merge \
  -m "fix: correct merge preserving both sides")
git replace "$BROKEN_MERGE_SHA" "$NEW_MERGE"
```

## Wrangler deploy pipeline integration
If your release script reads `git describe` to embed a version string in the Worker bundle, the grafted history makes tags from the legacy repo visible:

```typescript
// scripts/version.ts
import { execSync } from "node:child_process";

export function getWorkerVersion(): string {
  // git describe traverses replace refs automatically
  const raw = execSync("git describe --tags --always --dirty").toString().trim();
  // Produces e.g. "v2.1.0-14-gabcd123" even when the tag is in grafted history
  return raw;
}
```

```jsonc
// wrangler.jsonc
{
  "vars": {
    "WORKER_VERSION": "$WORKER_VERSION"
  }
}
```

```bash
# deploy.sh
export WORKER_VERSION=$(npx tsx scripts/version.ts)
wrangler deploy --env production
```

## Anti-patterns
- Committing replace refs to `.git/config` via `[transfer] hideRefs` — this silently hides the graft from fetches and confuses every collaborator.
- Using `git replace` as a substitute for an actual `git filter-repo` rewrite when you genuinely need to publish a clean, reviewable linear history on a public repo.
- Forgetting `GIT_NO_REPLACE_OBJECTS=1` when you need to inspect real object identity (e.g., verifying signatures on the original commits).
- Pushing replace refs without documenting them — engineers who clone fresh will see a mysteriously deep history with no explanation.
- Relying on replace refs to fix security-sensitive history; `git filter-repo` is the correct tool because replace leaves originals accessible.

## Gotchas
- `git clone` does NOT transfer `refs/replace/*` by default; new contributors get a broken view unless the remote's `uploadpack.allowAnySHA1InWant` is enabled or you document the fetch step.
- `git bundle` excludes replace refs unless you explicitly include the refspec `'refs/replace/*'` in the bundle command.
- GitHub's web UI does not honour replace refs — the commit graph and blame pages always show raw object parentage.
- `git gc` will not remove the original (replaced) object as long as the replace ref points to it; the replaced object stays reachable.
- Some Git hosting providers strip `refs/replace/*` on push for security reasons; test this before relying on shared grafts.

## Verification
```bash
# Without replace refs
GIT_NO_REPLACE_OBJECTS=1 git log --oneline | wc -l
# e.g. 312

# With replace refs (grafted history)
git log --oneline | wc -l
# e.g. 1847  (includes legacy commits)

# Confirm the replace ref exists
git for-each-ref refs/replace/
# refs/replace/a1b2c3d...  commit  <SHA of legacy tip>

# Blame should now reach into legacy history
git blame workers/src/index.ts | head -5
```

## Related
- [git-bundle-disaster-recovery-offline-clone.md](git-bundle-disaster-recovery-offline-clone.md)
- [git-filter-repo-sensitive-data-removal.md](git-filter-repo-sensitive-data-removal.md)
- [git-log-follow-file-history-workers.md](git-log-follow-file-history-workers.md)

## Sources
- https://git-scm.com/docs/git-replace
- https://git-scm.com/book/en/v2/Git-Tools-Replace
- https://github.blog/2021-03-03-tips-for-reading-git-history/
