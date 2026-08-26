# Maintaining Staging/Production Environment Parity for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A bug reaches production that was not caught in staging because the staging Worker was bound to a KV namespace that did not exist in the production configuration, silently returning empty results instead of errors. Teams need a systematic way to verify that staging and production binding shapes are identical before any promotion.

---

## Context

Cloudflare Workers `wrangler.toml` supports `[env.staging]` and `[env.production]` sections that share the same script but bind to different named resources (separate D1 databases, KV namespaces, R2 buckets). Parity means the binding *names* (the keys the TypeScript code accesses via `env.*`) are identical across environments; the underlying resource IDs differ. A parity-check script queries the Cloudflare API for each environment's deployed bindings and diffs the sets, failing CI if the names diverge. Promoting staging to production is a deliberate CI step that re-applies the production Terraform/wrangler config from the same commit SHA that passed staging tests.

---

## Section 1 — wrangler.toml with environment sections

```toml
# wrangler.toml
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

# ── Shared settings (inherited by all envs unless overridden) ─────────────────
[vars]
LOG_LEVEL = "info"

# ── Staging ───────────────────────────────────────────────────────────────────
[env.staging]
name = "orchords-api-staging"

[env.staging.vars]
ENVIRONMENT = "staging"
LOG_LEVEL   = "debug"

[[env.staging.d1_databases]]
binding       = "DB"
database_name = "orchords-staging"
database_id   = "<staging-db-uuid>"

[[env.staging.kv_namespaces]]
binding     = "CACHE"
id          = "<staging-kv-id>"
preview_id  = "<staging-kv-preview-id>"

[[env.staging.r2_buckets]]
binding     = "ASSETS"
bucket_name = "orchords-assets-staging"

[[env.staging.analytics_engine_datasets]]
binding = "AE"
dataset = "workers_events_staging"

# ── Production ────────────────────────────────────────────────────────────────
[env.production]
name = "orchords-api-production"

[env.production.vars]
ENVIRONMENT = "production"
LOG_LEVEL   = "warn"

[[env.production.d1_databases]]
binding       = "DB"
database_name = "orchords-main"
database_id   = "<prod-db-uuid>"

[[env.production.kv_namespaces]]
binding     = "CACHE"
id          = "<prod-kv-id>"
preview_id  = "<prod-kv-preview-id>"

[[env.production.r2_buckets]]
binding     = "ASSETS"
bucket_name = "orchords-assets-production"

[[env.production.analytics_engine_datasets]]
binding = "AE"
dataset = "workers_events_production"
```

---

## Section 2 — Parity-check script

```typescript
// scripts/check-parity.ts
// Run with: bun scripts/check-parity.ts
// Exits with code 1 if binding names diverge between environments

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;
const STAGING_WORKER    = "orchords-api-staging";
const PRODUCTION_WORKER = "orchords-api-production";

interface Binding {
  name: string;
  type: string;
}

interface WorkerSettings {
  result: { bindings: Binding[] };
}

async function getBindings(workerName: string): Promise<Binding[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${workerName}/bindings`,
    {
      headers: { Authorization: `Bearer ${API_TOKEN}` },
    }
  );
  if (!res.ok) {
    throw new Error(
      `Failed to fetch bindings for ${workerName}: ${res.status} ${await res.text()}`
    );
  }
  const data = (await res.json()) as WorkerSettings;
  return data.result.bindings ?? [];
}

function bindingKey(b: Binding): string {
  return `${b.type}::${b.name}`;
}

async function checkParity(): Promise<void> {
  const [stagingBindings, prodBindings] = await Promise.all([
    getBindings(STAGING_WORKER),
    getBindings(PRODUCTION_WORKER),
  ]);

  const stagingKeys = new Set(stagingBindings.map(bindingKey));
  const prodKeys    = new Set(prodBindings.map(bindingKey));

  const onlyInStaging = [...stagingKeys].filter((k) => !prodKeys.has(k));
  const onlyInProd    = [...prodKeys].filter((k) => !stagingKeys.has(k));

  if (onlyInStaging.length === 0 && onlyInProd.length === 0) {
    console.log("✓ Staging and production bindings are in parity.");
    console.log("  Bindings:", [...stagingKeys].join(", "));
    process.exit(0);
  }

  if (onlyInStaging.length > 0) {
    console.error("PARITY FAIL — bindings in staging but NOT in production:");
    onlyInStaging.forEach((k) => console.error(`  - ${k}`));
  }
  if (onlyInProd.length > 0) {
    console.error("PARITY FAIL — bindings in production but NOT in staging:");
    onlyInProd.forEach((k) => console.error(`  - ${k}`));
  }

  process.exit(1);
}

await checkParity();
```

---

## Section 3 — CI pipeline: deploy staging, check parity, promote to production

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]

env:
  CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  CF_API_TOKEN:  ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run build

      - name: Deploy to staging
        run: npx wrangler deploy --env staging

      - name: Run integration tests against staging
        run: npm run test:integration
        env:
          TEST_BASE_URL: https://orchords-api-staging.orchords.workers.dev

  parity-check:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v1
      - run: bun scripts/check-parity.ts
        # Fails the pipeline if binding names differ

  deploy-production:
    needs: parity-check
    runs-on: ubuntu-latest
    environment: production   # Requires manual approval in GitHub Environments
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run build

      - name: Deploy to production
        run: npx wrangler deploy --env production

      - name: Smoke test production
        run: |
          STATUS=$(curl -sf -o /dev/null -w "%{http_code}" https://api.example.com/health)
          if [ "$STATUS" != "200" ]; then
            echo "Production smoke test failed with status $STATUS"
            exit 1
          fi
          echo "Production smoke test passed."
```

---

## Anti-patterns

- **Using different binding names across environments** — TypeScript code that references `env.DB` in staging but `env.DATABASE` in production will throw a runtime TypeError in one environment; binding names must be identical.
- **Promoting staging to production by copying resource IDs** — Environments should reference their own resource IDs; copying the staging D1 database ID into production means both environments share the same database.
- **Skipping the parity check when adding a new binding** — Adding a KV namespace to production without adding it to staging causes parity drift; always update both `[env.staging.*]` and `[env.production.*]` in the same commit.
- **Using the default (no environment) worker script for production** — The `name` field without an `[env.*]` suffix deploys to the default script slot; explicitly using `--env production` makes the intent unambiguous and avoids accidental production deploys from local machines.

---

## Gotchas

- `wrangler deploy --env staging` uses the `[env.staging]` name override (`orchords-api-staging`) for the script name; the deployed script name in the dashboard will differ from the `name` field at the top of `wrangler.toml`.
- `[[env.staging.d1_databases]]` uses double brackets (array of tables in TOML); a single `[env.staging.d1_databases]` silently creates a table instead of an array entry and wrangler will reject the config at parse time.
- Secrets set with `wrangler secret put --env staging` are scoped to the staging script name; they are not shared with the production script even if the secret name is the same.
- The parity-check script queries the *deployed* bindings via the API, not the `wrangler.toml` file; it catches drift that occurs when someone manually adds a binding in the dashboard without updating the config file.

---

## Verification

```bash
# Deploy to staging and inspect its bindings
npx wrangler deploy --env staging --dry-run

# Manually run the parity check
bun scripts/check-parity.ts

# List deployed bindings for both scripts via wrangler
npx wrangler deployments list --env staging
npx wrangler deployments list --env production

# Confirm correct environment var is set
curl -sf https://orchords-api-staging.orchords.workers.dev/env \
  | jq .ENVIRONMENT
# Expected: "staging"

curl -sf https://api.example.com/env \
  | jq .ENVIRONMENT
# Expected: "production"
```

---

## Related

- `terraform-cloudflare-workers-d1-iac.md`
- `cloudflare-dns-workers-route-management.md`
- `cloudflare-access-service-token-workers.md`

---

## Sources

- Wrangler Environments — https://developers.cloudflare.com/workers/wrangler/environments/
- Cloudflare Workers Bindings API — https://developers.cloudflare.com/api/operations/worker-binding-get-bindings
- GitHub Environments for Deployment Protection — https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
