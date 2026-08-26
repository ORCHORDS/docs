# Git Refspec Advanced Fetch Push Patterns

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Workers team needs to: (a) fetch GitHub pull-request heads into a local namespace for automated testing without checking them out; (b) push release artifacts to a `releases/` ref namespace without publishing a branch; (c) keep a mirror remote in sync with the authoritative origin. The default `git fetch origin` and `git push origin HEAD` are insufficient because they operate only on branches and tags.

## Context
A *refspec* is Git's mapping expression `[+]<src>:<dst>` that tells fetch or push which objects to move and where to store them. The optional `+` prefix forces the update even if it is not a fast-forward. `src` and `dst` are fully qualified ref paths (e.g. `refs/heads/main`, `refs/pull/*/head`). Refspecs can be stored permanently in `.git/config` under `[remote "<name>"]` or passed one-off on the command line. Understanding refspecs unlocks patterns impossible with the high-level `--track` and `--set-upstream` shorthands.

## Refspec syntax fundamentals

```bash
# Canonical form
# [+]<src>:<dst>

# Fetch: copy remote ref "refs/heads/main" into local "refs/remotes/origin/main"
git fetch origin 'refs/heads/main:refs/remotes/origin/main'

# Push: push local HEAD to remote "refs/heads/my-feature"
git push origin 'HEAD:refs/heads/my-feature'

# Delete a remote ref (empty src)
git push origin ':refs/heads/stale-branch'
# Equivalent shorthand:
git push origin --delete stale-branch

# Force-push (non-fast-forward allowed)
git push origin '+HEAD:refs/heads/main'

# Wildcard glob — push all release/* branches to remote
git push origin 'refs/heads/release/*:refs/heads/release/*'
```

## Fetching GitHub pull-request heads into a local namespace

GitHub exposes every PR head at `refs/pull/<N>/head` and the merge commit (if one exists) at `refs/pull/<N>/merge`. These are not fetched by the default refspec.

```bash
# One-off: fetch a single PR into a local ref
git fetch origin 'refs/pull/42/head:refs/pr/42'
git checkout refs/pr/42       # detached HEAD for review

# Permanent config: fetch ALL PR heads automatically
git config --add remote.origin.fetch '+refs/pull/*/head:refs/remotes/origin/pr/*'
git fetch origin
git branch -r | grep 'origin/pr/'
# origin/pr/1
# origin/pr/42
# origin/pr/87

# Check out a PR as a local branch
git checkout -b pr-42 origin/pr/42
```

```yaml
# .github/workflows/pr-integration-test.yml
# Fetch PR head directly — useful when the workflow is triggered by
# an external event that only provides the PR number, not the SHA.
name: PR Integration Test
on:
  workflow_dispatch:
    inputs:
      pr_number:
        required: true
        type: number

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - name: Fetch PR head
        run: |
          PR="${{ inputs.pr_number }}"
          git fetch origin "refs/pull/${PR}/head:refs/pr/${PR}"
          git checkout "refs/pr/${PR}"
      - run: pnpm install --frozen-lockfile
      - run: pnpm test
```

## Pushing to a custom ref namespace (release snapshots)

```bash
# Push the current HEAD to a dated snapshot ref without creating a branch
DATE=$(date -u +%Y%m%dT%H%M%SZ)
git push origin "HEAD:refs/snapshots/workers/${DATE}"

# List snapshot refs
git ls-remote origin 'refs/snapshots/*'

# Fetch all snapshots locally
git fetch origin '+refs/snapshots/*:refs/snapshots/*'
git log --oneline refs/snapshots/workers/20260823T120000Z
```

```yaml
# Publish a snapshot ref on every deploy to production
- name: Tag snapshot ref
  env:
    CLOUDFLARE_DEPLOY_SHA: ${{ github.sha }}
  run: |
    DATE=$(date -u +%Y%m%dT%H%M%SZ)
    git push origin \
      "${CLOUDFLARE_DEPLOY_SHA}:refs/snapshots/prod/${DATE}"
```

## Mirror remote: keeping a backup in sync

```bash
# Add a mirror push remote (pushes all refs)
git remote add backup git@backup-host:workers-monorepo.git
git config remote.backup.mirror true        # sets push refspec to +refs/*:refs/*

# Push everything: branches, tags, notes, custom namespaces
git push backup

# Verify the mirror matches origin
git ls-remote origin | sort > /tmp/origin-refs.txt
git ls-remote backup | sort > /tmp/backup-refs.txt
diff /tmp/origin-refs.txt /tmp/backup-refs.txt
```

```yaml
# .github/workflows/mirror-sync.yml
name: Mirror Sync
on:
  push:
    branches: ['**']
    tags: ['**']

jobs:
  mirror:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true
      - name: Push to backup mirror
        run: |
          git remote add backup "${{ secrets.BACKUP_REMOTE_URL }}"
          git push backup '+refs/*:refs/*'
```

## Per-remote stored refspecs in .git/config

```ini
# .git/config — store non-default fetch mappings permanently
[remote "origin"]
    url = git@github.com:example-org/example-repo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
    fetch = +refs/pull/*/head:refs/remotes/origin/pr/*
    fetch = +refs/tags/*:refs/tags/*
    fetch = +refs/notes/*:refs/notes/*

[remote "staging"]
    url = git@github.com:example-org/example-repo.git
    push  = refs/heads/main:refs/heads/deploy/production
    push  = refs/heads/staging:refs/heads/deploy/staging
```

## TypeScript: validating refspec syntax before executing

```typescript
// scripts/validate-refspec.ts
const REFSPEC_RE =
  /^[+]?(?:[a-zA-Z0-9\-_./\*]+)?:(?:[a-zA-Z0-9\-_./\*]+)?$/;

export function validateRefspec(refspec: string): void {
  if (!REFSPEC_RE.test(refspec)) {
    throw new Error(`Invalid refspec: "${refspec}". Expected [+]<src>:<dst>`);
  }
  const [src, dst] = refspec.replace(/^\+/, "").split(":");
  if (src.includes("*") !== dst.includes("*")) {
    throw new Error(
      `Glob mismatch in refspec "${refspec}": both src and dst must use * or neither.`
    );
  }
}

// Usage in a deploy script
const refspec = `HEAD:refs/snapshots/prod/${new Date().toISOString()}`;
validateRefspec(refspec);
```

## Anti-patterns
- Using `git push origin HEAD` and expecting it to update a remote branch that has a different name — Git will create a new branch matching the local branch name unless a refspec is specified.
- Storing push refspecs with `+` (force) in `.git/config` permanently — a simple `git push` then silently force-pushes all matched refs.
- Fetching `refs/pull/*/merge` in CI for testing — the merge commit is computed by GitHub and may be stale; prefer `refs/pull/*/head` for the exact PR state.
- Wildcard push refspecs on a mirror remote pointed at an untrusted fork — all local refs including secrets-leaking notes refs are pushed.
- Confusing `git fetch origin main` (which uses configured refspecs) with `git fetch origin refs/heads/main` (which does an exact match) — they behave identically only when the default mapping is in place.

## Gotchas
- GitHub's `refs/pull/*/head` refs are read-only from the API perspective; you cannot push to them even with admin access.
- `git push origin ':refs/heads/foo'` deletes the remote branch; `git push origin ':refs/tags/v1.0'` deletes the tag. Both are permanent — there is no recycle bin.
- When a refspec contains `*`, Git does a glob on the ref list at negotiation time; very large repos with thousands of PRs may have slow `git ls-remote` calls.
- `git config remote.origin.fetch` can have multiple lines — `git config --add` appends; `git config --replace-all` replaces all occurrences. Accidentally doubling the default `+refs/heads/*:refs/remotes/origin/*` line causes duplicate fetch but is otherwise harmless.
- In GitHub Actions, `actions/checkout` resets `remote.origin.fetch` to its own minimal default; re-add custom fetch refspecs as a post-checkout step if needed.

## Verification
```bash
# Confirm custom PR fetch refspec is stored
git config --get-all remote.origin.fetch

# Fetch and verify PR refs land in expected namespace
git fetch origin
git for-each-ref --format='%(refname)' refs/remotes/origin/pr/ | head -5

# Verify snapshot ref exists on remote
git ls-remote origin 'refs/snapshots/*'

# Dry-run a push refspec without actually pushing
git push --dry-run --verbose origin 'HEAD:refs/snapshots/test'
```

## Related
- [git-fetch-atomic-ref-update-contract.md](git-fetch-atomic-ref-update-contract.md)
- [git-fetch-negotiation-algorithm-evaluation.md](git-fetch-negotiation-algorithm-evaluation.md)
- [git-bundle-disaster-recovery-offline-clone.md](git-bundle-disaster-recovery-offline-clone.md)
- [git-tag-semantic-versioning-workers-deploy-gates.md](git-tag-semantic-versioning-workers-deploy-gates.md)
- [git-hidden-ref-namespace-policy.md](git-hidden-ref-namespace-policy.md)

## Sources
- https://git-scm.com/docs/gitrevisions#Documentation/gitrevisions.txt-emltrefnamegtemegemmasterememheadsmasterememrefsheadsmasterem
- https://git-scm.com/book/en/v2/Git-Internals-The-Refspec
- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/checking-out-pull-requests-locally
- https://git-scm.com/docs/git-push#Documentation/git-push.txt-ltrefspecgt82308203
