# Environment Promotion Pipeline (dev → staging → production) for Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your team merges code to `main` and manually runs `wrangler deploy --env production`. There are no gates, no canary checks, and no audit trail. A bad deploy reaches production within minutes of merge. You need a structured promotion pipeline where code graduates from dev → staging → production only after passing automated quality gates at each stage.

## Context

Wrangler's `[env]` stanzas let you deploy the same Worker code to multiple named environments with different bindings, secrets, and routes. A GitHub Actions workflow can enforce promotion gates: unit tests, integration tests against staging, and canary error-rate checks before touching production. A D1 database provides a durable, queryable audit log of every promotion event.

## Solution

### wrangler.toml multi-environment configuration

```toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[vars]
APP_ENV = "dev"

[[kv_namespaces]]
binding = "CACHE"
id = "<dev-kv-id>"

[[d1_databases]]
binding = "DB"
database_name = "api-db-dev"
database_id = "<dev-d1-id>"

[env.staging]
vars = { APP_ENV = "staging" }

  [[env.staging.kv_namespaces]]
  binding = "CACHE"
  id = "<staging-kv-id>"

  [[env.staging.d1_databases]]
  binding = "DB"
  database_name = "api-db-staging"
  database_id = "<staging-d1-id>"

  [env.staging.routes]
  pattern = "staging-api.example.com/*"
  zone_name = "example.com"

[env.production]
vars = { APP_ENV = "production" }

  [[env.production.kv_namespaces]]
  binding = "CACHE"
  id = "<prod-kv-id>"

  [[env.production.d1_databases]]
  binding = "DB"
  database_name = "api-db-production"
  database_id = "<prod-d1-id>"

  [env.production.routes]
  pattern = "api.example.com/*"
  zone_name = "example.com"
```

### Environment-specific secrets

Secrets are set per environment and are never present in wrangler.toml:

```bash
# dev
wrangler secret put DATABASE_URL --env dev
# staging
wrangler secret put DATABASE_URL --env staging
# production
wrangler secret put DATABASE_URL --env production
```

In CI, use GitHub environment secrets scoped to the `staging` and `production` GitHub environments:

```yaml
# .github/workflows/promote.yml (partial)
env:
  CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

### D1 promotion audit log schema

```sql
-- migrations/0001_create_promotion_log.sql
CREATE TABLE IF NOT EXISTS promotion_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  sha         TEXT    NOT NULL,
  from_env    TEXT    NOT NULL,
  to_env      TEXT    NOT NULL,
  triggered_by TEXT   NOT NULL,
  status      TEXT    NOT NULL CHECK(status IN ('pending','success','failure','rollback')),
  gate_results TEXT,  -- JSON blob of gate check outcomes
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  completed_at TEXT
);

CREATE INDEX idx_promo_sha ON promotion_log(sha);
CREATE INDEX idx_promo_env ON promotion_log(to_env, created_at);
```

### Promotion audit logger (TypeScript)

```typescript
// src/lib/promotion-audit.ts
import Cloudflare from "cloudflare";

export interface GateResult {
  name: string;
  passed: boolean;
  detail: string;
}

export interface PromotionRecord {
  sha: string;
  fromEnv: string;
  toEnv: string;
  triggeredBy: string;
  status: "pending" | "success" | "failure" | "rollback";
  gateResults?: GateResult[];
}

export async function logPromotion(
  db: D1Database,
  record: PromotionRecord
): Promise<number> {
  const result = await db
    .prepare(
      `INSERT INTO promotion_log (sha, from_env, to_env, triggered_by, status, gate_results)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(
      record.sha,
      record.fromEnv,
      record.toEnv,
      record.triggeredBy,
      record.status,
      record.gateResults ? JSON.stringify(record.gateResults) : null
    )
    .run();
  return result.meta.last_row_id as number;
}

export async function updatePromotionStatus(
  db: D1Database,
  id: number,
  status: PromotionRecord["status"],
  gateResults?: GateResult[]
): Promise<void> {
  await db
    .prepare(
      `UPDATE promotion_log
       SET status = ?, gate_results = ?, completed_at = datetime('now')
       WHERE id = ?`
    )
    .bind(
      status,
      gateResults ? JSON.stringify(gateResults) : null,
      id
    )
    .run();
}
```

### GitHub Actions promotion workflow

```yaml
# .github/workflows/promote.yml
name: Promote Worker

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      target_env:
        description: "Target environment (staging|production)"
        required: true
        default: staging

jobs:
  deploy-dev:
    runs-on: ubuntu-latest
    environment: dev
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci
      - run: npm test
      - name: Deploy to dev
        run: npx wrangler deploy --env dev
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

  gate-dev:
    needs: deploy-dev
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - name: Integration tests against dev
        run: npm run test:integration -- --env dev
        env:
          BASE_URL: https://dev-api.example.com

  deploy-staging:
    needs: gate-dev
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci
      - name: Deploy to staging
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      - name: Log promotion to audit D1
        run: node scripts/log-promotion.mjs staging
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          AUDIT_D1_ID: ${{ secrets.AUDIT_D1_ID }}
          GIT_SHA: ${{ github.sha }}
          TRIGGERED_BY: ${{ github.actor }}

  gate-staging:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - name: Smoke tests against staging
        run: npm run test:smoke -- --env staging
        env:
          BASE_URL: https://staging-api.example.com
      - name: Canary metric gate (10-minute soak)
        run: node scripts/canary-gate.mjs --env staging --window 10m --error-threshold 0.5
        env:
          ANALYTICS_TOKEN: ${{ secrets.ANALYTICS_TOKEN }}

  deploy-production:
    needs: gate-staging
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval via GitHub environment protection
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci
      - name: Deploy to production
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      - name: Log promotion to audit D1
        run: node scripts/log-promotion.mjs production
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          AUDIT_D1_ID: ${{ secrets.AUDIT_D1_ID }}
          GIT_SHA: ${{ github.sha }}
          TRIGGERED_BY: ${{ github.actor }}
```

### Canary metric gate script

```typescript
// scripts/canary-gate.ts
const args = Object.fromEntries(
  process.argv.slice(2).reduce<string[][]>((acc, arg, i, arr) => {
    if (arg.startsWith("--")) acc.push([arg.slice(2), arr[i + 1]]);
    return acc;
  }, [])
);

const env = args["env"] ?? "staging";
const window = args["window"] ?? "10m";
const threshold = parseFloat(args["error-threshold"] ?? "1.0");

async function getErrorRate(environment: string, window: string): Promise<number> {
  const res = await fetch(
    `https://analytics.example.com/workers/error-rate?env=${environment}&window=${window}`,
    { headers: { Authorization: `Bearer ${process.env.ANALYTICS_TOKEN}` } }
  );
  if (!res.ok) throw new Error(`Analytics API error: ${res.status}`);
  const data = (await res.json()) as { error_rate: number };
  return data.error_rate;
}

(async () => {
  console.log(`Checking error rate for ${env} over ${window}...`);
  const rate = await getErrorRate(env, window);
  console.log(`Error rate: ${rate.toFixed(3)}%`);
  if (rate > threshold) {
    console.error(`GATE FAILED: ${rate}% > threshold ${threshold}%`);
    process.exit(1);
  }
  console.log("GATE PASSED");
})();
```

## Implementation Details

- GitHub environment protection rules on the `production` environment add a required manual reviewer step between `gate-staging` and `deploy-production`. This gives the team a final human gate before prod.
- D1 audit log lives in a dedicated `api-db-audit` database, not per-environment, so the full promotion history across all environments is queryable in one place.
- Wrangler picks up `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` environment variables automatically — no flags needed in the deploy commands.
- Use `wrangler versions upload` + `wrangler versions deploy` (the new Gradual Deployments API) instead of `wrangler deploy` to unlock native percentage-based traffic splitting at the Worker level without the KV trick.

## Anti-patterns

- **Shared bindings across environments**: Using the same KV namespace or D1 database ID in dev and staging contaminates production-quality data with test data.
- **Skipping staging integration tests**: Treating staging as purely a traffic gate (no functional tests) means regressions only surface in production.
- **Storing secrets in wrangler.toml vars**: `vars` are plain-text in the bundle. Credentials must be set via `wrangler secret put`.
- **No audit log**: Without a record of who promoted what SHA and when, incident post-mortems have no authoritative source of truth.

## Gotchas

- `wrangler deploy --env production` without a GitHub environment protection rule is just as risky as a direct deploy. The protection rule must be configured in the GitHub repository settings, not in the workflow file.
- Wrangler environment names in `wrangler.toml` must match exactly the `--env` flag value. A mismatch silently deploys to the default (dev) environment.
- D1 does not support cross-database joins. If you need to correlate promotion records with application data, replicate or export the audit log separately.
- `wrangler secret list --env production` shows secret names but not values. Document which secrets each environment needs in your runbook, not in code.

## Verification

```bash
# List all promotion records for the last SHA
wrangler d1 execute api-db-audit \
  --command "SELECT * FROM promotion_log WHERE sha = '$(git rev-parse HEAD)' ORDER BY created_at DESC" \
  --remote

# Confirm the production Worker version matches the expected SHA
wrangler deployments list --env production

# Tail production logs after promotion
wrangler tail api-worker --env production --format pretty
```

## Related

- `workers-gradual-traffic-migration-routes.md`
- `workers-deployment-verification-smoke-tests.md`
- `wrangler-deploy-preview-pr-environments.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/d1/
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
