# Managing Deploy Order for Workers with Service Binding Dependencies

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your monorepo contains five Cloudflare Workers where `api-gateway` calls `auth-worker` via a service binding, `auth-worker` calls `token-store`, and `cdn-router` calls both `api-gateway` and a standalone `edge-config` Worker. Deploying them in the wrong order leaves bindings pointing at stale code for up to 30 seconds and causes 500s in production during the deploy window.

## Context

Cloudflare Workers service bindings create direct Worker-to-Worker RPC calls without going through the public internet. A binding is declared in `wrangler.toml` as a reference to another Worker's name; at runtime Cloudflare resolves the binding to the **currently deployed** version of the target Worker. This means deploy order matters: if you deploy `api-gateway` before `auth-worker` has been updated, `api-gateway` will call the old `auth-worker` code for any in-flight requests during the deploy window. In a monorepo CI/CD pipeline driven by Turborepo or GitHub Actions, the default parallel execution model does not account for these runtime service binding dependencies. Teams that skip deploy-order management report intermittent 502/500 errors during every release that touches multiple Workers in the same dependency chain.

## Mapping the Service Binding Graph

```bash
# Extract all service binding names from wrangler.toml files in the monorepo
grep -r "\[\[services\]\]" workers/*/wrangler.toml -A 3 \
  | grep -E "binding|service" \
  | awk '{print FILENAME, $0}' \
  | column -t

# Example output (abbreviated):
# workers/api-gateway/wrangler.toml  binding = "AUTH"
# workers/api-gateway/wrangler.toml  service = "auth-worker"
# workers/auth-worker/wrangler.toml  binding = "TOKEN_STORE"
# workers/auth-worker/wrangler.toml  service = "token-store"

# Build a dependency adjacency list for topological sort
# Script: scripts/service-binding-graph.sh
for toml in workers/*/wrangler.toml; do
  worker=$(grep '^name' "$toml" | head -1 | cut -d'"' -f2)
  deps=$(grep 'service = ' "$toml" | cut -d'"' -f2 | tr '\n' ',')
  echo "${worker}: ${deps%,}"
done
```

## Topological Deploy Order in CI

The safest approach is to derive the deploy order from the binding graph so that dependencies are always deployed before dependants:

```yaml
# .github/workflows/deploy-workers.yml
name: Deploy Workers (dependency-ordered)

on:
  push:
    branches: [main]

jobs:
  # Leaf nodes — no service binding dependencies
  deploy-token-store:
    uses: ./.github/workflows/_deploy-worker.yml
    with:
      worker: token-store

  deploy-edge-config:
    uses: ./.github/workflows/_deploy-worker.yml
    with:
      worker: edge-config

  # Mid-tier — depends on token-store
  deploy-auth-worker:
    needs: [deploy-token-store]
    uses: ./.github/workflows/_deploy-worker.yml
    with:
      worker: auth-worker

  # Top-tier — depends on auth-worker and edge-config
  deploy-api-gateway:
    needs: [deploy-auth-worker, deploy-edge-config]
    uses: ./.github/workflows/_deploy-worker.yml
    with:
      worker: api-gateway

  # Router depends on api-gateway
  deploy-cdn-router:
    needs: [deploy-api-gateway]
    uses: ./.github/workflows/_deploy-worker.yml
    with:
      worker: cdn-router
```

```yaml
# .github/workflows/_deploy-worker.yml (reusable workflow)
name: Deploy single Worker
on:
  workflow_call:
    inputs:
      worker:
        required: true
        type: string

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - name: Build worker
        run: pnpm --filter "@monorepo/${{ inputs.worker }}" build
      - name: Deploy to Cloudflare
        run: |
          pnpm --filter "@monorepo/${{ inputs.worker }}" exec \
            wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Local Deploy Script with Ordered Execution

```bash
#!/usr/bin/env bash
# scripts/deploy-all.sh — deploys Workers in dependency order
set -euo pipefail

ENV=${1:-staging}

echo "==> Deploying leaf Workers..."
pnpm --filter @monorepo/token-store exec wrangler deploy --env "$ENV" &
pnpm --filter @monorepo/edge-config exec wrangler deploy --env "$ENV" &
wait
echo "    token-store and edge-config deployed"

echo "==> Deploying mid-tier Workers..."
pnpm --filter @monorepo/auth-worker exec wrangler deploy --env "$ENV"
echo "    auth-worker deployed"

echo "==> Deploying top-tier Workers..."
pnpm --filter @monorepo/api-gateway exec wrangler deploy --env "$ENV"
echo "    api-gateway deployed"

echo "==> Deploying router..."
pnpm --filter @monorepo/cdn-router exec wrangler deploy --env "$ENV"
echo "    cdn-router deployed"

echo "All Workers deployed successfully to $ENV."
```

## Smoke-Testing Service Bindings After Deploy

```bash
# After deploying, verify each binding resolves to the new version
# by checking the Worker version ID from the Cloudflare API

CF_ACCOUNT_ID="your-account-id"
CF_API_TOKEN="$CLOUDFLARE_API_TOKEN"

for worker in token-store edge-config auth-worker api-gateway cdn-router; do
  version=$(curl -s \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${worker}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    | jq -r '.result.etag // "unknown"')
  echo "${worker}: etag=${version}"
done

# Run integration smoke test that exercises the full binding chain
curl -sf https://api.example.com/health | jq '.services'
# Expected: {"auth-worker":"ok","token-store":"ok","edge-config":"ok"}

# Use wrangler tail to observe live logs during the smoke test
wrangler tail api-gateway --env production --format json &
TAIL_PID=$!
curl -sf https://api.example.com/auth/ping
kill "$TAIL_PID"
```

## Anti-patterns

- Running `pnpm turbo run deploy` without configuring Turborepo's task dependency graph—Turborepo parallelizes by default, ignoring Cloudflare's service binding runtime dependencies.
- Deploying all Workers simultaneously with `xargs -P` or `parallel`—parallel deploys save 30 seconds but risk a 30–60 second window where the graph is partially updated.
- Hard-coding the deploy order in a shell script without a machine-readable source of truth—when a new binding is added to `wrangler.toml`, the script silently uses the wrong order until a human notices a 502 in production.
- Using Cloudflare's `[version]` pinning in `wrangler.toml` to avoid deploy-order issues—this defers the problem and eventually leads to Workers running against versions that have been removed.

## Gotchas

- Cloudflare propagates Worker deploys globally in under 30 seconds, but during that window some data centres may still invoke the previous version via a service binding; design idempotent handlers and use `waitUntil` for side effects.
- Wrangler exits with code 0 on a successful deploy but the `etag` in the API response is the only reliable way to confirm the new script version is live; poll the API if you need strict ordering guarantees.
- If a Worker fails to deploy mid-sequence, downstream Workers in the chain have already been skipped, leaving the graph in a partially updated state; your CI workflow's `needs:` chain ensures GitHub Actions marks subsequent jobs as skipped, but a manual rollback of already-deployed Workers may be required.

## Verification

```bash
# Confirm the GitHub Actions job graph ran in the right order
gh run view --log | grep -E "deploy-(token-store|edge-config|auth-worker|api-gateway|cdn-router)"

# Assert the current deployed script etags differ from the previous release
# (run before and after deploy, compare outputs)
for worker in token-store auth-worker api-gateway; do
  curl -s \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${worker}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    | jq -r '"${worker}: " + .result.etag'
done

# Validate the service binding chain end-to-end
curl -sf https://api.example.com/auth/me \
  -H "Authorization: Bearer $TEST_JWT" \
  | jq '.user_id'
```

## Related

- `worktree/monorepo-wrangler-selective-deploy.md`
- `worktree/wrangler-environments-staging-production.md`
- `worktree/github-actions-wrangler-deploy-pipeline.md`
- `worktree/canary-deployment-strategy.md`
- `worktree/rollback-strategy.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/wrangler/configuration/#service-bindings
- https://turbo.build/repo/docs/reference/run#--filter
