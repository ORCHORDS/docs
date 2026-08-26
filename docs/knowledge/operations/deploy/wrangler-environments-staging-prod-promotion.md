# Multi-Environment Workers Promotion Pipeline with Wrangler Environments

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a repeatable, CI-driven pipeline that deploys a Workers application to a `staging` environment on every merge to `main`, and promotes exactly the same artifact to `production` when a Git tag is pushed — with separate D1, KV, and R2 bindings per environment.

## Context

Wrangler `[env.*]` blocks in `wrangler.toml` let you name distinct deployment targets. Each environment can override bindings, variables, and routes, while sharing the same Worker source. GitHub Actions drives the pipeline: a push to `main` triggers `wrangler deploy --env staging`; a `v*` tag push triggers `wrangler deploy --env production`. The same compiled artifact is reused, with environment-specific bindings injected at deploy time.

## wrangler.toml — full multi-environment configuration

```toml
# wrangler.toml
name = "my-api"
main = "src/index.ts"
compatibility_date = "2026-01-01"

# ── Shared defaults ───────────────────────────────────────────────────────────
[vars]
APP_ENV = "development"
FEATURE_NEW_SEARCH = "false"

# ── Staging environment ───────────────────────────────────────────────────────
[env.staging]
name = "my-api-staging"
route = { pattern = "staging-api.example.com/*", zone_name = "example.com" }

[env.staging.vars]
APP_ENV = "staging"
FEATURE_NEW_SEARCH = "true"

[[env.staging.kv_namespaces]]
binding = "CACHE"
id = "<staging-kv-id>"

[[env.staging.d1_databases]]
binding = "DB"
database_name = "my-api-staging"
database_id = "<staging-d1-id>"

[[env.staging.r2_buckets]]
binding = "ASSETS"
bucket_name = "my-api-assets-staging"

# ── Production environment ────────────────────────────────────────────────────
[env.production]
name = "my-api-production"
route = { pattern = "api.example.com/*", zone_name = "example.com" }

[env.production.vars]
APP_ENV = "production"
FEATURE_NEW_SEARCH = "false"

[[env.production.kv_namespaces]]
binding = "CACHE"
id = "<production-kv-id>"

[[env.production.d1_databases]]
binding = "DB"
database_name = "my-api-production"
database_id = "<production-d1-id>"

[[env.production.r2_buckets]]
binding = "ASSETS"
bucket_name = "my-api-assets-production"
```

## GitHub Actions pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  deploy-staging:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Deploy to staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --env staging

      - name: Smoke test staging
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://staging-api.example.com/health)
          if [ "$STATUS" != "200" ]; then echo "Staging health check failed: $STATUS"; exit 1; fi

  deploy-production:
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Deploy to production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --env production

      - name: Smoke test production
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api.example.com/health)
          if [ "$STATUS" != "200" ]; then echo "Production health check failed: $STATUS"; exit 1; fi
```

## Worker source — reading environment-specific vars

```typescript
// src/index.ts
export interface Env {
  APP_ENV: string;
  FEATURE_NEW_SEARCH: string;
  CACHE: KVNamespace;
  DB: D1Database;
  ASSETS: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({ status: 'ok', env: env.APP_ENV });
    }

    const useNewSearch = env.FEATURE_NEW_SEARCH === 'true';

    // Route to feature-flagged code path
    if (useNewSearch && url.pathname.startsWith('/search')) {
      return handleNewSearch(request, env);
    }

    return new Response('Hello from ' + env.APP_ENV, { status: 200 });
  },
};

async function handleNewSearch(request: Request, env: Env): Promise<Response> {
  // New search implementation backed by D1
  const { results } = await env.DB.prepare(
    'SELECT id, title FROM items WHERE title LIKE ?'
  ).bind('%example%').all();
  return Response.json({ results, engine: 'new' });
}
```

## Promoting staging to production manually

When CI is unavailable, tag the same commit that was deployed to staging:

```bash
# Find the staging deploy commit
git log --oneline -5

# Tag it — this triggers the production deploy job
git tag v1.4.2 <commit-sha>
git push origin v1.4.2
```

## Anti-patterns

- **Using the same D1/KV IDs across environments** — a staging migration or data wipe will corrupt production data.
- **Deploying a different branch to production than what was tested in staging** — always tag the exact commit that passed staging.
- **Storing secrets in `[vars]`** — use `wrangler secret put --env production` for sensitive values; `vars` are visible in the dashboard.
- **Skipping the smoke test step** — a deployment that completes without error can still serve 500s if bindings are misconfigured.

## Gotchas

- `wrangler deploy --env staging` creates a Worker named `my-api-staging` (the `name` override). Omitting the `name` override causes both environments to share the same Worker name and overwrite each other.
- D1 migrations must be run separately per environment: `wrangler d1 migrations apply my-api-staging --env staging`.
- The GitHub Actions `environment: production` gate enables required reviewers — configure this in repository Settings → Environments.
- Wrangler reads `CLOUDFLARE_ACCOUNT_ID` from the environment or from `wrangler.toml`'s top-level `account_id` field.

## Verification

```bash
# List deployed Workers and confirm both environments exist
wrangler deployments list --env staging
wrangler deployments list --env production

# Check live env var
curl https://staging-api.example.com/health
# → {"status":"ok","env":"staging"}
curl https://api.example.com/health
# → {"status":"ok","env":"production"}
```

## Related

- `workers-blue-green-deploy-traffic-split-kv.md`
- `cloudflare-pages-preview-environments-per-pr.md`
- `workers-deployment-annotations-version-tags.md`

## Sources

- Wrangler environments: https://developers.cloudflare.com/workers/wrangler/environments/
- D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
- GitHub Actions environments: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
