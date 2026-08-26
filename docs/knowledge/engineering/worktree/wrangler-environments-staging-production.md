# Wrangler Multi-Environment Config: Staging vs Production

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your Cloudflare Worker accidentally uses production KV, D1, or secrets when deployed from a feature branch because all environments share the same `wrangler.toml` bindings. Or your staging Worker URL is indistinguishable from production, making it easy to test against the wrong endpoint. You need a single config file that cleanly separates staging from production resources and is safe to commit to a monorepo.

---

## Context

Wrangler supports named environments via `[env.<name>]` stanzas in `wrangler.toml`. Each environment can override any top-level setting: bindings, routes, secrets, compatibility flags, and Worker name. Values not overridden inherit from the top level. Secrets (set via `wrangler secret put --env <name>`) are stored per environment in Cloudflare and never appear in `wrangler.toml`. This means the config file is safe to commit while environment-specific credentials remain encrypted.

In a monorepo, each package's `wrangler.toml` controls only its own Worker. Environment names are conventionally `staging` and `production`, matching branch names or GitHub environment names used for deploy gates.

---

## Core wrangler.toml Structure

```toml
# packages/api-worker/wrangler.toml

# ── Top-level defaults (shared or dev-only) ──────────────────────────────────
name            = "api-worker-dev"
main            = "src/index.ts"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

[vars]
ENVIRONMENT     = "development"
LOG_LEVEL       = "debug"
API_BASE_URL    = "http://localhost:8787"

[[kv_namespaces]]
binding         = "SESSIONS"
id              = "aaaa1111aaaa1111aaaa1111aaaa1111"   # dev namespace

[[d1_databases]]
binding         = "DB"
database_name   = "api-db-dev"
database_id     = "bbbb2222bbbb2222bbbb2222bbbb2222"

# ── Staging environment ───────────────────────────────────────────────────────
[env.staging]
name            = "api-worker-staging"
routes          = [{ pattern = "staging-api.example.com/*", zone_name = "example.com" }]

[env.staging.vars]
ENVIRONMENT     = "staging"
LOG_LEVEL       = "info"
API_BASE_URL    = "https://staging-api.example.com"

[[env.staging.kv_namespaces]]
binding         = "SESSIONS"
id              = "cccc3333cccc3333cccc3333cccc3333"   # staging namespace

[[env.staging.d1_databases]]
binding         = "DB"
database_name   = "api-db-staging"
database_id     = "dddd4444dddd4444dddd4444dddd4444"

# ── Production environment ────────────────────────────────────────────────────
[env.production]
name            = "api-worker"
routes          = [{ pattern = "api.example.com/*", zone_name = "example.com" }]

[env.production.vars]
ENVIRONMENT     = "production"
LOG_LEVEL       = "warn"
API_BASE_URL    = "https://api.example.com"

[[env.production.kv_namespaces]]
binding         = "SESSIONS"
id              = "eeee5555eeee5555eeee5555eeee5555"   # production namespace

[[env.production.d1_databases]]
binding         = "DB"
database_name   = "api-db-prod"
database_id     = "ffff6666ffff6666ffff6666ffff6666"
```

---

## Section 1: Secrets Per Environment

Secrets are never in `wrangler.toml`. Set them once per environment:

```bash
# Set a secret for staging
wrangler secret put AUTH_SECRET --env staging
# Prompts for value — stored encrypted in Cloudflare

# Set the same secret for production (different value)
wrangler secret put AUTH_SECRET --env production

# List secrets for an environment (names only, never values)
wrangler secret list --env staging
wrangler secret list --env production
```

In CI, secrets are written via the Wrangler API using `CLOUDFLARE_API_TOKEN`:

```bash
# In GitHub Actions (using wrangler directly, value from GitHub Secrets)
echo "$AUTH_SECRET_STAGING" | wrangler secret put AUTH_SECRET --env staging
echo "$AUTH_SECRET_PROD"    | wrangler secret put AUTH_SECRET --env production
```

In Worker code, access secrets identically regardless of environment:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.AUTH_SECRET is available in all environments
    const token = env.AUTH_SECRET;
    // ...
  },
};
```

---

## Section 2: TypeScript Environment Types

Declare a single `Env` type covering all possible bindings. The runtime injects only the bindings relevant to the deployed environment:

```typescript
// packages/api-worker/src/types/env.d.ts
export interface Env {
  // KV
  SESSIONS: KVNamespace;
  // D1
  DB: D1Database;
  // Secrets (never in wrangler.toml)
  AUTH_SECRET: string;
  STRIPE_WEBHOOK_SECRET: string;
  // Vars (in wrangler.toml [vars])
  ENVIRONMENT: "development" | "staging" | "production";
  LOG_LEVEL: "debug" | "info" | "warn" | "error";
  API_BASE_URL: string;
}
```

---

## Section 3: Local Development with wrangler dev

```bash
# Run against dev defaults (top-level wrangler.toml)
wrangler dev

# Run with staging bindings locally (remote KV, remote D1)
wrangler dev --env staging --remote

# Run with production bindings locally — useful for debugging prod issues
# CAUTION: writes go to real production data
wrangler dev --env production --remote
```

For local development without remote KV/D1, use Miniflare's in-memory bindings by omitting `--remote`. Wrangler will create `.wrangler/state/` local state:

```bash
wrangler dev --env staging   # local KV/D1 backed by SQLite in .wrangler/state/
```

Add `.wrangler/state/` to `.gitignore`:

```gitignore
# packages/api-worker/.gitignore
.wrangler/
dist/
```

---

## Section 4: GitHub Actions Deploy Workflow

Pair Wrangler environments with GitHub Environments for deploy gates:

```yaml
# .github/workflows/deploy-worker.yml
name: Deploy API Worker

on:
  push:
    branches: [main]
    paths: ["packages/api-worker/**"]
  workflow_dispatch:
    inputs:
      environment:
        description: "Target environment"
        required: true
        type: choice
        options: [staging, production]

jobs:
  deploy-staging:
    if: github.ref == 'refs/heads/main' || github.event.inputs.environment == 'staging'
    runs-on: ubuntu-latest
    environment: staging          # GitHub Environment — maps to branch protection rules
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile
      - name: Deploy to staging
        working-directory: packages/api-worker
        run: pnpm exec wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

  deploy-production:
    needs: deploy-staging
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production        # GitHub Environment — requires manual approval
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile
      - name: Deploy to production
        working-directory: packages/api-worker
        run: pnpm exec wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PRODUCTION }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

Note: Use separate `CLOUDFLARE_API_TOKEN` secrets per environment with scoped API tokens. The staging token cannot write to production Workers.

---

## Section 5: D1 Migrations Per Environment

D1 migrations run against a specific environment's database:

```bash
# Apply pending migrations to staging
wrangler d1 migrations apply api-db-staging --env staging

# Apply pending migrations to production
wrangler d1 migrations apply api-db-prod --env production

# Check migration status
wrangler d1 migrations list api-db-staging --env staging
```

In CI, run migrations before each deploy:

```yaml
- name: Run D1 migrations (staging)
  working-directory: packages/api-worker
  run: |
    pnpm exec wrangler d1 migrations apply api-db-staging --env staging
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

- name: Deploy to staging
  working-directory: packages/api-worker
  run: pnpm exec wrangler deploy --env staging
```

---

## Section 6: Tail Logs Per Environment

Inspect live logs from a specific environment:

```bash
# Tail staging logs
wrangler tail --env staging

# Tail production logs — filter to errors only
wrangler tail --env production --status error

# Tail with sampling (reduces noise in high-traffic production)
wrangler tail --env production --sampling-rate 0.01
```

---

## Anti-patterns

- **One environment for everything.** Using the top-level (dev) config for staging/production means test data contaminates production KV and D1.
- **Hardcoding environment names in Worker source.** Compare `env.ENVIRONMENT` for runtime branching, never read the Wrangler environment name at runtime (it is not exposed to the Worker).
- **Committing secrets to `wrangler.toml` via `[vars]`.** Vars are plaintext and visible in the Cloudflare dashboard. Use `wrangler secret put` for any sensitive value.
- **Sharing a single Cloudflare API token across all environments.** A leaked CI secret would allow deploys to all environments. Scope tokens per environment.
- **Using `--env` without also specifying a separate Worker name.** Without `name` in `[env.production]`, Wrangler overwrites the dev Worker when deploying production.

---

## Gotchas

- Environment names in `wrangler.toml` must be lowercase alphanumeric with hyphens. `env.prod-v2` is valid; `env.Prod` is not.
- `wrangler dev --env production` without `--remote` creates a local simulation that does NOT use production data — the `--remote` flag is required to connect to real Cloudflare resources.
- Workers names must be globally unique per Cloudflare account. `api-worker-staging` and `api-worker` are different Workers. Check your account before choosing names.
- `[env.staging]` does not inherit `[[kv_namespaces]]` from the top level — you must re-declare every binding in each environment stanza.
- `wrangler.toml` TOML array-of-tables (`[[env.staging.kv_namespaces]]`) syntax requires double brackets; missing one bracket causes a silent parse failure where the binding is ignored.

---

## Verification

```bash
# Confirm the correct Worker name resolves per environment
wrangler whoami
wrangler deployments list --env staging
wrangler deployments list --env production

# Check routes are correct
wrangler deploy --env staging --dry-run
wrangler deploy --env production --dry-run

# Verify no binding leakage between environments
curl https://staging-api.example.com/healthz | jq .environment
# Should return "staging"

curl https://api.example.com/healthz | jq .environment
# Should return "production"
```

---

## Related

- `cloudflare-workers-vitest-miniflare-testing.md` — test bindings that mirror each environment
- `github-actions-wrangler-deploy-pipeline.md` — full deploy pipeline
- `feature-flags-2026.md` — runtime feature flags across environments
- `workers-kv-r2-d1-storage-selection.md` — choosing the right binding type

---

## Sources

- Wrangler Environments docs — https://developers.cloudflare.com/workers/wrangler/environments/
- Cloudflare API Token scopes — https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- D1 Migrations docs — https://developers.cloudflare.com/d1/reference/migrations/
- GitHub Environments (approval gates) — https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
