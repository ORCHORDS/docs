# Git Post-Merge Hook for Automated Wrangler Deployment

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After merging a PR locally (or after a `git pull` that fast-forwards `main`), the developer must remember to run `wrangler deploy` manually. Steps get skipped, staging lags behind `main`, and the team debugs issues that are already fixed in source but not yet deployed. A `post-merge` hook fires automatically after every successful `git merge` (including fast-forward pulls), giving you a zero-ceremony deployment trigger without CI pipeline latency.

## Context

Git's `post-merge` hook receives one argument: `1` if the merge was a squash merge, `0` otherwise. It runs in the working tree root after `MERGE_HEAD` is cleared but before the terminal returns to the user. Because it runs locally, it has access to the developer's full environment—including Wrangler credentials stored in `~/.wrangler/`—without needing CI secrets injection. The hook is not transferred by `git clone`, so each developer opts in by creating `.git/hooks/post-merge` (or by using a hook manager like Lefthook that installs it automatically).

---

## Hook Installation with Lefthook

Add to `lefthook.yml` so every team member gets the hook on `lefthook install`:

```yaml
# lefthook.yml
post-merge:
  commands:
    wrangler-deploy:
      run: ./.hooks/post-merge-deploy.sh
      fail_text: "Wrangler deploy failed after merge. Run `wrangler deploy` manually."
```

```bash
#!/usr/bin/env bash
# .hooks/post-merge-deploy.sh
set -euo pipefail

SQUASH_MERGE=${1:-0}
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Only auto-deploy from the main branch
if [[ "$BRANCH" != "main" ]]; then
  echo "post-merge: skipping Wrangler deploy (branch: $BRANCH)"
  exit 0
fi

# Detect which workers changed in this merge
CHANGED_WORKERS=$(git diff-tree -r --name-only ORIG_HEAD HEAD \
  | grep -E '^workers/' \
  | cut -d'/' -f2 \
  | sort -u)

if [[ -z "$CHANGED_WORKERS" ]]; then
  echo "post-merge: no worker source changed, skipping deploy"
  exit 0
fi

echo "post-merge: deploying changed workers: $CHANGED_WORKERS"

for worker in $CHANGED_WORKERS; do
  echo "  Deploying workers/$worker ..."
  (cd "workers/$worker" && wrangler deploy --env staging)
done
```

## Detecting Changed Files with ORIG_HEAD

The hook has access to `ORIG_HEAD`, which points to the commit before the merge. Use it to scope deploys to only what changed:

```bash
#!/usr/bin/env bash
# Granular change detection across monorepo packages
ORIG=${ORIG_HEAD:-HEAD~1}

git diff-tree -r --name-only "$ORIG" HEAD | while read -r path; do
  case "$path" in
    packages/api/*)   echo "api" ;;
    packages/auth/*)  echo "auth" ;;
    shared/*)         echo "api auth edge-cache" ;;
  esac
done | tr ' ' '\n' | sort -u > /tmp/deploy-targets.txt

while IFS= read -r target; do
  echo "Deploying: $target"
  wrangler deploy --config "wrangler.$target.toml" --env staging
done < /tmp/deploy-targets.txt
```

## Wrangler Environment Selection by Branch

Auto-select the Wrangler environment based on the current branch to prevent accidental production deploys from local hooks:

```typescript
// scripts/resolve-wrangler-env.ts
import { execSync } from "child_process";

export function resolveWranglerEnv(): "staging" | "preview" | never {
  const branch = execSync("git rev-parse --abbrev-ref HEAD")
    .toString()
    .trim();

  const envMap: Record<string, "staging" | "preview"> = {
    main: "staging",
    develop: "preview",
  };

  const env = envMap[branch];
  if (!env) {
    throw new Error(
      `post-merge hook: branch '${branch}' has no mapped Wrangler env. ` +
        `Add it to scripts/resolve-wrangler-env.ts or skip auto-deploy.`
    );
  }
  return env;
}
```

```bash
# In the hook script, call the resolver:
ENV=$(npx tsx scripts/resolve-wrangler-env.ts) || exit 0
wrangler deploy --env "$ENV"
```

## Skipping the Hook for Hotfixes

Sometimes a merge should not trigger a deploy—e.g., a documentation-only PR or a hotfix that CI will deploy via a separate pipeline. Use a git commit message trailer or environment variable to skip:

```bash
#!/usr/bin/env bash
# Check the merge commit message for a skip trailer
MERGE_MSG=$(git log -1 --format="%B")

if echo "$MERGE_MSG" | grep -qi "deploy-skip: true"; then
  echo "post-merge: deploy skipped by commit trailer"
  exit 0
fi

# Allow CI environments to suppress local hook side-effects
if [[ "${CI:-false}" == "true" ]]; then
  echo "post-merge: running in CI, hook is a no-op"
  exit 0
fi
```

## Timeout Guard and Async Fallback

Wrangler deploys can take 10–30 seconds. If a developer is on a slow connection, the hook blocks their terminal. Use a timeout with an async fallback:

```bash
#!/usr/bin/env bash
TIMEOUT=60  # seconds

deploy_with_timeout() {
  local worker="$1"
  local env="$2"
  if timeout "$TIMEOUT" wrangler deploy --config "workers/$worker/wrangler.toml" --env "$env"; then
    echo "  ✓ $worker deployed"
  else
    local exit_code=$?
    if [[ $exit_code -eq 124 ]]; then
      echo "  ⚠ $worker deploy timed out after ${TIMEOUT}s — queuing async deploy"
      # Write a marker file; a background daemon or next CI run picks it up
      echo "$worker:$env:$(date -u +%s)" >> ~/.local/share/wrangler-pending-deploys
    else
      echo "  ✗ $worker deploy failed (exit $exit_code)"
      exit 1
    fi
  fi
}
```

---

## Anti-patterns

- **Deploying to production from a local hook.** Local hooks bypass CI validation—unit tests, type checks, security scans. Never point `post-merge` at `--env production`.
- **Not guarding on branch name.** Running the hook on every feature branch merge creates noise and wastes Wrangler API quota.
- **Committing `.git/hooks/` directly.** Git does not track `.git/hooks`. Use Lefthook, Husky, or a setup script so team members opt in consistently.
- **Ignoring non-zero exit codes.** A failing Wrangler deploy should exit non-zero so the developer sees the error instead of silently shipping broken code.

## Gotchas

- `ORIG_HEAD` is set by `git merge` but **not** by `git cherry-pick` or `git rebase`. If your workflow uses either, guard against an unset `ORIG_HEAD`.
- The hook runs even for `git pull --rebase` merges on some Git versions. Test with `[[ -f .git/MERGE_HEAD ]]` to detect a true merge vs. a rebase fast-forward.
- Wrangler reads `CLOUDFLARE_API_TOKEN` from the environment. Ensure developers have this set in their shell profile, not just in CI secrets.
- On macOS, `timeout` is from GNU coreutils (`brew install coreutils`). Use `gtimeout` or check availability in the hook.

## Verification

```bash
# 1. Install hook manager
npx lefthook install

# 2. Create a test merge
git checkout -b test/post-merge-smoke
echo "// smoke" >> workers/api/src/index.ts
git add . && git commit -m "chore: smoke test post-merge hook"
git checkout main && git merge --no-ff test/post-merge-smoke
# Hook fires here — observe Wrangler output

# 3. Verify deployment reached staging
wrangler deployments list --env staging | head -5

# 4. Confirm skip trailer works
git merge --no-ff some-docs-branch -m "docs: update readme

deploy-skip: true"
# Expect: "post-merge: deploy skipped by commit trailer"
```

## Related

- `git-hooks-lefthook-monorepo.md`
- `git-hooks-sequential-parallel-execution-strategy.md`
- `wrangler-environments-staging-production.md`
- `monorepo-wrangler-selective-deploy.md`
- `github-actions-wrangler-deploy-pipeline.md`

## Sources

- Git documentation: githooks(5) — `post-merge`
- Wrangler CLI reference: `wrangler deploy --env`
- Lefthook documentation: https://github.com/evilmartians/lefthook
- Cloudflare Workers docs: Environments and configuration
