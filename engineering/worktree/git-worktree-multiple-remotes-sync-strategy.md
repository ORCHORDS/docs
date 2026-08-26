# Git Worktree Multiple Remotes Sync Strategy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project (example.com) maintains a primary GitHub origin, an internal Cloudflare-hosted mirror for CI isolation, and occasionally forks from upstream OSS projects. Engineers using `git worktree` for parallel branch work hit fetch/push ambiguity when multiple remotes share branch names. Tracking which worktree is wired to which remote — and keeping all mirrors in sync — breaks down without a disciplined strategy.

---

## Context

`git worktree` checks out branches into sibling directories but shares the single `.git` object store and remote configuration. When remotes diverge (e.g., `origin` and `upstream` both have `main`), fetch/push operations in a worktree silently target whichever remote the local tracking branch points to, causing stale deploys or lost commits. A structured multiple-remote protocol prevents this by making tracking explicit per worktree and automating cross-remote sync through CI.

---

## Remote Configuration Convention

Standardise remote names across all example project repos so every engineer's worktree behaves identically:

```bash
# Primary GitHub remote (default push target)
git remote add origin  git@github.com:example project-app/example project.git

# Internal Cloudflare Pages CI mirror (read-write for deploy hooks)
git remote add cf-mirror  git@gitlab.internal.example.com:example project/example project.git

# Upstream OSS dependency (read-only)
git remote add upstream  git@github.com:some-oss/dependency.git

# Verify
git remote -v
```

Set the default push target at repo level so bare accidental `git push` never hits the mirror:

```bash
git config remote.pushDefault origin
```

---

## Worktree Creation with Explicit Tracking

When creating a worktree for a feature branch that needs to push to a specific remote, set the upstream explicitly at creation time:

```bash
# Create worktree tracking origin
git worktree add ../example project-feat-payments -b feat/payments --track origin/main

# Create worktree tracking cf-mirror for a deploy-validation branch
git worktree add ../example project-cf-staging -b deploy/staging --track cf-mirror/main
```

Confirm tracking inside the worktree:

```bash
cd ../example project-feat-payments
git branch -vv
# feat/payments abc1234 [origin/main: ahead 3] feat: add stripe handler
```

---

## Cross-Remote Fetch Script

Keeping all remotes up-to-date before branching prevents divergence. Run this from the main worktree (not a linked one):

```bash
#!/usr/bin/env bash
# scripts/sync-remotes.sh
set -euo pipefail

REMOTES=(origin cf-mirror upstream)

for remote in "${REMOTES[@]}"; do
  echo "==> Fetching ${remote}..."
  git fetch "${remote}" --prune --tags
done

# Check if cf-mirror/main lags origin/main
ORIGIN_SHA=$(git rev-parse origin/main)
MIRROR_SHA=$(git rev-parse cf-mirror/main 2>/dev/null || echo "missing")

if [[ "${ORIGIN_SHA}" != "${MIRROR_SHA}" ]]; then
  echo "WARNING: cf-mirror/main is behind origin/main. Run: git push cf-mirror main"
fi
```

---

## Mirror Push CI Job

Push to `cf-mirror` after every merge to `main` on GitHub Actions, keeping the Cloudflare CI mirror fresh:

```yaml
# .github/workflows/sync-cf-mirror.yml
name: Sync CF Mirror

on:
  push:
    branches: [main]

jobs:
  mirror:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Push to internal mirror
        env:
          CF_MIRROR_KEY: ${{ secrets.CF_MIRROR_DEPLOY_KEY }}
        run: |
          mkdir -p ~/.ssh
          echo "${CF_MIRROR_KEY}" > ~/.ssh/cf_mirror_key
          chmod 600 ~/.ssh/cf_mirror_key
          git remote add cf-mirror git@gitlab.internal.example.com:example project/example project.git
          GIT_SSH_COMMAND="ssh -i ~/.ssh/cf_mirror_key -o StrictHostKeyChecking=no" \
            git push cf-mirror HEAD:main --tags
```

---

## Upstream Rebase Workflow in a Worktree

When pulling upstream OSS changes into a worktree without touching the main checkout:

```bash
# Create an integration worktree
git worktree add ../example project-upstream-sync -b chore/upstream-sync

cd ../example project-upstream-sync

# Fetch upstream and rebase
git fetch upstream
git rebase upstream/main

# Resolve conflicts here, then push to origin for PR
git push origin chore/upstream-sync
```

The main worktree remains clean and unblocked during the rebase work.

---

## Worktree Remote Isolation Check

Before pushing from any worktree, confirm the target remote is correct:

```bash
#!/usr/bin/env bash
# scripts/worktree-remote-check.sh
WORKTREE_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "DETACHED")
TRACKING=$(git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>/dev/null || echo "none")
PUSH_REMOTE=$(git remote get-url "$(git config branch."${WORKTREE_BRANCH}".remote 2>/dev/null || echo origin)" 2>/dev/null || echo "unknown")

echo "Branch:    ${WORKTREE_BRANCH}"
echo "Tracking:  ${TRACKING}"
echo "Push URL:  ${PUSH_REMOTE}"
```

Wire this as a `pre-push` hook in each worktree's `.git/config` hooks path override (worktrees support `core.hooksPath` scoped to that checkout).

---

## Anti-patterns

- **Sharing a worktree between two remotes without explicit tracking** — `git push` will default to `origin` even when the worktree was meant for `cf-mirror`, silently skipping the internal CI pipeline.
- **Running `git remote add` inside a linked worktree** — remotes are stored in the shared `.git/config`; add them from the main worktree to avoid confusion about where the config lives.
- **Relying on `git push --all` across remotes in CI** — this pushes every local branch to every remote; use targeted `git push <remote> <refspec>` in automation.
- **Tag pollution** — pushing tags from a worktree to both remotes without checking for tag conflicts causes `--tags` to fail silently on the duplicate.

---

## Gotchas

- `git worktree add --track` requires the remote branch to already exist; if the remote branch is new, create it with `git push -u origin <branch>` first, then add the worktree.
- `git fetch --all` inside a linked worktree works but uses the shared object store — large upstream fetches block other worktrees' index operations momentarily on single-disk setups.
- `GIT_DIR` is set differently inside worktrees (`<repo>/.git/worktrees/<name>` vs `<repo>/.git`); scripts that hard-code `.git` paths break. Use `git rev-parse --git-dir` instead.
- SSH key multiplexing (`ControlMaster`) must be configured per remote host in `~/.ssh/config` when pushing to multiple remotes in rapid succession, or connections race.

---

## Verification

```bash
# 1. Confirm all remotes resolve correctly
git remote -v | sort

# 2. Confirm worktree tracking
git worktree list --porcelain | grep -E "^(worktree|branch)"

# 3. Dry-run push to each remote
git push --dry-run origin main
git push --dry-run cf-mirror main

# 4. Confirm mirror is in sync
diff <(git ls-remote origin refs/heads/main) \
     <(git ls-remote cf-mirror refs/heads/main)
```

---

## Related

- `git-worktree-lockfile-isolation.md`
- `git-worktree-parallel-wrangler-environments.md`
- `git-credential-helper-workers-ci-token-rotation.md`
- `github-actions-wrangler-deploy-pipeline.md`
- `git-refspec-advanced-fetch-push-patterns.md`

---

## Sources

- https://git-scm.com/docs/git-worktree
- https://git-scm.com/docs/git-remote
- https://git-scm.com/docs/git-fetch
- https://git-scm.com/docs/gitconfig (`branch.<name>.remote`, `remote.pushDefault`)
- https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#push
