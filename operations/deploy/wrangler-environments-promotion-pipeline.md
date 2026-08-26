# Wrangler Named Environments Promotion Pipeline

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Teams running Cloudflare Workers across dev, staging, and production need a structured way to promote the same artifact through named Wrangler environments without duplicating `wrangler.toml` logic or leaking production secrets into lower environments.

## Context
Wrangler supports named environment blocks inside `wrangler.toml`. Each block can override bindings, vars, routes, and KV/D1 namespace IDs. A CI promotion pipeline should deploy to each environment in sequence, gating on smoke tests before advancing. Without an explicit promotion model, teams either deploy the same `wrangler deploy` command with environment-specific flags ad hoc, or maintain separate toml files that drift.

## wrangler.toml Environment Blocks
Define each environment as an isolated block sharing the same Worker name prefix.

```toml
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

kv_namespaces = [
  { binding = "CACHE", id = "dev-kv-id-placeholder" }
]

[env.staging]
name = "orchords-api-staging"
kv_namespaces = [
  { binding = "CACHE", id = "staging-kv-id" }
]
[env.staging.vars]
ENVIRONMENT = "staging"
LOG_LEVEL = "debug"

[env.production]
name = "orchords-api-production"
kv_namespaces = [
  { binding = "CACHE", id = "prod-kv-id" }
]
routes = [{ pattern = "api.example.com/*", zone_name = "example.com" }]
[env.production.vars]
ENVIRONMENT = "production"
LOG_LEVEL = "warn"
```

## TypeScript Worker with Environment-Aware Behaviour

```typescript
export interface Env {
  CACHE: KVNamespace;
  ENVIRONMENT: string;
  LOG_LEVEL: string;
}

function log(level: string, msg: string, env: Env): void {
  const levels = { debug: 0, info: 1, warn: 2, error: 3 };
  const threshold = levels[env.LOG_LEVEL as keyof typeof levels] ?? 1;
  if (levels[level as keyof typeof levels] >= threshold) {
    console.log(JSON.stringify({ level, msg, env: env.ENVIRONMENT }));
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    log("info", `Handling ${request.method} ${new URL(request.url).pathname}`, env);

    const cacheKey = new URL(request.url).pathname;
    const cached = await env.CACHE.get(cacheKey);
    if (cached) {
      log("debug", "Cache hit", env);
      return new Response(cached, { headers: { "X-Cache": "HIT" } });
    }

    const body = JSON.stringify({ env: env.ENVIRONMENT, path: cacheKey, ts: Date.now() });
    ctx.waitUntil(env.CACHE.put(cacheKey, body, { expirationTtl: 300 }));
    return new Response(body, { headers: { "Content-Type": "application/json", "X-Cache": "MISS" } });
  },
};
```

## CI Promotion Script
Use a sequential shell pipeline that deploys then smoke-tests before advancing.

```bash
#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENTS=("" "staging" "production")
SMOKE_URLS=(
  "https://orchords-api.orchords-api.workers.dev/health"
  "https://orchords-api-staging.orchords-api-staging.workers.dev/health"
  "https://api.example.com/health"
)

for i in "${!ENVIRONMENTS[@]}"; do
  ENV_FLAG="${ENVIRONMENTS[$i]}"
  SMOKE_URL="${SMOKE_URLS[$i]}"

  if [[ -z "$ENV_FLAG" ]]; then
    echo "Deploying to dev (default env)..."
    npx wrangler deploy
  else
    echo "Deploying to $ENV_FLAG..."
    npx wrangler deploy --env "$ENV_FLAG"
  fi

  echo "Smoke-testing $SMOKE_URL..."
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SMOKE_URL")
  if [[ "$STATUS" != "200" ]]; then
    echo "Smoke test failed for $ENV_FLAG (HTTP $STATUS). Halting promotion."
    exit 1
  fi
  echo "Smoke test passed for ${ENV_FLAG:-dev}."
done

echo "Full promotion pipeline complete."
```

## Secret Promotion via Wrangler Secrets

Production secrets must be set separately per environment. Never copy them from lower envs.

```typescript
// scripts/rotate-secret.ts — run with npx tsx
import { execSync } from "child_process";

const ENVIRONMENTS = ["staging", "production"] as const;
const SECRET_NAME = process.argv[2];
const SECRET_VALUE = process.env[`SECRET_${SECRET_NAME}`];

if (!SECRET_NAME || !SECRET_VALUE) {
  console.error("Usage: SECRET_MY_KEY=... tsx rotate-secret.ts MY_KEY");
  process.exit(1);
}

for (const env of ENVIRONMENTS) {
  console.log(`Setting ${SECRET_NAME} on env=${env}`);
  execSync(
    `echo "${SECRET_VALUE}" | npx wrangler secret put ${SECRET_NAME} --env ${env}`,
    { stdio: "inherit" }
  );
}
console.log("Secret rotation complete.");
```

## Deployment Verification Worker
A lightweight health-check endpoint to assert the correct environment is live.

```typescript
export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    const payload = {
      status: "ok",
      environment: env.ENVIRONMENT,
      version: __STATIC_CONTENT_MANIFEST ?? "unknown",
      timestamp: new Date().toISOString(),
    };
    return Response.json(payload);
  },
};
```

## Anti-patterns
- Maintaining separate `wrangler.toml` files per environment — they inevitably drift
- Sharing the same KV namespace ID across environments — data bleeds between stages
- Promoting to production without an intervening smoke-test gate
- Storing production route config in lower-environment blocks
- Using `--var` CLI overrides instead of wrangler.toml vars — not tracked in source control

## Gotchas
- `wrangler deploy` without `--env` deploys to the **root** (default) env, not `[env.dev]`; name your dev block explicitly or rely on the root
- KV namespace IDs are account-scoped; staging and production IDs must be provisioned separately via `wrangler kv namespace create`
- Secrets set with `wrangler secret put --env staging` are not visible to `wrangler dev` sessions against the default env
- Route patterns in `[env.production]` take precedence over the root block; double-defining them causes duplicate route errors
- `compatibility_date` in a named env block overrides the root value — keep it consistent or explicitly set it in every block

## Verification
```bash
# Confirm correct env is live
curl -s https://api.example.com/health | jq '.environment'
# Expected: "production"

# List deployed named environments
npx wrangler deployments list --env production

# Tail logs for staging only
npx wrangler tail orchords-api-staging
```

## Related
- `wrangler-tail-logs-deployment-verification.md`
- `workers-secrets-rotation-zero-downtime.md`
- `environment-parity-staging-production.md`
- `deploy-gate-e2e-tests-playwright-pages.md`

## Sources
- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/configuration/secrets/
