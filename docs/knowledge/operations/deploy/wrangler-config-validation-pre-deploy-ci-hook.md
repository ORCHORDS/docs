# Wrangler Config Validation Pre-deploy CI Hook

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A `wrangler.toml` with a typo, an invalid binding reference, or an undefined environment key causes the deploy to fail mid-pipeline after minutes of build time. You want to catch configuration errors before any artifact is built or uploaded, failing fast at the start of CI rather than at the push step.

---

## Context

Wrangler does not expose a dedicated `wrangler validate` command (as of 2026). Validation must be assembled from a combination of:

1. JSON Schema linting of `wrangler.toml` / `wrangler.json`
2. `wrangler deploy --dry-run` to validate binding resolution
3. Custom scripts that assert required fields, binding names, and environment parity

This pre-deploy hook pattern gates the CI pipeline before any Cloudflare API call is made.

---

## Schema Linting with TypeScript

Use the `@cloudflare/workers-types` package and a TOML parser to validate the config structure before CI proceeds:

```typescript
// scripts/validate-wrangler-config.ts
import { readFileSync } from "fs";
import TOML from "@iarna/toml";

interface WranglerBinding {
  binding: string;
  id?: string;
  database_id?: string;
  bucket_name?: string;
}

interface WranglerEnvironment {
  name?: string;
  routes?: string[];
  kv_namespaces?: WranglerBinding[];
  d1_databases?: WranglerBinding[];
  r2_buckets?: WranglerBinding[];
  vars?: Record<string, string>;
}

interface WranglerConfig extends WranglerEnvironment {
  name: string;
  main: string;
  compatibility_date: string;
  env?: Record<string, WranglerEnvironment>;
}

function validateConfig(configPath: string): void {
  const raw = readFileSync(configPath, "utf-8");
  const config = TOML.parse(raw) as unknown as WranglerConfig;

  const errors: string[] = [];

  // Required top-level fields
  if (!config.name) errors.push("Missing required field: name");
  if (!config.main) errors.push("Missing required field: main");
  if (!config.compatibility_date) errors.push("Missing required field: compatibility_date");

  // Validate compatibility_date format
  if (config.compatibility_date && !/^\d{4}-\d{2}-\d{2}$/.test(config.compatibility_date)) {
    errors.push(`Invalid compatibility_date format: ${config.compatibility_date} (expected YYYY-MM-DD)`);
  }

  // Validate date is not in the future
  const compatDate = new Date(config.compatibility_date);
  if (compatDate > new Date()) {
    errors.push(`compatibility_date is in the future: ${config.compatibility_date}`);
  }

  // Validate binding names are unique per environment
  function checkBindingUniqueness(env: WranglerEnvironment, envName: string): void {
    const names: string[] = [
      ...(env.kv_namespaces?.map((b) => b.binding) ?? []),
      ...(env.d1_databases?.map((b) => b.binding) ?? []),
      ...(env.r2_buckets?.map((b) => b.binding) ?? []),
    ];
    const duplicates = names.filter((n, i) => names.indexOf(n) !== i);
    if (duplicates.length > 0) {
      errors.push(`Duplicate binding names in [${envName}]: ${duplicates.join(", ")}`);
    }
  }

  checkBindingUniqueness(config, "root");

  if (config.env) {
    for (const [envName, envConfig] of Object.entries(config.env)) {
      checkBindingUniqueness(envConfig, `env.${envName}`);
    }
  }

  if (errors.length > 0) {
    console.error("Wrangler config validation FAILED:");
    errors.forEach((e) => console.error(`  - ${e}`));
    process.exit(1);
  }

  console.log(`Wrangler config validated OK: ${configPath}`);
}

validateConfig(process.argv[2] || "wrangler.toml");
```

---

## Dry-run Validation via Wrangler

`wrangler deploy --dry-run` builds the bundle and resolves bindings locally without making any API calls or uploading anything:

```bash
# Validate production environment
wrangler deploy --dry-run --env production

# Validate staging environment
wrangler deploy --dry-run --env staging

# Outdir is required for dry-run to succeed (it writes the bundle there)
wrangler deploy --dry-run --outdir /tmp/wrangler-dry-run --env production
```

This catches: missing `main` entrypoint, broken imports, compatibility flag conflicts, and malformed binding declarations.

---

## Environment Parity Assertion

Ensure all required environments define the same set of bindings to prevent staging/production drift:

```typescript
// scripts/assert-env-parity.ts
import { readFileSync } from "fs";
import TOML from "@iarna/toml";

const REQUIRED_ENVIRONMENTS = ["staging", "production"];
const REQUIRED_BINDINGS = ["DB", "CACHE", "ASSETS_BUCKET"];

const raw = readFileSync("wrangler.toml", "utf-8");
const config = TOML.parse(raw) as any;

const errors: string[] = [];

for (const envName of REQUIRED_ENVIRONMENTS) {
  const env = config.env?.[envName];
  if (!env) {
    errors.push(`Missing environment: [env.${envName}]`);
    continue;
  }

  const definedBindings = [
    ...(env.kv_namespaces?.map((b: any) => b.binding) ?? []),
    ...(env.d1_databases?.map((b: any) => b.binding) ?? []),
    ...(env.r2_buckets?.map((b: any) => b.binding) ?? []),
  ];

  for (const required of REQUIRED_BINDINGS) {
    if (!definedBindings.includes(required)) {
      errors.push(`[env.${envName}] missing binding: ${required}`);
    }
  }
}

if (errors.length > 0) {
  errors.forEach((e) => console.error(e));
  process.exit(1);
}

console.log("Environment parity check passed");
```

---

## GitHub Actions Pre-deploy Gate

```yaml
# .github/workflows/deploy-worker.yml
name: Deploy Worker

on:
  push:
    branches: [main]

jobs:
  validate:
    name: Validate Wrangler Config
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install dependencies
        run: npm ci

      - name: Validate wrangler.toml schema
        run: npx ts-node scripts/validate-wrangler-config.ts wrangler.toml

      - name: Assert environment parity
        run: npx ts-node scripts/assert-env-parity.ts

      - name: Wrangler dry-run (staging)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --dry-run --outdir /tmp/dry-run --env staging

      - name: Wrangler dry-run (production)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --dry-run --outdir /tmp/dry-run --env production

  deploy:
    name: Deploy
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - name: Deploy to production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --env production
```

---

## Compatibility Date Freshness Gate

Prevent deploying with a compatibility date older than 180 days to avoid accumulating compatibility flag debt:

```typescript
// scripts/check-compat-date.ts
import { readFileSync } from "fs";
import TOML from "@iarna/toml";

const MAX_AGE_DAYS = 180;
const raw = readFileSync("wrangler.toml", "utf-8");
const config = TOML.parse(raw) as any;
const compatDate = new Date(config.compatibility_date);
const ageMs = Date.now() - compatDate.getTime();
const ageDays = Math.floor(ageMs / (1000 * 60 * 60 * 24));

if (ageDays > MAX_AGE_DAYS) {
  console.warn(
    `WARNING: compatibility_date is ${ageDays} days old (${config.compatibility_date}). ` +
    `Consider bumping it to pick up the latest platform improvements.`
  );
  // Warn only — don't fail; compatibility bumps require testing
}

console.log(`compatibility_date age: ${ageDays} days`);
```

---

## Anti-patterns

- **Running `wrangler deploy` directly without a prior dry-run gate** — you discover config errors after upload begins.
- **Validating only the root config and skipping `[env.*]` blocks** — environment-specific binding errors go undetected until the environment is targeted.
- **Using `wrangler deploy --dry-run` as the sole validation step** — it does not catch semantic errors like duplicate binding names or missing required `vars`.
- **Skipping parity checks between staging and production** — production can reference bindings not tested in staging.
- **Treating config validation as optional** — make it the first job in the pipeline with no `continue-on-error`.

---

## Gotchas

- `wrangler deploy --dry-run` requires a valid `CLOUDFLARE_API_TOKEN` even though it makes no actual API calls (it authenticates the token at startup).
- The `--outdir` flag is required for `--dry-run`; without it, the command may error on some Wrangler versions.
- TOML parsing libraries vary in their treatment of inline tables vs dotted keys — test your parser against the actual `wrangler.toml` syntax used.
- Wrangler v3 changed `wrangler.toml` field names (`kv-namespaces` became `kv_namespaces`) — ensure the validator targets the correct version.
- `compatibility_flags` entries are not validated locally by Wrangler; invalid flags only surface at deploy time.

---

## Verification

```bash
# Run full pre-deploy validation locally
npx ts-node scripts/validate-wrangler-config.ts
npx ts-node scripts/assert-env-parity.ts
npx wrangler deploy --dry-run --outdir /tmp/dry-run --env production && echo "Dry-run OK"
```

---

## Related

- `wrangler-environments-promotion-pipeline.md`
- `env-binding-precedence.md`
- `deploy-gate-antipatterns.md`
- `workers-bundle-analysis-regression-ci.md`
- `environment-parity-staging-production.md`

---

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
