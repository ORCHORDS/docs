# Multi-Account Deployment Strategies

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Enterprise teams and agencies operating Cloudflare workloads often maintain
separate Cloudflare accounts for each environment tier (development, staging,
production) or for each tenant (agency clients). A single Wrangler project
must target different account IDs, Workers, D1 databases, KV namespaces, and
R2 buckets depending on which account is being deployed to. Without a
deliberate strategy this leads to credential sprawl, accidental cross-account
deployments, and impossible-to-audit blast radii.

## Context

Cloudflare's account model is flat: each account owns its own Workers, KV
namespaces, D1 databases, R2 buckets, and Pages projects. There is no native
"sub-account" hierarchy. Cross-account access requires explicit API tokens
scoped to each account.

Wrangler reads the active account ID from (in priority order):
1. `CLOUDFLARE_ACCOUNT_ID` environment variable
2. `account_id` field in `wrangler.toml`
3. Interactive selection during `wrangler login`

This means account targeting is entirely controllable at the CI/CD level via
environment variables and secret stores, making per-account deployment
pipelines straightforward to implement without modifying `wrangler.toml`.

A complementary pattern is a monorepo where each environment has its own
`wrangler.<env>.toml` file that sets the correct account_id, binding IDs, and
Worker name prefix.

## Section 1: Account Credential Management in CI/CD

### Secret naming convention for multi-account pipelines

Store one API token per account in your CI secret store. Tokens should be
scoped to the minimum permissions needed for deployment (Edit Workers, Edit KV,
etc.) and never be admin tokens.

```
# GitHub Actions secrets naming convention
CF_API_TOKEN_DEV        → token for development account
CF_API_TOKEN_STAGING    → token for staging account
CF_API_TOKEN_PROD       → token for production account

CF_ACCOUNT_ID_DEV       → account ID for development
CF_ACCOUNT_ID_STAGING   → account ID for staging
CF_ACCOUNT_ID_PROD      → account ID for production
```

### GitHub Actions matrix deployment across accounts

```yaml
# .github/workflows/multi-account-deploy.yml
name: Multi-Account Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    strategy:
      fail-fast: true          # fail fast: don't promote to prod if staging fails
      matrix:
        include:
          - env: staging
            account_id_secret: CF_ACCOUNT_ID_STAGING
            api_token_secret: CF_API_TOKEN_STAGING
          - env: production
            account_id_secret: CF_ACCOUNT_ID_PROD
            api_token_secret: CF_API_TOKEN_PROD
    runs-on: ubuntu-latest
    environment: ${{ matrix.env }}
    needs: []
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Deploy to ${{ matrix.env }}
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets[matrix.account_id_secret] }}
          CLOUDFLARE_API_TOKEN: ${{ secrets[matrix.api_token_secret] }}
        run: |
          wrangler deploy \
            --config wrangler.${{ matrix.env }}.toml
```

### Per-environment wrangler configuration files

```toml
# wrangler.staging.toml
name = "api-gateway-staging"
main = "src/index.ts"
compatibility_date = "2026-01-01"
account_id = ""          # Intentionally blank; set via CLOUDFLARE_ACCOUNT_ID env var

[vars]
ENVIRONMENT = "staging"
LOG_LEVEL = "debug"

[[kv_namespaces]]
binding = "CACHE"
id = "aaa111bbb222ccc333ddd444eee555ff"   # staging KV namespace ID

[[d1_databases]]
binding = "DB"
database_name = "app-db-staging"
database_id = "staging-db-uuid-here"
```

```toml
# wrangler.production.toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2026-01-01"
account_id = ""          # Set via CLOUDFLARE_ACCOUNT_ID

[vars]
ENVIRONMENT = "production"
LOG_LEVEL = "warn"

[[kv_namespaces]]
binding = "CACHE"
id = "fff555eee444ddd333ccc222bbb111aa"   # production KV namespace ID

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "prod-db-uuid-here"
```

## Section 2: Cross-Account Data Migration and Promotion

Workers cannot directly access bindings (KV, R2, D1) belonging to a different
account. Data promotion from staging to production must go through an
intermediate step using Wrangler CLI or Cloudflare API calls from a build
agent that holds tokens for both accounts.

### KV namespace data promotion script

```bash
#!/usr/bin/env bash
# promote-kv.sh — copy KV keys from staging to production account
# Requires: CF_API_TOKEN_STAGING, CF_ACCOUNT_ID_STAGING,
#           CF_API_TOKEN_PROD, CF_ACCOUNT_ID_PROD

set -euo pipefail

STAGING_NS_ID="aaa111bbb222ccc333ddd444eee555ff"
PROD_NS_ID="fff555eee444ddd333ccc222bbb111aa"

echo "Exporting keys from staging..."
CLOUDFLARE_API_TOKEN="$CF_API_TOKEN_STAGING" \
CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID_STAGING" \
  wrangler kv key list \
    --namespace-id "$STAGING_NS_ID" \
    --json > /tmp/kv-keys.json

echo "Promoting $(jq length /tmp/kv-keys.json) keys to production..."

jq -r '.[].name' /tmp/kv-keys.json | while read -r key; do
  value=$(
    CLOUDFLARE_API_TOKEN="$CF_API_TOKEN_STAGING" \
    CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID_STAGING" \
      wrangler kv key get --namespace-id "$STAGING_NS_ID" "$key"
  )
  CLOUDFLARE_API_TOKEN="$CF_API_TOKEN_PROD" \
  CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID_PROD" \
    wrangler kv key put --namespace-id "$PROD_NS_ID" "$key" "$value"
done

echo "KV promotion complete."
```

### D1 schema promotion via SQL export

```bash
#!/usr/bin/env bash
# promote-d1-schema.sh — apply pending migrations to production D1

set -euo pipefail

echo "Applying D1 migrations to production..."
CLOUDFLARE_API_TOKEN="$CF_API_TOKEN_PROD" \
CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID_PROD" \
  wrangler d1 migrations apply app-db \
    --remote \
    --config wrangler.production.toml

echo "D1 migration promotion complete."
```

## Section 3: Account Isolation Enforcement

Preventing accidental cross-account deployments is as important as enabling
intentional ones. Enforce account isolation in CI by validating that the
deployed Worker's account_id matches the expected value for the target
environment.

### Post-deploy account validation script

```bash
#!/usr/bin/env bash
# validate-account.sh — assert Worker is deployed to the expected account

set -euo pipefail

EXPECTED_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID}"
WORKER_NAME="${1:?Usage: validate-account.sh <worker-name>}"

echo "Verifying Worker '$WORKER_NAME' belongs to account '$EXPECTED_ACCOUNT_ID'..."

ACTUAL_ACCOUNT=$(
  curl -s \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/accounts/${EXPECTED_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}" \
    | jq -r '.result.id // empty'
)

if [[ -z "$ACTUAL_ACCOUNT" ]]; then
  echo "ERROR: Worker '$WORKER_NAME' not found in account '$EXPECTED_ACCOUNT_ID'." >&2
  echo "Possible cross-account deployment — check CLOUDFLARE_ACCOUNT_ID." >&2
  exit 1
fi

echo "OK: Worker confirmed in expected account."
```

### Makefile targets for account-aware deployment

```makefile
# Makefile
.PHONY: deploy-staging deploy-production validate

deploy-staging:
    CLOUDFLARE_ACCOUNT_ID=$(CF_ACCOUNT_ID_STAGING) \
    CLOUDFLARE_API_TOKEN=$(CF_API_TOKEN_STAGING) \
      wrangler deploy --config wrangler.staging.toml
    CLOUDFLARE_ACCOUNT_ID=$(CF_ACCOUNT_ID_STAGING) \
    CLOUDFLARE_API_TOKEN=$(CF_API_TOKEN_STAGING) \
      bash scripts/validate-account.sh api-gateway-staging

deploy-production: deploy-staging
    CLOUDFLARE_ACCOUNT_ID=$(CF_ACCOUNT_ID_PROD) \
    CLOUDFLARE_API_TOKEN=$(CF_API_TOKEN_PROD) \
      wrangler deploy --config wrangler.production.toml
    CLOUDFLARE_ACCOUNT_ID=$(CF_ACCOUNT_ID_PROD) \
    CLOUDFLARE_API_TOKEN=$(CF_API_TOKEN_PROD) \
      bash scripts/validate-account.sh api-gateway
```

## Anti-patterns

- **Using a single admin API token across all accounts**: a leaked token
  compromises every environment simultaneously. Use per-account tokens with
  minimum required permissions.

- **Hard-coding account_id in wrangler.toml**: makes the same config file
  unusable for other accounts without modification, breaking the DRY principle
  and creating merge conflicts in multi-env repos.

- **Deploying staging and production in parallel**: staging must validate first.
  Use `fail-fast: true` and sequential job dependencies in CI.

- **Using `wrangler login` browser auth in CI**: this stores credentials in
  `~/.wrangler/config` which is ephemeral in CI runners. Always use
  `CLOUDFLARE_API_TOKEN` in automated pipelines.

- **Sharing KV namespaces or D1 databases across accounts**: Cloudflare does
  not support cross-account resource access from bindings. Shared resources
  must be accessed via an intermediate API Worker or exported/imported as data.

## Gotchas

- Cloudflare account IDs are UUIDs but are displayed without hyphens in the
  dashboard (32 hex chars). Both forms are accepted by the API; keep a
  consistent format in your config files to avoid drift.

- `wrangler.toml` `account_id` set to an empty string `""` causes Wrangler to
  prompt interactively. Set it to the actual value OR rely entirely on the
  `CLOUDFLARE_ACCOUNT_ID` env var; never use `""` in CI.

- Workers Service Bindings cannot cross account boundaries—a Worker in account
  A cannot bind to a Worker in account B. Cross-account Worker invocation must
  use HTTPS fetch to the Worker's public URL.

- Pages projects are account-scoped and do not inherit wrangler.toml
  `account_id`. Pages deployments triggered via Wrangler read
  `CLOUDFLARE_ACCOUNT_ID` from the environment.

## Verification

```bash
# List all Workers in the staging account
CLOUDFLARE_API_TOKEN="$CF_API_TOKEN_STAGING" \
CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID_STAGING" \
  wrangler deployments list --name api-gateway-staging

# Confirm production account is isolated
CLOUDFLARE_API_TOKEN="$CF_API_TOKEN_PROD" \
CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID_PROD" \
  wrangler deployments list --name api-gateway
# Should NOT show any staging workers

# Verify API token scopes for each account
curl -s -H "Authorization: Bearer $CF_API_TOKEN_PROD" \
  "https://api.cloudflare.com/client/v4/user/tokens/verify" | jq '.result'
```

## Related

- `secrets-management-wrangler-vault.md`
- `env-var-management-strategy.md`
- `oidc-federated-deploy-credentials.md`
- `multi-region-deployment.md`
- `cloudflare-workers-deploy-pipeline.md`

## Sources

- Wrangler account configuration: https://developers.cloudflare.com/workers/wrangler/configuration/#account-id
- Cloudflare API token permissions: https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- Workers limits and account model: https://developers.cloudflare.com/workers/platform/limits/
- Cross-account isolation guidance: https://developers.cloudflare.com/fundamentals/account-and-billing/account-setup/
