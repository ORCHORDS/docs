# Deploying to Cloudflare Workers for Platforms via GitHub Actions

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You operate a SaaS product built on Cloudflare Workers for Platforms and need a repeatable CI pipeline that compiles tenant-uploaded scripts, uploads them to a dispatch namespace, and promotes them to production without manual Wrangler invocations.

## Context
Workers for Platforms exposes a dispatch namespace where each tenant's script lives under a unique name. Deploying is a two-step process: upload the worker bundle via the REST API (or `wrangler dispatch-namespace`), then optionally bind the namespace to a parent router worker. GitHub Actions handles both steps using OIDC credentials so no long-lived API tokens are stored as secrets.

## Setting Up OIDC for Workers for Platforms

Create a Cloudflare API token scoped to `Workers Scripts:Edit` and `Workers for Platforms:Edit`, then configure the OIDC trust in the Cloudflare dashboard under **Account > Workers for Platforms > OIDC settings**.

```yaml
# .github/workflows/wfp-deploy.yml
name: Workers for Platforms – Deploy Tenant Script

on:
  push:
    branches: [main]
    paths:
      - 'tenant-scripts/**'
      - 'router-worker/**'

permissions:
  id-token: write
  contents: read
```

## Building Tenant Scripts

Tenant scripts share a common build step. A matrix job compiles each subdirectory in `tenant-scripts/` and uploads the output bundle.

```yaml
jobs:
  build-and-upload:
    runs-on: ubuntu-24.04
    strategy:
      matrix:
        tenant: ${{ fromJson(needs.discover.outputs.tenants) }}
    needs: discover
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Build tenant bundle
        run: |
          cd tenant-scripts/${{ matrix.tenant }}
          pnpm exec esbuild src/index.ts \
            --bundle \
            --format=esm \
            --outfile=dist/worker.js \
            --external:__STATIC_CONTENT_MANIFEST

      - name: Upload to dispatch namespace
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
          DISPATCH_NAMESPACE: ${{ vars.WFP_NAMESPACE }}
          TENANT_NAME: ${{ matrix.tenant }}
          CF_API_TOKEN: ${{ secrets.CF_WFP_API_TOKEN }}
        run: |
          curl -s -o /dev/null -w "%{http_code}" \
            --fail-with-body \
            -X PUT \
            "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/dispatch/namespaces/${DISPATCH_NAMESPACE}/scripts/${TENANT_NAME}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/javascript+module" \
            --data-binary @tenant-scripts/${TENANT_NAME}/dist/worker.js
```

## Discovering Changed Tenants

A pre-job discovers which tenant directories changed so only affected scripts redeploy.

```yaml
  discover:
    runs-on: ubuntu-24.04
    outputs:
      tenants: ${{ steps.list.outputs.tenants }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - name: Identify changed tenant scripts
        id: list
        run: |
          CHANGED=$(git diff --name-only HEAD~1 HEAD -- tenant-scripts/ \
            | cut -d/ -f2 | sort -u | jq -R -s -c 'split("\n") | map(select(length > 0))')
          echo "tenants=${CHANGED}" >> "$GITHUB_OUTPUT"
```

## Promoting the Router Worker

After tenant scripts are uploaded, redeploy the parent router worker that contains the dispatch namespace binding.

```yaml
  deploy-router:
    runs-on: ubuntu-24.04
    needs: build-and-upload
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          workingDirectory: router-worker
          command: deploy --env production
```

`wrangler.toml` for the router worker:

```toml
name = "saas-router"
main = "src/router.ts"
compatibility_date = "2026-08-01"

[[dispatch_namespaces]]
binding = "DISPATCH"
namespace = "tenant-scripts-prod"
```

## TypeScript Router Worker

```typescript
// router-worker/src/router.ts
export interface Env {
  DISPATCH: DispatchNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const tenantId = url.hostname.split('.')[0];

    if (!tenantId) {
      return new Response('Missing tenant', { status: 400 });
    }

    const tenantWorker = env.DISPATCH.get(tenantId, {
      outbound: {
        service: 'saas-outbound-proxy',
        environment: 'production',
      },
    });

    return tenantWorker.fetch(request);
  },
};
```

## Rollback Strategy

Tag each successful deployment with the git SHA and keep a rollback workflow that re-uploads the previous bundle from a cached artifact.

```yaml
  rollback:
    runs-on: ubuntu-24.04
    if: failure()
    needs: deploy-router
    steps:
      - name: Re-upload previous bundle
        env:
          PREVIOUS_SHA: ${{ github.event.before }}
        run: |
          echo "Triggering rollback to ${PREVIOUS_SHA}"
          gh workflow run rollback.yml \
            -f sha="${PREVIOUS_SHA}" \
            --repo ${{ github.repository }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Anti-patterns
- Storing the Cloudflare API token as a plain Actions secret with `Workers Scripts:Edit` on the entire account — scope it to the specific dispatch namespace only.
- Uploading all tenants on every push regardless of changes — use the `discover` job to limit deploys to changed scripts.
- Skipping the router-worker redeploy when the dispatch namespace binding configuration changes — the parent worker must also be redeployed.
- Using `wrangler publish` (deprecated) instead of `wrangler deploy` with `dispatch_namespaces` binding.
- Committing compiled bundles to the repository instead of building them in CI.

## Gotchas
- `DispatchNamespace.get()` requires the tenant name to be URL-safe; enforce this validation before upload.
- The upload API returns `200` on both create and update — use the `etag` response header to detect whether a new version was actually written.
- Workers for Platforms scripts do not inherit the account-level bindings; declare all bindings (KV, D1, R2) explicitly per tenant via the REST API's `metadata` body field.
- Free/Paid tier limits on dispatch namespace script counts differ — the CI pipeline should fail fast when approaching limits.

## Verification
1. Run the `wfp-deploy.yml` workflow on a branch with a change in `tenant-scripts/alpha/`.
2. Confirm only the `alpha` tenant appears in the matrix output from `discover`.
3. Call `curl https://alpha.your-saas.com/health` and verify the response comes from the freshly deployed script (check the `CF-Ray` header and worker version in response metadata).
4. Introduce a syntax error in the script, confirm the upload step fails and the router-worker deployment is blocked.

## Related
- `github-actions-oidc-cloudflare-deploy.md`
- `github-actions-matrix-strategy-workers.md`
- `github-actions-workers-preview-environments.md`
- `github-actions-retry-failed-workers-deploy.md`

## Sources
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
- https://github.com/cloudflare/wrangler-action
