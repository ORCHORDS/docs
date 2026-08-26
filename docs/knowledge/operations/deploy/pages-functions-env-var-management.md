# Pages Functions Environment Variable Management

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Cloudflare Pages Functions behave differently from Workers when it comes to
environment variables: plain-text vars and secrets are configured separately
in the Pages dashboard, cannot be set with `wrangler secret put`, and are
scoped to either production (main branch) or preview (all other branches).
Teams regularly hit the problem of missing env vars on preview deployments
because they set them only for production, or they hard-code secrets in
`wrangler.toml` because they don't know about the Pages-specific secret API.
This article covers the full lifecycle: local dev, preview, and production.

## Context

Pages Functions run on the same Workers runtime but their configuration surface
differs from standalone Workers:

| Feature | Workers | Pages Functions |
|---|---|---|
| `wrangler secret put` | Yes | No (use Pages API) |
| `wrangler.toml` `[vars]` | Yes | Yes (build-time only, not runtime) |
| Dashboard env vars | Yes | Yes (production + preview separate) |
| `.dev.vars` for local dev | Yes | Yes |
| KV / D1 / R2 bindings | `wrangler.toml` | `wrangler.toml` `[env.production]` |

The critical distinction: for Pages Functions, `[vars]` in `wrangler.toml`
affects the **build-time** Wrangler invocation, not runtime. Runtime
environment variables for Pages Functions are set via the Cloudflare dashboard
or the Pages API. Secrets are never visible in `wrangler.toml`.

Local development reads `.dev.vars` (same as Workers) and the `[vars]` section
in `wrangler.toml`.

## Section 1: Local Development Variables

### .dev.vars file (never commit)

```bash
# functions/.dev.vars  — gitignored, read by wrangler pages dev
DATABASE_URL=postgres://localhost:5432/myapp_dev
API_SECRET=dev-secret-not-real
STRIPE_KEY=sk_test_xxxxxxxxxxxxx
ENVIRONMENT=development
```

### wrangler.toml for Pages with per-environment vars

```toml
# wrangler.toml at project root
name = "my-pages-app"
compatibility_date = "2026-01-01"
pages_build_output_dir = "./dist"

# Plain-text vars available to both preview and production (non-sensitive)
[vars]
APP_NAME = "My App"
SUPPORT_EMAIL = "support@example.com"
API_BASE_URL = "https://api.example.com"

# KV binding for preview deployments
[[kv_namespaces]]
binding = "FEATURE_FLAGS"
id = "preview-kv-namespace-id"

[env.production]
# Vars that differ in production
[env.production.vars]
APP_NAME = "My App"
API_BASE_URL = "https://api.example.com"
SUPPORT_EMAIL = "support@example.com"

[[env.production.kv_namespaces]]
binding = "FEATURE_FLAGS"
id = "production-kv-namespace-id"

[[env.production.d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "production-db-uuid"
```

### Start local dev server

```bash
# Pages Functions dev server — reads .dev.vars and wrangler.toml [vars]
wrangler pages dev ./dist --compatibility-date 2026-01-01

# With explicit .dev.vars path
wrangler pages dev ./dist --env-file ./functions/.dev.vars
```

## Section 2: Managing Secrets via the Pages API

Pages does not expose secrets through `wrangler secret put`. Use the Cloudflare
REST API or the dashboard. All secrets are write-only (not readable after
setting) and are scoped to production or preview independently.

### Set a secret for production only

```bash
#!/usr/bin/env bash
# set-pages-secret.sh — set a secret on a Pages project
# Usage: ACCOUNT_ID=xxx PROJECT=my-app bash set-pages-secret.sh STRIPE_KEY sk_live_...

set -euo pipefail

ACCOUNT_ID="${ACCOUNT_ID:?}"
PROJECT="${PROJECT:?}"
SECRET_NAME="${1:?Secret name required}"
SECRET_VALUE="${2:?Secret value required}"
ENVIRONMENT="${ENVIRONMENT:-production}"  # "production" or "preview"

curl -s -X PATCH \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}" \
  --data "$(jq -n \
    --arg name "$SECRET_NAME" \
    --arg val "$SECRET_VALUE" \
    --arg env "$ENVIRONMENT" \
    '{deployment_configs: {($env): {env_vars: {($name): {type: "secret_text", value: $val}}}}}'
  )" \
  | jq '.success'
```

### Set the same secret for both production and preview

```bash
#!/usr/bin/env bash
# set-pages-secret-all-envs.sh

set -euo pipefail

ACCOUNT_ID="${ACCOUNT_ID:?}"
PROJECT="${PROJECT:?}"
SECRET_NAME="${1:?}"
SECRET_VALUE="${2:?}"

PAYLOAD=$(jq -n \
  --arg name "$SECRET_NAME" \
  --arg val "$SECRET_VALUE" \
  '{
    deployment_configs: {
      production: {env_vars: {($name): {type: "secret_text", value: $val}}},
      preview:    {env_vars: {($name): {type: "secret_text", value: $val}}}
    }
  }')

curl -s -X PATCH \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}" \
  --data "$PAYLOAD" \
  | jq '{success, errors}'
```

### List current environment variable names (values are redacted for secrets)

```bash
curl -s \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}" \
  | jq '.result.deployment_configs | {
      production_vars: .production.env_vars | keys,
      preview_vars: .preview.env_vars | keys
    }'
```

### Delete an environment variable or secret

```bash
#!/usr/bin/env bash
# delete-pages-env-var.sh

ACCOUNT_ID="${ACCOUNT_ID:?}"
PROJECT="${PROJECT:?}"
VAR_NAME="${1:?}"

# Passing null removes the variable
curl -s -X PATCH \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}" \
  --data "$(jq -n \
    --arg name "$VAR_NAME" \
    '{deployment_configs: {production: {env_vars: {($name): null}}}}'
  )" \
  | jq '{success, errors}'
```

## Section 3: CI/CD Integration and Parity Enforcement

### GitHub Actions workflow with Pages secret management

```yaml
# .github/workflows/pages-deploy.yml
name: Pages Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: npm ci && npm run build

      - name: Sync production secrets to Pages
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          PROJECT: my-pages-app
          STRIPE_KEY: ${{ secrets.STRIPE_LIVE_KEY }}
          DATABASE_URL: ${{ secrets.PROD_DATABASE_URL }}
        run: |
          bash scripts/set-pages-secret.sh STRIPE_KEY "$STRIPE_KEY"
          bash scripts/set-pages-secret.sh DATABASE_URL "$DATABASE_URL"

      - name: Deploy to Pages
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: wrangler pages deploy ./dist --project-name my-pages-app

      - name: Verify required env vars are present
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: bash scripts/verify-pages-env-vars.sh my-pages-app
```

### verify-pages-env-vars.sh — assert required vars exist post-deploy

```bash
#!/usr/bin/env bash
# verify-pages-env-vars.sh
# Usage: bash verify-pages-env-vars.sh <project-name>

set -euo pipefail

PROJECT="${1:?project name required}"
ACCOUNT_ID="${ACCOUNT_ID:?}"

REQUIRED_VARS=(
  STRIPE_KEY
  DATABASE_URL
  APP_NAME
  SUPPORT_EMAIL
)

echo "Checking Pages project: $PROJECT"

PROD_VARS=$(
  curl -s \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}" \
    | jq -r '.result.deployment_configs.production.env_vars | keys[]'
)

MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
  if ! echo "$PROD_VARS" | grep -qx "$var"; then
    MISSING+=("$var")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "ERROR: Missing required env vars in production: ${MISSING[*]}" >&2
  exit 1
fi

echo "OK: All required env vars present in production."
```

## Anti-patterns

- **Storing secrets in `wrangler.toml` `[vars]`**: plain-text vars in
  `wrangler.toml` are committed to source control and appear in build logs.
  Only non-sensitive configuration belongs in `[vars]`.

- **Setting env vars only for production and forgetting preview**: preview
  deployments (PR branches) will fail silently or with cryptic errors if
  they lack required secrets. Set secrets for both environments unless the
  feature is intentionally disabled in preview.

- **Using `wrangler secret put` for Pages secrets**: this command targets
  standalone Workers, not Pages projects. It silently creates a standalone
  Worker secret unrelated to your Pages project.

- **Mixing `.dev.vars` with committed `wrangler.toml` vars for sensitive data**:
  `.dev.vars` is gitignored by default—verify this in `.gitignore`. Never let
  `.dev.vars` be committed.

- **Assuming build-time `[vars]` in `wrangler.toml` are runtime vars**: they
  are not. If a Pages Function reads `env.MY_VAR`, that value must come from
  the Pages dashboard or API, not just from `wrangler.toml`.

## Gotchas

- Pages secrets are write-only: once set, their value cannot be retrieved via
  the API. Maintain a secrets inventory in a secrets manager (e.g., 1Password,
  AWS Secrets Manager) outside of Cloudflare.

- When you PATCH the Pages project deployment config, the entire `env_vars`
  object for that environment is merged, not replaced. To delete a var, pass
  its key with a `null` value.

- Preview deployments in Pages always inherit the "preview" environment config
  regardless of branch name. You cannot configure separate env vars for
  individual PR branches.

- Pages Functions do not support `wrangler secret list`—use the REST API to
  enumerate configured var names (values remain hidden).

- Changes to env vars in the dashboard take effect on the next deployment
  trigger, not immediately. Re-deploy after updating secrets.

## Verification

```bash
# Confirm env var names are configured for both environments
curl -s \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/my-pages-app" \
  | jq '.result.deployment_configs | {
      production: (.production.env_vars | keys),
      preview:    (.preview.env_vars | keys)
    }'

# Trigger a new production deployment to apply latest env var changes
wrangler pages deploy ./dist \
  --project-name my-pages-app \
  --branch main

# Check the most recent deployment's environment
curl -s \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/my-pages-app/deployments?per_page=1" \
  | jq '.result[0] | {id, url, environment, created_on}'
```

## Related

- `env-var-management-strategy.md`
- `secrets-management-wrangler-vault.md`
- `cloudflare-pages-preview-deployments.md`
- `environment-parity-staging-production.md`
- `pages-deployment-hooks-post-deploy-scripts.md`

## Sources

- Pages deployment configuration: https://developers.cloudflare.com/pages/configuration/build-configuration/
- Pages Functions bindings: https://developers.cloudflare.com/pages/functions/bindings/
- Pages REST API (project PATCH): https://developers.cloudflare.com/api/operations/pages-project-edit-project
- `.dev.vars` for local Pages dev: https://developers.cloudflare.com/pages/functions/local-development/
