# Wrangler Secrets Bulk Management in CI

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Workers project grows from one environment to three (preview, staging, production) and from five secrets to thirty. Running `wrangler secret put KEY` interactively for each key × environment is error-prone and blocks automated deployments. Engineers copy secrets between environments by hand, forget to rotate them after a leak, and have no audit trail of which secrets each environment currently holds. A systematic approach — bulk secret management integrated into CI/CD — solves all three problems.

## Context
`wrangler secret put` stores an encrypted key-value pair in Cloudflare's secret store, bound to a specific Worker and environment. Secrets are never revealed after upload — only the key names are listable. Wrangler 3+ provides `wrangler secret bulk` (accepts a JSON file of key/value pairs), which is the primary mechanism for CI automation. Secrets are environment-scoped in `wrangler.toml` via `[env.<name>]` blocks, and the `--env` flag selects the target. Cloudflare also exposes a Secrets API (used internally by wrangler) that can be called directly when batch or cross-Worker automation is needed.

## wrangler.toml: declaring secret bindings

```toml
# wrangler.toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Declare secrets — these are the *names* only; values are stored in CF
[vars]
LOG_LEVEL = "info"   # non-secret env var

# Secrets referenced by binding name in the Worker
# wrangler.toml does NOT store values; only declares keys
# Values are set with `wrangler secret put` or `wrangler secret bulk`

[env.staging]
name = "api-gateway-staging"

[env.production]
name = "api-gateway-production"
```

```typescript
// src/index.ts — accessing secrets at runtime
export interface Env {
  DATABASE_URL: string;
  API_KEY: string;
  JWT_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const db = await connectDatabase(env.DATABASE_URL);
    // ...
  },
};
```

## Single-secret operations

```bash
# Upload a secret interactively (prompts for value)
wrangler secret put DATABASE_URL --env production

# Upload via stdin (non-interactive, safe for CI)
echo "postgresql://user:pass@host/db" | \
  wrangler secret put DATABASE_URL --env production

# List secrets (shows keys only, never values)
wrangler secret list --env production
# ┌─────────────────┬──────────────────────┐
# │ Name            │ Type                 │
# ├─────────────────┼──────────────────────┤
# │ DATABASE_URL    │ secret_text          │
# │ API_KEY         │ secret_text          │
# │ JWT_SECRET      │ secret_text          │
# └─────────────────┴──────────────────────┘

# Delete a secret
wrangler secret delete OLD_API_KEY --env production
```

## Bulk secret upload from a JSON file

```bash
# secrets.staging.json — DO NOT COMMIT THIS FILE
# Use .gitignore to exclude secrets.*.json
cat > secrets.staging.json <<'EOF'
{
  "DATABASE_URL": "postgresql://user:pass@staging-host/db",
  "API_KEY": "sk-staging-abc123",
  "JWT_SECRET": "staging-jwt-secret-value",
  "STRIPE_KEY": "sk_test_abc123",
  "SENDGRID_KEY": "SG.staging.key"
}
EOF

# Bulk upload — one API call per key internally, atomic on error
wrangler secret bulk secrets.staging.json --env staging

# Clean up the local file immediately after upload
rm secrets.staging.json

# Verify keys landed
wrangler secret list --env staging
```

## CI/CD: injecting secrets from GitHub Actions environment secrets

```yaml
# .github/workflows/deploy-production.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production    # GitHub environment with protection rules

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - uses: pnpm/action-setup@v3
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      # Step 1: Sync secrets from GitHub to Cloudflare via bulk JSON
      - name: Sync secrets to Cloudflare (production)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          # Build the JSON payload from GitHub environment secrets
          # Each secret is a separate GitHub secret; jq assembles the payload
          cat > /tmp/secrets.json <<EOF
          {
            "DATABASE_URL": "${{ secrets.DATABASE_URL }}",
            "API_KEY": "${{ secrets.API_KEY }}",
            "JWT_SECRET": "${{ secrets.JWT_SECRET }}",
            "STRIPE_KEY": "${{ secrets.STRIPE_KEY }}",
            "SENDGRID_KEY": "${{ secrets.SENDGRID_KEY }}"
          }
          EOF
          pnpm wrangler secret bulk /tmp/secrets.json --env production
          rm /tmp/secrets.json

      # Step 2: Deploy after secrets are in place
      - name: Deploy Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler deploy --env production
```

## Multi-environment secret sync script

```typescript
// scripts/sync-secrets.ts
import { execSync } from "node:child_process";
import { writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

type Environment = "staging" | "production";

interface SecretMap {

}

function syncSecrets(env: Environment, secrets: SecretMap): void {
  const tempFile = join(tmpdir(), `wrangler-secrets-${env}-${Date.now()}.json`);

  try {
    writeFileSync(tempFile, JSON.stringify(secrets, null, 2), { mode: 0o600 });
    console.log(`Syncing ${Object.keys(secrets).length} secrets to ${env}...`);

    execSync(`pnpm wrangler secret bulk ${tempFile} --env ${env}`, {
      stdio: "inherit",
      env: {
        ...process.env,
        CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN,
      },
    });

    console.log(`Verifying secrets on ${env}...`);
    execSync(`pnpm wrangler secret list --env ${env}`, { stdio: "inherit" });
  } finally {
    unlinkSync(tempFile);   // always delete even on error
  }
}

// Load secrets from process.env (GitHub Actions injects them)
const requiredKeys = [
  "DATABASE_URL",
  "API_KEY",
  "JWT_SECRET",
  "STRIPE_KEY",
  "SENDGRID_KEY",
] as const;

const missingKeys = requiredKeys.filter((k) => !process.env[k]);
if (missingKeys.length > 0) {
  console.error("Missing required env vars:", missingKeys);
  process.exit(1);
}

const secrets: SecretMap = Object.fromEntries(
  requiredKeys.map((k) => [k, process.env[k] as string])
);

const env = (process.env.DEPLOY_ENV ?? "staging") as Environment;
syncSecrets(env, secrets);
```

## Secret rotation workflow

```bash
#!/usr/bin/env bash
# scripts/rotate-secret.sh
# Rotate a single secret in all environments atomically.
set -euo pipefail

KEY="${1:?Usage: rotate-secret.sh KEY}"
NEW_VALUE="${2:?Usage: rotate-secret.sh KEY VALUE}"
ENVIRONMENTS=("staging" "production")

for ENV in "${ENVIRONMENTS[@]}"; do
  echo "==> Rotating ${KEY} in ${ENV}..."
  echo "${NEW_VALUE}" | wrangler secret put "${KEY}" --env "${ENV}"
  echo "==> Done: ${KEY} in ${ENV}"
done

echo ""
echo "Rotation complete. Verify with:"
for ENV in "${ENVIRONMENTS[@]}"; do
  echo "  wrangler secret list --env ${ENV}"
done
```

## Auditing secret key presence via the Cloudflare API

```typescript
// scripts/audit-secrets.ts
// Verify that every required secret key exists across all environments.
import { execSync } from "node:child_process";

const REQUIRED_SECRETS = [
  "DATABASE_URL",
  "API_KEY",
  "JWT_SECRET",
  "STRIPE_KEY",
  "SENDGRID_KEY",
];
const ENVIRONMENTS = ["staging", "production"] as const;

interface WranglerSecret {
  name: string;
  type: string;
}

function listSecrets(env: string): string[] {
  const out = execSync(
    `pnpm wrangler secret list --env ${env} --json`,
    { encoding: "utf8" }
  );
  return (JSON.parse(out) as WranglerSecret[]).map((s) => s.name);
}

let allPassed = true;

for (const env of ENVIRONMENTS) {
  const present = new Set(listSecrets(env));
  const missing = REQUIRED_SECRETS.filter((k) => !present.has(k));
  if (missing.length > 0) {
    console.error(`[${env}] MISSING secrets:`, missing);
    allPassed = false;
  } else {
    console.log(`[${env}] All ${REQUIRED_SECRETS.length} secrets present.`);
  }
}

if (!allPassed) process.exit(1);
```

## Anti-patterns
- Putting actual secret values in `wrangler.toml` under `[vars]` — `[vars]` is for non-sensitive environment variables visible in plain text in the config file and the dashboard.
- Committing a `secrets.json` file to the repository — even if the file is later deleted, the values remain in git history and are extractable with `git log -p`.
- Using `echo "value" | wrangler secret put` in a shell script where `set -x` is enabled — this echoes the value to the CI log.
- Uploading secrets before deploying in a separate job without a dependency gate — a race condition can leave a Worker running with stale secrets if a previous deploy completes before the new secrets propagate.
- Storing secrets in Cloudflare KV instead of the Wrangler secrets store — KV values are not encrypted at rest at the same security level as Worker secrets and are accessible to anyone with KV read permissions.

## Gotchas
- `wrangler secret bulk` requires a flat JSON object — nested objects are rejected. Flatten complex configs before upload.
- `wrangler secret list --json` is available in wrangler >= 3.22.0; earlier versions produce human-readable table output only, breaking the `JSON.parse` in audit scripts.
- GitHub Actions `environment: production` protection rules gate the job — if secrets are stored in the environment (not the repository), the job waits for required reviewers before executing. This is intentional for production but can stall automated deploy pipelines if misconfigured.
- Secrets take effect on the next Worker invocation after upload — there is no forced restart. Long-running Durable Objects retain the old binding until their isolate is evicted (typically within minutes).
- The Cloudflare API rate limit for secret writes is 1200 requests/5 minutes per account; `wrangler secret bulk` with 30+ secrets in rapid succession across multiple Workers can hit this limit during large migrations.

## Verification
```bash
# Confirm all required secrets exist in production
wrangler secret list --env production

# Confirm a specific key exists (exit 0) or is missing (exit 1)
wrangler secret list --env production --json \
  | jq -e '.[] | select(.name == "DATABASE_URL")' > /dev/null \
  && echo "DATABASE_URL present" || echo "DATABASE_URL MISSING"

# Run the full audit script
CLOUDFLARE_API_TOKEN="$CF_API_TOKEN" npx tsx scripts/audit-secrets.ts
```

## Related
- [wrangler-environments-staging-production.md](wrangler-environments-staging-production.md)
- [github-actions-wrangler-deploy-pipeline.md](github-actions-wrangler-deploy-pipeline.md)
- [secret-scanning-2026.md](secret-scanning-2026.md)
- [workers-d1-migration-ci-pipeline.md](workers-d1-migration-ci-pipeline.md)
- [cloudflare-workers-observability-tail-workers.md](cloudflare-workers-observability-tail-workers.md)

## Sources
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/wrangler/commands/#secret
- https://developers.cloudflare.com/api/operations/worker-bindings-list-bindings
- https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
