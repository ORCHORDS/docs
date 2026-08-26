# env-binding-precedence

**Issue:** Which env value wins — `wrangler.toml`, dashboard, secret
**Date:** 2026-08-09
**Status:** documented

## Symptom
You set a secret via `wrangler secret put FOO`. You also set
`FOO = "value"` in `wrangler.toml`. The secret is ignored; the
toml value is used. Or vice versa. The behavior is confusing.

## Root cause
CF Workers / Pages has 3 places to set env values:
1. **`wrangler.toml` `[vars]`** — committed, default values
2. **CF dashboard "Environment variables"** — web UI, overrides
   wrangler.toml
3. **`wrangler secret put`** — encrypted, overrides dashboard

The precedence is:
- **Secrets > Dashboard > wrangler.toml**
- For environments: `[env.preview.vars]` overrides `[vars]`
- Secrets are per-environment (production vs preview)

**Source:** CF docs:
https://developers.cloudflare.com/workers/configuration/environment-variables/

> "Secrets take precedence over non-secrets. The dashboard
> values override wrangler.toml values."

## Fix
A consistent naming + management pattern:

### Convention
- **`wrangler.toml`** — non-secret defaults (env name, feature
  flags, public API URLs)
- **Dashboard / secrets** — actual secrets (API keys, DB
  credentials)
- **NEVER** put secrets in `wrangler.toml` (visible in git)

```toml
# wrangler.toml
name = "example project-pages"
compatibility_date = "2026-08-01"

[vars]
ENVIRONMENT = "production"
API_BASE_URL = "https://api.example.com"
FEATURE_NEW_DASHBOARD = "true"
LOG_LEVEL = "info"

# Secrets (set via `wrangler secret put`):
# - DATABASE_URL
# - STRIPE_SECRET_KEY
# - CF_API_TOKEN
# - SENDGRID_API_KEY
```

### Set secrets via CLI
```bash
# Production
wrangler secret put DATABASE_URL --env production
# Interactive prompt for the value

# Preview
wrangler secret put DATABASE_URL --env preview
```

For CI:
```bash
echo "$DATABASE_URL" | wrangler secret put DATABASE_URL --env production
```

### Use the secrets in code
```ts
export interface Env {
  // From wrangler.toml [vars]
  ENVIRONMENT: string;
  API_BASE_URL: string;
  // From `wrangler secret put`
  DATABASE_URL: string;
  STRIPE_SECRET_KEY: string;
  // Bindings (not env vars)
  DB: D1Database;
  R2: R2Bucket;
  KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    // env.DATABASE_URL is the secret value
    // env.ENVIRONMENT is the toml value
  },
};
```

## Verification
- **Test:** `wrangler dev` loads both toml + secrets
- **Live:** Different values per environment (dev/staging/prod)
- **Audit:** Quarterly review of secrets vs toml values

## Gotchas
- **`wrangler.toml` is committed to git.** Don't put secrets in
  it. Even if you delete them later, the git history has them.
- **The dashboard shows env vars but not secret values** (for
  security). You can see "a secret called DATABASE_URL exists"
  but not its value.
- **Per-environment bindings** (D1, R2, KV) are configured
  per-environment in `wrangler.toml`:
  ```toml
  [[env.production.d1_databases]]
  binding = "DB"
  database_name = "example project-prod"
  database_id = "abc"

  [[env.preview.d1_databases]]
  binding = "DB"
  database_name = "example project-preview"
  database_id = "def"
  ```
- **`wrangler secret put` is one-at-a-time.** For bulk secrets,
  use a script:
  ```bash
  while IFS='=' read -r key value; do
    echo "$value" | wrangler secret put "$key" --env production
  done < .env.production
  ```
- **Secrets are not synced across environments.** Each
  environment has its own secrets. Don't assume production
  secret = preview secret.

## Related
- `wrangler-deploys.md`
- `secrets-rotation-runbook.md`
- CF env vars: https://developers.cloudflare.com/workers/configuration/environment-variables/
