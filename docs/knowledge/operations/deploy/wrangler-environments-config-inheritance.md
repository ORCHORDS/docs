# Wrangler Environments Config Inheritance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Deploying with `--env production` picks up the wrong KV binding because you assumed `[env.production.kv_namespaces]` would merge with the top-level `[[kv_namespaces]]` block. Or `nodejs_compat` stops working in production because `compatibility_flags` was declared only at the top level. The inheritance model is partial and field-type-dependent, and misreading it causes silent production incidents.

## Context

Wrangler's environment system lets a single `wrangler.toml` target multiple Cloudflare accounts, routes, and bindings via `[env.staging]`, `[env.production]`, etc. Inheritance is **asymmetric**: scalar fields (`name`, `compatibility_date`, `main`) inherit from the base config if not redeclared; **array and table fields** (`routes`, `kv_namespaces`, `vars`, `d1_databases`, `compatibility_flags`) do **not merge** — an env block's array **completely replaces** the base. This replacement behaviour is the source of most multi-environment deploy bugs.

## 1. Field-by-Field Inheritance Reference

```toml
# wrangler.toml — annotated with inheritance behaviour per field

name = "my-worker"                 # INHERITED by env blocks that omit it (appends env suffix in older Wrangler)
main = "src/index.ts"              # INHERITED
compatibility_date = "2026-01-01"  # INHERITED — always declare at top level
account_id = "abc123"              # INHERITED

# ──────────────────────────────────────────────────────────────────────────────
# ARRAY / TABLE FIELDS: NOT inherited — each env block that declares one
# completely replaces the top-level value. Omitting the field in an env block
# does NOT inherit it; the binding is simply absent for that env.
# ──────────────────────────────────────────────────────────────────────────────
compatibility_flags = ["nodejs_compat"]  # NOT inherited by [env.*] blocks

[vars]
LOG_LEVEL = "debug"                # NOT merged — env [vars] replaces this entirely

[[kv_namespaces]]
binding = "CACHE"
id = "global-kv-id"               # NOT included in env deploys that declare their own

[[routes]]
pattern = "*.example.com/*"       # Only applies to the DEFAULT env (no --env flag)
zone_name = "example.com"

# ──────────────────────────────────────────────────────────────────────────────
[env.staging]
name = "my-worker-staging"         # Overrides top-level name
# compatibility_date: not declared → INHERITS "2026-01-01" from top level ✓
# compatibility_flags: not declared → ABSENT (NOT inherited) — nodejs_compat is off!

vars = { LOG_LEVEL = "debug", ENV = "staging" }  # Replaces [vars] entirely

[[env.staging.kv_namespaces]]
binding = "CACHE"
id = "staging-kv-id"              # Only this KV binding exists for staging

[[env.staging.routes]]
pattern = "staging.example.com/*"
zone_name = "example.com"

# ──────────────────────────────────────────────────────────────────────────────
[env.production]
name = "my-worker-production"
compatibility_flags = ["nodejs_compat"]  # Must redeclare — it was NOT inherited

vars = { LOG_LEVEL = "warn", ENV = "production" }

[[env.production.kv_namespaces]]
binding = "CACHE"
id = "production-kv-id"

[[env.production.routes]]
pattern = "example.com/*"
zone_name = "example.com"
```

## 2. The `compatibility_flags` Trap

```toml
# BAD — flags declared only at top level
compatibility_flags = ["nodejs_compat"]

[env.production]
name = "my-worker-production"
# nodejs_compat is NOT active in production — the env block implicitly
# overrides compatibility_flags to an empty array.

# GOOD — redeclare per environment
[env.production]
name = "my-worker-production"
compatibility_flags = ["nodejs_compat"]

[env.staging]
name = "my-worker-staging"
compatibility_flags = ["nodejs_compat"]
```

```typescript
// scripts/validate-compat-flags.ts — fail CI if required flags are missing per env
import { parse } from "@iarna/toml";
import { readFileSync } from "fs";

const REQUIRED_FLAGS = ["nodejs_compat"];
const config = parse(readFileSync("wrangler.toml", "utf8")) as {
  compatibility_flags?: string[];
  env?: Record<string, { compatibility_flags?: string[]; name?: string }>;
};

const envs = Object.keys(config.env ?? {});
for (const envName of envs) {
  const flags = config.env![envName].compatibility_flags ?? [];
  for (const flag of REQUIRED_FLAGS) {
    if (!flags.includes(flag)) {
      console.error(`[FAIL] env.${envName} is missing required compatibility_flag: ${flag}`);
      process.exit(1);
    }
  }
  console.log(`[OK] env.${envName}: ${flags.join(", ")}`);
}
```

## 3. The Routes Replacement Trap

```toml
# BAD — top-level routes are for the DEFAULT environment only
[[routes]]
pattern = "example.com/*"
zone_name = "example.com"

[env.production]
name = "my-worker-production"
# No [[env.production.routes]] declared → Worker deploys but attaches to NO routes.
# Production traffic never reaches it.

# GOOD — routes must be declared in every env that needs them
[[env.production.routes]]
pattern = "example.com/*"
zone_name = "example.com"

[[env.staging.routes]]
pattern = "staging.example.com/*"
zone_name = "example.com"
```

## 4. Auditing Effective Config Per Environment

```typescript
// scripts/audit-wrangler-envs.ts — resolve and diff effective config per env
import { execSync } from "child_process";
import { mkdirSync } from "fs";

const envs = ["staging", "production"] as const;

for (const env of envs) {
  const outDir = `/tmp/wrangler-dry-run-${env}`;
  mkdirSync(outDir, { recursive: true });
  console.log(`\n=== Dry-run for --env ${env} ===`);
  try {
    execSync(`npx wrangler deploy --env ${env} --dry-run --outdir ${outDir}`, {
      stdio: "inherit",
    });
    // Assert bundle was produced
    const files = execSync(`ls ${outDir}`).toString().trim();
    if (!files) throw new Error(`No output produced for env: ${env}`);
    console.log(`Bundle files: ${files}`);
  } catch (err) {
    console.error(`Config resolution failed for env: ${env}`, err);
    process.exit(1);
  }
}
```

## 5. JSON Config Inheritance Behaves Identically

```jsonc
// wrangler.jsonc — same replacement rules apply in JSON format
{
  "name": "my-worker",
  "compatibility_date": "2026-01-01",
  // Top-level kv_namespaces: ONLY active for the default env (no --env flag)
  "kv_namespaces": [{ "binding": "CACHE", "id": "global-id" }],

  "env": {
    "production": {
      "name": "my-worker-production",
      // This array REPLACES kv_namespaces entirely for --env production
      // "global-id" is NOT available in production
      "kv_namespaces": [{ "binding": "CACHE", "id": "prod-id" }],
      // compatibility_flags must be repeated here too
      "compatibility_flags": ["nodejs_compat"]
    }
  }
}
```

## 6. CI Validation — Enforce Correct Bindings Per Env

```yaml
# .github/workflows/wrangler-env-validation.yml
name: Wrangler Environment Config Validation
on:
  pull_request:
    paths: ["wrangler.toml", "wrangler.json", "wrangler.jsonc"]

jobs:
  validate:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        env: [staging, production]
    steps:
      - uses: actions/checkout@v4
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: deploy --env ${{ matrix.env }} --dry-run --outdir /tmp/wrangler-${{ matrix.env }}

      - name: Assert compatibility flags present
        run: |
          grep -r "nodejs_compat" /tmp/wrangler-${{ matrix.env }}/ \
            || (echo "::error::nodejs_compat missing in ${{ matrix.env }} bundle" && exit 1)

      - name: Validate compat flags per env
        run: npx tsx scripts/validate-compat-flags.ts
```

## Anti-patterns

- Assuming `[vars]` at the top level merges with `[env.production.vars]` — the env vars block replaces, not merges; any key not redeclared is absent in that environment.
- Declaring `compatibility_flags` only at the top level and expecting all environments to inherit them — they do not.
- Relying on the default environment's `[[routes]]` for production traffic — always declare routes explicitly in each env block.
- Using the same Worker `name` across environments (by omitting the override) — both environments deploy to the same Worker name and overwrite each other.

## Gotchas

- `workers_dev = true` at the top level does **not** propagate to env blocks; each env block independently determines if it publishes to a `workers.dev` subdomain.
- Secrets set via `wrangler secret put` are per-environment; `wrangler secret put --env production` sets a completely different value from `wrangler secret put --env staging`.
- `send_email`, `browser`, and `ai` bindings must be redeclared in each env block; they do not inherit.
- `wrangler deploy --env production` uses the env block's `name` as the Worker name in the Cloudflare dashboard — omitting `name` in the env block causes Wrangler to auto-generate `{base-name}-production`, which may not match existing route binding expectations.
- In `wrangler.json` / `wrangler.jsonc`, there is no `[[array]]` double-bracket syntax — arrays are standard JSON arrays, but the same replacement (not merge) semantics apply.

## Verification

```bash
# Inspect effective resolved config per environment
npx wrangler deploy --env staging    --dry-run --outdir /tmp/staging-bundle
npx wrangler deploy --env production --dry-run --outdir /tmp/production-bundle

# Confirm compatibility flags present in both bundles
grep -r "nodejs_compat" /tmp/staging-bundle/
grep -r "nodejs_compat" /tmp/production-bundle/

# List KV bindings Wrangler will use for each env
npx wrangler kv namespace list --env staging
npx wrangler kv namespace list --env production
```

## Related

- `wrangler-environments-promotion-pipeline.md`
- `env-binding-precedence.md`
- `env-var-management-strategy.md`
- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `wrangler-json-schema-config-validation-ci.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
