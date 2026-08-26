# Managing Multiple Wrangler Environments (Dev / Staging / Production)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a single Cloudflare Worker codebase that needs to run in three environments — local dev, staging, and production — with different KV namespaces, D1 databases, routes, secrets, and environment variables per tier. Ad-hoc `wrangler deploy --env staging` commands are undocumented and error-prone. You want a single `wrangler.toml` that is the canonical source of truth for all environment-specific config.

## Context

Wrangler's `[env.<name>]` sections allow defining per-environment overrides for any top-level key. The base (top-level) config acts as defaults; environment sections merge on top and can fully override bindings, routes, vars, and worker name. Secrets are set per-environment via `wrangler secret put --env <name>`.

Environment names are arbitrary strings — `staging`, `production`, `preview` are conventional. The `dev` environment is special: `wrangler dev` always uses the top-level config (or `[env.dev]` if you define one explicitly).

## Solution

```toml
# wrangler.toml
name = "api-dev"
main = "src/index.ts"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]
account_id = "abc123devaccountid"

# ── Shared / dev defaults ────────────────────────────────────────
[vars]
ENVIRONMENT = "development"
LOG_LEVEL = "debug"
API_BASE_URL = "http://localhost:8787"

[[kv_namespaces]]
binding = "SESSIONS"
id = "dev-kv-namespace-id-sessions"
preview_id = "dev-kv-namespace-id-sessions-preview"

[[kv_namespaces]]
binding = "CONFIG"
id = "dev-kv-namespace-id-config"
preview_id = "dev-kv-namespace-id-config-preview"

[[d1_databases]]
binding = "DB"
database_name = "app-db-dev"
database_id = "dev-d1-database-id"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "assets-dev"

# ── Staging environment ──────────────────────────────────────────
[env.staging]
name = "api-staging"
account_id = "abc123devaccountid"  # same account, different resources

[env.staging.vars]
ENVIRONMENT = "staging"
LOG_LEVEL = "info"
API_BASE_URL = "https://api-staging.example.com"

[[env.staging.kv_namespaces]]
binding = "SESSIONS"
id = "staging-kv-namespace-id-sessions"

[[env.staging.kv_namespaces]]
binding = "CONFIG"
id = "staging-kv-namespace-id-config"

[[env.staging.d1_databases]]
binding = "DB"
database_name = "app-db-staging"
database_id = "staging-d1-database-id"

[[env.staging.r2_buckets]]
binding = "ASSETS"
bucket_name = "assets-staging"

[[env.staging.routes]]
pattern = "api-staging.example.com/*"
zone_name = "example.com"

# ── Production environment ───────────────────────────────────────
[env.production]
name = "api-production"
account_id = "abc123prodaccountid"  # separate production account

[env.production.vars]
ENVIRONMENT = "production"
LOG_LEVEL = "warn"
API_BASE_URL = "https://api.example.com"

[[env.production.kv_namespaces]]
binding = "SESSIONS"
id = "prod-kv-namespace-id-sessions"

[[env.production.kv_namespaces]]
binding = "CONFIG"
id = "prod-kv-namespace-id-config"

[[env.production.d1_databases]]
binding = "DB"
database_name = "app-db-production"
database_id = "prod-d1-database-id"

[[env.production.r2_buckets]]
binding = "ASSETS"
bucket_name = "assets-production"

[[env.production.r2_buckets]]
binding = "UPLOADS"
bucket_name = "uploads-production"

[[env.production.routes]]
pattern = "api.example.com/*"
zone_name = "example.com"

[env.production.limits]
cpu_ms = 50
```

```typescript
// src/index.ts — environment-aware Worker
export interface Env {
  ENVIRONMENT: string;
  LOG_LEVEL: string;
  API_BASE_URL: string;
  JWT_SECRET: string;      // secret binding — set via wrangler secret put
  SESSIONS: KVNamespace;
  CONFIG: KVNamespace;
  DB: D1Database;
  ASSETS: R2Bucket;
  UPLOADS?: R2Bucket;     // only bound in production
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const log = makeLogger(env.LOG_LEVEL);

    log.info(`[${env.ENVIRONMENT}] ${request.method} ${request.url}`);

    // Production-only guard
    if (env.UPLOADS === undefined && env.ENVIRONMENT === "production") {
      return new Response("Upload binding missing in production", { status: 500 });
    }

    return new Response(JSON.stringify({ env: env.ENVIRONMENT }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};

function makeLogger(level: string) {
  const levels = { debug: 0, info: 1, warn: 2, error: 3 };
  const current = levels[level as keyof typeof levels] ?? 1;
  return {
    debug: (msg: string) => current <= 0 && console.debug(msg),
    info:  (msg: string) => current <= 1 && console.log(msg),
    warn:  (msg: string) => current <= 2 && console.warn(msg),
    error: (msg: string) => current <= 3 && console.error(msg),
  };
}
```

```bash
# Makefile targets for environment operations
# Usage: make deploy ENV=staging

.PHONY: deploy promote secrets-set

deploy:
    npm run build
    wrangler deploy --env $(ENV)

promote-to-staging:
    $(MAKE) deploy ENV=staging

promote-to-production:
    @echo "Deploying to PRODUCTION — confirm? [y/N]"
    @read ans; [ "$${ans}" = y ]
    $(MAKE) deploy ENV=production

secrets-set:
    wrangler secret put JWT_SECRET --env $(ENV)
    wrangler secret put DATABASE_ENCRYPTION_KEY --env $(ENV)

secrets-list:
    wrangler secret list --env $(ENV)
```

```yaml
# .github/workflows/deploy.yml — environment promotion pipeline
name: Deploy Workers

on:
  push:
    branches:
      - main      # triggers staging
      - release/* # triggers production

jobs:
  deploy-staging:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm run build
      - run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}

  deploy-production:
    if: startsWith(github.ref, 'refs/heads/release/')
    runs-on: ubuntu-latest
    environment: production   # GitHub environment with required reviewers
    needs: []
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm run build
      - run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PRODUCTION }}
```

## Implementation Details

**KV namespace IDs per environment** — create namespaces up front and record their IDs in `wrangler.toml`. Never share a KV namespace between environments — data bleed causes hard-to-debug issues.

Create namespaces:
```bash
wrangler kv:namespace create SESSIONS --env staging
wrangler kv:namespace create SESSIONS --env production
```

The command prints the `id` to paste into `wrangler.toml`.

**Setting secrets per environment:**
```bash
# Each environment gets its own secret value
wrangler secret put JWT_SECRET --env staging
wrangler secret put JWT_SECRET --env production

# List secrets for an environment (values not shown)
wrangler secret list --env production
```

**Preview namespaces** — the `preview_id` field in `[[kv_namespaces]]` is used by `wrangler dev --remote`. In production environments you can omit it; in dev/staging it allows local development against a real KV without affecting the main namespace.

**Environment promotion workflow:**
1. Develop locally with `wrangler dev` (top-level config / dev defaults)
2. Merge to `main` → CI auto-deploys to staging
3. QA on `api-staging.example.com`
4. Cut `release/v1.x` branch → CI deploys to production with required reviewer gate

## Anti-patterns

- **Using the same KV/D1/R2 resource IDs in multiple environments** — changes in staging contaminate production data.
- **Putting secrets in `[env.production.vars]`** — `vars` are plaintext in `wrangler.toml` (committed to git). Use `wrangler secret put` for anything sensitive.
- **Deploying with `--env production` from a developer laptop** — always deploy to production via CI/CD with scoped tokens; local deploys bypass audit logs.
- **Omitting the `name` override in `[env.staging]`** — without it, all environments deploy a Worker named after the root `name`, overwriting each other.
- **Using `account_id` in `wrangler.toml` for production when it differs from dev** — if your prod account differs, override `account_id` in `[env.production]` and use separate API tokens.

## Gotchas

- `wrangler dev` ignores `[env.*]` sections entirely unless you pass `--env <name>`; it uses the top-level config as "dev".
- Route `zone_name` requires the zone to be active on the account associated with the API token used at deploy time.
- Compatibility flags are NOT inherited from the top-level into `[env.*]` — you must repeat `compatibility_date` and `compatibility_flags` in each environment section if they differ.
- `wrangler secret list --env production` lists secret names but never values — verify a secret is set by testing the Worker, not by trying to read the value.
- D1 migrations (`wrangler d1 migrations apply`) require the `--env` flag to target the correct database.

## Verification

```bash
# Deploy to staging and verify
wrangler deploy --env staging --dry-run  # prints config without deploying
wrangler deploy --env staging
curl https://api-staging.example.com/health

# Check which Worker is deployed per environment
wrangler deployments list --env staging
wrangler deployments list --env production

# Confirm secrets are set
wrangler secret list --env production

# Tail logs per environment
wrangler tail api-staging
wrangler tail api-production
```

## Related

- `documentation/docs/policies/infra/workers-terraform-cloudflare-provider.md`
- `documentation/docs/policies/infra/workers-multi-account-deployment.md`
- `documentation/docs/policies/infra/workers-traffic-splitting-ab-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/configuration/secrets/
