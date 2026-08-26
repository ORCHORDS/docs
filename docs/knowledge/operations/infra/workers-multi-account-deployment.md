# Multi-Account Cloudflare Workers Deployment Strategy

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your organization wants hard isolation between dev, staging, and production Cloudflare Workers environments — not just different namespaces in one account, but separate Cloudflare accounts entirely. This enforces billing isolation, prevents accidental prod changes from dev credentials, and lets you give engineers broad access to the dev account without risk to production.

## Context

Cloudflare accounts are the primary isolation boundary: Workers, KV namespaces, D1 databases, R2 buckets, and analytics are all account-scoped. An API token is tied to one account (or can span multiple with explicit permission grants). Service Bindings only work within the same account — cross-account Worker calls must use plain HTTPS fetch.

Typical org layout:
- `orchords-dev` account — engineers have Owner/Admin role, free-tier usage
- `orchords-staging` account — CI-only access, mirrors prod config
- `orchords-prod` account — CI-only access via scoped tokens, no human direct access

## Solution

```toml
# wrangler.toml — per-environment account_id overrides
name = "api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Dev (default / local)
account_id = "DEV_ACCOUNT_ID"

[vars]
ENVIRONMENT = "development"

[[kv_namespaces]]
binding = "CONFIG"
id = "dev-config-kv-id"

[env.staging]
account_id = "STAGING_ACCOUNT_ID"   # different account
name = "api"

[env.staging.vars]
ENVIRONMENT = "staging"

[[env.staging.kv_namespaces]]
binding = "CONFIG"
id = "staging-config-kv-id"

[[env.staging.routes]]
pattern = "api-staging.example.com/*"
zone_name = "example.com"

[env.production]
account_id = "PROD_ACCOUNT_ID"      # production account
name = "api"

[env.production.vars]
ENVIRONMENT = "production"

[[env.production.kv_namespaces]]
binding = "CONFIG"
id = "prod-config-kv-id"

[[env.production.routes]]
pattern = "api.example.com/*"
zone_name = "example.com"
```

```typescript
// src/index.ts — cross-account service call via fetch (no Service Bindings)
export interface Env {
  ENVIRONMENT: string;
  CONFIG: KVNamespace;
  // Service Bindings do NOT work cross-account.
  // Instead, call the downstream Worker via HTTPS.
  DOWNSTREAM_WORKER_URL: string;   // var per environment
  INTER_SERVICE_TOKEN: string;     // secret binding
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Cross-account Worker call — use fetch, NOT a Service Binding
    const downstreamResponse = await callDownstream(env, request);
    return downstreamResponse;
  },
};

async function callDownstream(env: Env, originalRequest: Request): Promise<Response> {
  const url = new URL(originalRequest.url);
  const downstreamUrl = `${env.DOWNSTREAM_WORKER_URL}${url.pathname}${url.search}`;

  const response = await fetch(downstreamUrl, {
    method: originalRequest.method,
    headers: {
      ...Object.fromEntries(originalRequest.headers),
      // Strip incoming auth, add inter-service token
      Authorization: `Bearer ${env.INTER_SERVICE_TOKEN}`,
      "X-Source-Account": env.ENVIRONMENT,
    },
    body: originalRequest.body,
  });

  return new Response(response.body, {
    status: response.status,
    headers: response.headers,
  });
}
```

```bash
# scripts/setup-accounts.sh — initial account bootstrap
# Run once per account after account creation.

set -euo pipefail

ENV=${1:?Usage: setup-accounts.sh <dev|staging|production>}

case $ENV in
  dev)
    export CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_DEV
    export CLOUDFLARE_ACCOUNT_ID=$CF_ACCOUNT_ID_DEV
    ;;
  staging)
    export CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_STAGING
    export CLOUDFLARE_ACCOUNT_ID=$CF_ACCOUNT_ID_STAGING
    ;;
  production)
    export CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_PROD
    export CLOUDFLARE_ACCOUNT_ID=$CF_ACCOUNT_ID_PROD
    ;;
esac

# Create KV namespace in the target account
wrangler kv:namespace create CONFIG --env $ENV

# Create D1 database
wrangler d1 create app-db-$ENV

# Create R2 bucket
wrangler r2 bucket create assets-$ENV

# Set secrets
wrangler secret put JWT_SECRET --env $ENV
wrangler secret put INTER_SERVICE_TOKEN --env $ENV

echo "Bootstrap complete for $ENV"
```

```yaml
# .github/workflows/multi-account-deploy.yml
name: Multi-Account Deploy

on:
  push:
    branches: [main, staging]

jobs:
  deploy-staging:
    if: github.ref == 'refs/heads/staging'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci && npm run build
      - name: Deploy to staging account
        run: npx wrangler deploy --env staging
        env:
          # Token scoped to STAGING_ACCOUNT_ID only
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}

  deploy-production:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci && npm run build
      - name: Deploy to production account
        run: npx wrangler deploy --env production
        env:
          # Token scoped to PROD_ACCOUNT_ID only — cannot touch dev/staging
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
```

```typescript
// scripts/verify-deployment.ts — post-deploy cross-account verification
import { execSync } from "child_process";

interface AccountConfig {
  env: string;
  apiToken: string;
  accountId: string;
  workerUrl: string;
}

async function verifyDeployment(config: AccountConfig): Promise<void> {
  // 1. Verify Worker is deployed
  const deployments = execSync(
    `CLOUDFLARE_API_TOKEN=${config.apiToken} wrangler deployments list --env ${config.env}`,
    { encoding: "utf-8" }
  );
  console.log(`[${config.env}] Deployments:\n`, deployments);

  // 2. Smoke-test the deployed URL
  const response = await fetch(`${config.workerUrl}/health`);
  if (!response.ok) {
    throw new Error(
      `[${config.env}] Health check failed: ${response.status} ${response.statusText}`
    );
  }
  const body = await response.json<{ env: string }>();
  if (body.env !== config.env) {
    throw new Error(
      `[${config.env}] Worker reported wrong environment: ${body.env}`
    );
  }

  console.log(`[${config.env}] Verification passed.`);
}

// Run against all environments
const configs: AccountConfig[] = [
  {
    env: "staging",
    apiToken: process.env.CF_API_TOKEN_STAGING!,
    accountId: process.env.CF_ACCOUNT_ID_STAGING!,
    workerUrl: "https://api-staging.example.com",
  },
  {
    env: "production",
    apiToken: process.env.CF_API_TOKEN_PROD!,
    accountId: process.env.CF_ACCOUNT_ID_PROD!,
    workerUrl: "https://api.example.com",
  },
];

Promise.all(configs.map(verifyDeployment)).catch(console.error);
```

## Implementation Details

**DNS routing between accounts** — if both accounts serve traffic under `example.com`, the zone must live in exactly one account. Route traffic to the other account's Worker via a CNAME or a Cloudflare Load Balancer origin pool. Alternatively, use `workers.dev` subdomains for staging (`api.orchords-staging.workers.dev`) and only attach the production zone to the prod account.

**Cost isolation** — each Cloudflare account has independent billing. Workers Paid plan ($5/month) must be enabled per account. This makes it easy to audit which environment consumed how many requests, CPU ms, and KV reads.

**Account-scoped API tokens** — create each token in its respective account dashboard:
- Dev token: Workers Scripts Edit + KV Edit + D1 Edit + R2 Edit (broad — engineers use this locally)
- Staging/Prod tokens: same permissions but restricted to CI IP ranges if supported

Store each token as a GitHub Actions environment secret mapped to the matching GitHub Environment (`staging`, `production`), ensuring only the right job can access the right token.

## Anti-patterns

- **Service Bindings across accounts** — not supported. Service Bindings require both Workers to be in the same account. Use HTTPS fetch with a shared secret token for cross-account Worker calls.
- **One API token with access to all three accounts** — if this token leaks, all environments are compromised. Use per-account tokens.
- **Human production access** — remove human accounts from the production Cloudflare account; all prod deploys via CI. Break-glass access via a time-limited token, not a permanent role.
- **Shared KV/D1 resource IDs across accounts** — each account has its own namespace; an ID from the dev account is invalid in the prod account.
- **Exposing `account_id` values as secrets** — account IDs are not secret; they're in API responses, docs, and URLs. Only `api_token` values need to be secret.

## Gotchas

- `wrangler deploy --env production` with the wrong `CLOUDFLARE_API_TOKEN` env var will fail with a 403 — this is a safety feature; check which token is active.
- Zone-based routes (`zone_name = "example.com"`) require the zone to exist and be active in the target account. If the zone is in the dev account, you cannot attach a prod-account Worker to it via zone routes — use a `workers.dev` route instead or transfer the zone.
- `wrangler tail` streams logs only for Workers in the account associated with the current `CLOUDFLARE_API_TOKEN`.
- Cloudflare Analytics Engine and Workers Analytics are per-account — you cannot query cross-account from a single dashboard.
- D1 database IDs are account-scoped; running `wrangler d1 migrations apply --database prod-db-id` requires the prod API token to be active.

## Verification

```bash
# Verify dev account Worker
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_DEV wrangler deployments list

# Verify staging account Worker
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_STAGING wrangler deployments list --env staging

# Verify production account Worker
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_PROD wrangler deployments list --env production

# Cross-account smoke tests
curl -sf https://api-staging.example.com/health | jq .env
curl -sf https://api.example.com/health | jq .env

# Confirm tokens cannot cross accounts (expect 403)
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN_DEV \
  curl -H "Authorization: Bearer $CF_API_TOKEN_DEV" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID_PROD/workers/scripts"
```

## Related

- `documentation/docs/policies/infra/workers-wrangler-environments-matrix.md`
- `documentation/docs/policies/infra/workers-terraform-cloudflare-provider.md`
- `documentation/docs/policies/infra/workers-traffic-splitting-ab-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/fundamentals/setup/manage-members/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/configuration/routing/routes/
