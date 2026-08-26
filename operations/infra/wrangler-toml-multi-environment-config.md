# wrangler-toml-multi-environment-config

**Issue:** Structuring wrangler.toml for dev / staging / production
         with per-environment bindings, secrets, and vars without
         duplicating config or leaking production values
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

The Worker deploys with `wrangler deploy` and picks up the wrong
database. Production code queries the staging D1 bucket because
`wrangler.toml` has a single `[[d1_databases]]` block. Or the
Worker in `dev` hits the live KV namespace because environments
were never separated. Adding `[env.staging]` blocks fixes it but
inheriting the right top-level config while overriding only the
bindings is not obvious from the docs.

## Context

`wrangler.toml` supports named environments under `[env.<name>]`.
Each environment can inherit from the top-level config and selec-
tively override bindings, routes, variables, and worker names.
Secrets are never in `wrangler.toml` — they are uploaded with
`wrangler secret put` and stored encrypted in Cloudflare's infra.
The relationship between top-level values and `[env.*]` overrides
has specific rules about what inherits and what must be redeclared.

---

## Inheritance Rules

| Key type                | Inherits from top?  | Override in env?    |
|-------------------------|---------------------|---------------------|
| `name`                  | Yes (prefixed)      | Yes (rename worker) |
| `main`                  | Yes                 | Yes                 |
| `compatibility_date`    | Yes                 | Yes                 |
| `[vars]`                | No — must redeclare | Yes                 |
| `[[kv_namespaces]]`     | No — must redeclare | Yes                 |
| `[[d1_databases]]`      | No — must redeclare | Yes                 |
| `[[r2_buckets]]`        | No — must redeclare | Yes                 |
| `[[routes]]`            | No — must redeclare | Yes                 |
| `[[custom_domains]]`    | No — must redeclare | Yes                 |
| `[triggers]` (crons)    | No — must redeclare | Yes                 |
| Secrets (wrangler put)  | Per env, encrypted  | Separate upload     |

Bindings (KV, D1, R2) and vars do NOT inherit from the top-level
block. They must be explicitly listed under each `[env.*]` block.
Only scalar fields like `main`, `compatibility_date`, and `name`
inherit.

---

## Full Reference wrangler.toml

```toml
# wrangler.toml
name            = "my-worker"         # base name; envs override
main            = "src/index.ts"
compatibility_date = "2025-10-01"
workers_dev     = false               # disable *.workers.dev globally

# ── Development (default, used by `wrangler dev`) ────────────────
[vars]
ENVIRONMENT = "development"
API_BASE_URL = "http://localhost:8787"

[[kv_namespaces]]
binding      = "CACHE"
id           = "aaaa0000000000000000000000000001"  # local / preview
preview_id   = "aaaa0000000000000000000000000001"

[[d1_databases]]
binding      = "DB"
database_name = "myapp-dev"
database_id  = "bbbb0000-0000-0000-0000-000000000001"

[[r2_buckets]]
binding      = "UPLOADS"
bucket_name  = "myapp-uploads-dev"

# ── Staging ──────────────────────────────────────────────────────
[env.staging]
name = "my-worker-staging"

[env.staging.vars]
ENVIRONMENT  = "staging"
API_BASE_URL = "https://api-staging.example.com"

[[env.staging.kv_namespaces]]
binding    = "CACHE"
id         = "cccc0000000000000000000000000001"
preview_id = "cccc0000000000000000000000000001"

[[env.staging.d1_databases]]
binding       = "DB"
database_name = "myapp-staging"
database_id   = "dddd0000-0000-0000-0000-000000000001"

[[env.staging.r2_buckets]]
binding     = "UPLOADS"
bucket_name = "myapp-uploads-staging"

[[env.staging.routes]]
pattern   = "api-staging.example.com/*"
zone_name = "example.com"

# ── Production ───────────────────────────────────────────────────
[env.production]
name = "my-worker-production"

[env.production.vars]
ENVIRONMENT  = "production"
API_BASE_URL = "https://api.example.com"

[[env.production.kv_namespaces]]
binding    = "CACHE"
id         = "eeee0000000000000000000000000001"
preview_id = "eeee0000000000000000000000000001"

[[env.production.d1_databases]]
binding       = "DB"
database_name = "myapp-production"
database_id   = "ffff0000-0000-0000-0000-000000000001"

[[env.production.r2_buckets]]
binding     = "UPLOADS"
bucket_name = "myapp-uploads-production"

[[env.production.custom_domains]]
pattern = "api.example.com"

[env.production.triggers]
crons = ["0 */6 * * *"]   # every 6 hours, production only
```

---

## Deploying to Environments

```bash
# Local dev (uses top-level config by default)
wrangler dev

# Deploy to staging
wrangler deploy --env staging

# Deploy to production
wrangler deploy --env production

# Tail logs from production
wrangler tail --env production

# Check which worker is deployed where
wrangler deployments list --env production
```

---

## Vars vs Secrets

`[vars]` values are stored in plaintext in `wrangler.toml` and
are visible to anyone with repo access. Use them for non-sensitive
per-environment configuration.

```toml
# OK in vars — non-sensitive
[env.production.vars]
FEATURE_FLAG_NEW_CHECKOUT = "true"
MAX_UPLOAD_MB             = "50"
LOG_LEVEL                 = "warn"
```

Secrets are encrypted at rest by Cloudflare and injected at
runtime. They must be uploaded separately per environment:

```bash
# Upload a secret to staging
wrangler secret put DATABASE_URL --env staging
# → prompts for value, encrypts, stores in CF

# Upload to production
wrangler secret put DATABASE_URL --env production

# List secrets (names only, not values)
wrangler secret list --env production

# Delete a secret
wrangler secret delete OLD_API_KEY --env production
```

In TypeScript, both vars and secrets appear on `env`:

```ts
interface Env {
  // Var — set in wrangler.toml [vars]
  ENVIRONMENT: string;
  // Secret — uploaded via wrangler secret put
  DATABASE_URL: string;
  // Binding
  DB: D1Database;
  CACHE: KVNamespace;
  UPLOADS: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // At runtime, env.DATABASE_URL is the secret value
    // env.ENVIRONMENT is the var value
    // env.DB is the D1 binding
    return new Response(env.ENVIRONMENT);
  },
};
```

---

## CI/CD Environment Patterns

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}

  deploy-production:
    runs-on: ubuntu-latest
    environment: production
    needs: deploy-staging
    steps:
      - uses: actions/checkout@v4
      - run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
```

Use separate CF API tokens scoped to each environment's Worker
so a compromised staging token cannot deploy to production.

---

## Anti-patterns

- **Putting secrets in `[vars]` or directly in wrangler.toml.**
  They appear in plaintext in git history. Use `wrangler secret
  put` exclusively for credentials.
- **Sharing a single D1 database ID across dev and production.**
  A migration gone wrong in dev will corrupt production data.
  Always provision separate databases per environment.
- **Relying on env name string matching inside the Worker.**
  `env.ENVIRONMENT === "production"` is acceptable, but do not
  gate security controls on it — gate them on the presence of
  required secrets or signed JWTs instead.
- **Putting `preview_id` as the same as `id` for production KV.**
  The `preview_id` namespace is used by `wrangler dev` when not
  in local mode. Giving it the production namespace means `wrangler
  dev` will read from and write to live production KV.

## Gotchas

- `workers_dev = false` in the top-level block does not carry into
  `[env.*]` blocks. Declare `workers_dev = false` explicitly in
  each env block if you want to disable `.workers.dev` per env.
- Secrets uploaded without `--env` go to the default "production"
  environment (i.e., the Worker deployed without `--env`). The
  env naming is distinct from the wrangler.toml `[env.*]` naming.
- Wrangler will reject a deployment if a binding declared in
  `wrangler.toml` does not exist in the Cloudflare account. Create
  KV namespaces, D1 databases, and R2 buckets before first deploy.
- `[env.production]` inside wrangler.toml is a wrangler concept.
  The Worker's internal name registered with Cloudflare is the
  `name` field, not the env key.
- Route and custom domain conflicts: two Workers cannot claim the
  same route pattern. Staging routes must be on a subdomain that
  does not overlap with production patterns.

## Verification

```bash
# Confirm the correct D1 database is bound
wrangler d1 list --env production
# → shows database_name matching production config

# Confirm secrets are set
wrangler secret list --env production
# → DATABASE_URL, STRIPE_KEY listed (values hidden)

# Smoke test staging
curl https://api-staging.example.com/health
# → {"env":"staging","db":"myapp-staging"}

# Smoke test production
curl https://api.example.com/health
# → {"env":"production","db":"myapp-production"}
```

## Related

- `cloudflare/wrangler-toml-reference.md`
- `cloudflare/wrangler-toml-public-exposure.md`
- `cloudflare/d1-best-practices.md`
- `cloudflare/kv-best-practices.md`
- `infra/secrets-management-comparison.md`

## Source URLs

- https://developers.cloudflare.com/workers/wrangler/
  configuration/
- https://developers.cloudflare.com/workers/wrangler/commands/
  #secret
- https://developers.cloudflare.com/workers/platform/
  environments/
