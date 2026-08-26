# Trunk-Based Development Workflow for Cloudflare Workers Teams

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Workers team accumulates long-lived feature branches. Merge conflicts compound daily, integration surprises arrive at deployment time, and the main branch diverges so far from feature branches that rebasing becomes a multi-hour exercise. Deployments cluster at the end of sprints, increasing blast radius. You need a workflow that keeps every developer within hours of `main` and makes continuous deployment safe.

## Context

Trunk-Based Development (TBD) is a source-control branching model where developers integrate into a shared `main` branch at least once per day. Long-lived branches are replaced by:

- **Short-lived feature branches** (< 2 days, typically < 1 day)
- **Feature flags** to hide incomplete work from production traffic
- **Merge queues** to serialize integration and gate on CI
- **Branch-by-abstraction** for large refactors

Cloudflare Workers is particularly well-suited to TBD because:
- Preview deployments are free and instant (`wrangler deploy --env preview`)
- Workers KV / Durable Objects support environment namespacing
- `wrangler` environments map cleanly to trunk / preview / production

## Solution

### 1. Branch naming conventions

Enforce short branch names that encode intent and lifespan:

```
<type>/<ticket-id>-<slug>
```

Examples:
```
feat/WRK-412-rate-limit-header
fix/WRK-401-kv-namespace-null
chore/WRK-388-update-wrangler
```

Rules (enforced via branch protection or a `pre-push` hook):
- Maximum slug length: 50 characters
- No upper-case, no spaces, hyphens only
- No `wip/`, `dev/`, or `temp/` prefixes — if it can't be named, it isn't ready to branch

```bash
#!/bin/sh
# .git/hooks/pre-push

BRANCH=$(git symbolic-ref --short HEAD)

# Allow main and release branches through
if echo "$BRANCH" | grep -qE '^(main|release/.+)$'; then
  exit 0
fi

BRANCH_PATTERN='^(feat|fix|chore|docs|test|refactor|perf|ci)/[A-Z]+-[0-9]+-[a-z0-9-]{1,50}$'

if ! echo "$BRANCH" | grep -qE "$BRANCH_PATTERN"; then
  echo "ERROR: branch name '$BRANCH' does not follow convention."
  echo "Expected: <type>/<TICKET-ID>-<slug>  (e.g. feat/WRK-42-add-retry)"
  exit 1
fi

exit 0
```

### 2. Feature flags instead of long branches

For features that span more than one day, use a flag instead of keeping a branch open. Store flags in Workers KV:

```typescript
// src/feature-flags.ts
export interface Env {
  FLAGS: KVNamespace;
}

export type FlagName =
  | 'rate-limiting-v2'
  | 'new-auth-flow'
  | 'streaming-response';

/**
 * Returns true if the named feature flag is enabled.
 * Flags are stored in KV as JSON: { "enabled": true, "rollout": 0.5 }
 * The rollout field (0.0-1.0) enables percentage-based rollout.
 */
export async function isEnabled(
  env: Env,
  flag: FlagName,
  requestId?: string
): Promise<boolean> {
  const raw = await env.FLAGS.get(flag, { type: 'json' }) as
    | { enabled: boolean; rollout?: number }
    | null;

  if (!raw || !raw.enabled) return false;
  if (raw.rollout === undefined || raw.rollout >= 1.0) return true;

  // Deterministic per-request rollout using last 4 hex digits of requestId
  if (!requestId) return Math.random() < raw.rollout;
  const bucket = parseInt(requestId.slice(-4), 16) / 0xffff;
  return bucket < raw.rollout;
}
```

Usage in a Worker:

```typescript
// src/index.ts
import { isEnabled, type Env } from './feature-flags';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const reqId = request.headers.get('cf-ray') ?? crypto.randomUUID();

    if (await isEnabled(env, 'rate-limiting-v2', reqId)) {
      return handleWithRateLimitV2(request, env);
    }

    return handleDefault(request, env);
  },
};
```

Set a flag via Wrangler without touching code or branches:

```bash
# Enable for 10% rollout in production
wrangler kv key put --namespace-id=$FLAGS_NAMESPACE_ID \
  "rate-limiting-v2" \
  '{"enabled": true, "rollout": 0.1}'

# Full enable
wrangler kv key put --namespace-id=$FLAGS_NAMESPACE_ID \
  "rate-limiting-v2" \
  '{"enabled": true, "rollout": 1.0}'

# Kill switch
wrangler kv key put --namespace-id=$FLAGS_NAMESPACE_ID \
  "rate-limiting-v2" \
  '{"enabled": false}'
```

### 3. Pre-merge CI gates

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npx tsc --noEmit

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npx eslint . --max-warnings 0

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npx vitest run --reporter=verbose

  dry-run-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - name: Wrangler dry-run
        run: npx wrangler deploy --dry-run --outdir dist/
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

### 4. Merge queue setup (branch protection)

Configure via GitHub REST API or UI:

```bash
# Using GitHub CLI
gh api \
  --method PUT \
  repos/example-org/example-repo/branches/main/protection \
  --field required_status_checks='{"strict":true,"contexts":["typecheck","lint","test","dry-run-deploy"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

Enable merge queue on the branch protection (GitHub UI: Settings > Branches > Edit > Enable merge queue). Set:
- Minimum PRs to merge: 1
- Maximum PRs to merge: 5
- Merge method: Squash (keeps main history linear)

### 5. Team norms for Workers-specific considerations

```markdown
## Workers TBD Team Norms (paste into your team wiki)

### Branch lifespan
- Open a PR within 4 hours of creating a branch.
- Branches older than 2 days are stale and must be rebased or closed.
- Use `git fetch --prune` daily to remove deleted remote branches.

### wrangler.toml changes
- Changes to `wrangler.toml` that add new bindings must include a
  corresponding `terraform` or `wrangler` provisioning script.
- Never commit account_id or zone_id; use environment variables.

### Environment parity
- Every PR gets a preview Worker deployed by CI at `pr-<number>.<worker>.workers.dev`.
- Smoke-test your change against the preview URL before requesting review.

### KV / DO state
- If your branch creates a new KV namespace, provision it in the `dev`
  environment first and document the namespace ID in the PR description.
- Durable Object migrations must be backward-compatible for at least one
  release cycle (old DO class + new DO class must coexist).

### Hotfixes
- Even hotfixes go through a branch + PR + merge queue.
- Use the `fix/` prefix and tag the PR with `priority: hotfix`.
- The merge queue processes `priority: hotfix` PRs ahead of the queue.
```

## Implementation Details

- TBD requires feature flags as a first-class primitive. Without flags, incomplete features must hide behind long branches.
- The `wrangler deploy --dry-run` CI step catches `wrangler.toml` misconfiguration (invalid binding names, missing vars) before merge, not after.
- Squash-merge keeps `main` history one-commit-per-feature, enabling clean `git bisect` runs and readable `git log --oneline`.
- Preview Worker URLs (`pr-<number>.<worker>.workers.dev`) are deployed by the `preview-deploy` CI job (see `workers-gitops-auto-deploy-main-branch.md`) and torn down when the PR closes.

## Anti-patterns

- **`develop` or `staging` branches**: permanent integration branches become a second trunk that diverges from `main`; eliminate them.
- **Merging without CI green**: even urgent fixes; the merge queue enforces this automatically.
- **Long-running `refactor/` branches**: use branch-by-abstraction — add the new abstraction behind a flag, migrate callers incrementally on `main`, remove the old code.
- **Storing KV namespace IDs in `.env.example`**: namespace IDs are environment-specific; store in CI secrets or a secrets manager.

## Gotchas

- GitHub merge queues do not support merge-commit strategy — only squash or rebase. Plan accordingly before enabling.
- `wrangler.toml` `env` blocks inherit from the top-level config; an accidental top-level `kv_namespaces` entry will bind in every environment including production.
- Feature flags in KV have ~60ms cold-read latency; cache in `ctx.waitUntil` or use a `Cache API` entry for hot paths.

## Verification

```bash
# Confirm branch naming hook is active
cat .git/hooks/pre-push

# Check merge queue is enabled on main
gh api repos/example-org/example-repo/branches/main/protection | jq '.required_pull_request_reviews'

# List feature flags currently set in production KV
wrangler kv list --namespace-id=$FLAGS_NAMESPACE_ID

# Verify dry-run passes locally
npx wrangler deploy --dry-run --outdir dist/
```

## Related

- `documentation/categories/worktree/workers-merge-queue-github-actions.md`
- `documentation/categories/worktree/workers-conventional-commits-enforcement.md`
- `documentation/categories/worktree/feature-flag-parallel-dev.md`

## Sources

- https://trunkbaseddevelopment.com/
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
