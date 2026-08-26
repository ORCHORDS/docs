# Wrangler Config Inheritance Environments Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example project Workers monorepo has grown to six environments — local, preview, staging, canary, production-us, production-eu — each with overlapping but distinct `wrangler.toml` settings. Copy-pasting the full config into each `[env.*]` block means every binding change must be applied in six places, causing drift and silent misconfiguration. Understanding how Wrangler merges top-level config with environment overrides prevents this.

## Context

Wrangler's `wrangler.toml` supports an environment system where the top-level table defines base configuration and `[env.<name>]` blocks override specific fields. Wrangler does not do deep-merge on all fields: some fields (like `vars` and `kv_namespaces`) are shallow-merged or fully replaced depending on the field type. Knowing the exact merge semantics for each field type is the difference between a clean DRY config and a subtle production misconfiguration.

## Top-Level vs Environment Field Merge Semantics

Wrangler applies the following rules when merging top-level config with an environment block:

| Field type | Merge behaviour |
|---|---|
| `name` | Replaced: env overrides the Worker name |
| `vars` | Shallow-merged: env adds/overrides individual keys |
| `kv_namespaces` | Replaced: env must list ALL KV bindings it needs |
| `r2_buckets` | Replaced: env must list ALL R2 bindings |
| `d1_databases` | Replaced: env must list ALL D1 bindings |
| `services` | Replaced: env must list ALL service bindings |
| `compatibility_date` | Replaced by env if specified |
| `compatibility_flags` | Replaced by env if specified (not additive) |
| `build.command` | Replaced by env if specified |

```toml
# wrangler.toml — base config shared by all environments
name = "example project-api"
main = "src/index.ts"
compatibility_date = "2026-06-01"
compatibility_flags = ["nodejs_compat"]

[vars]
APP_ENV = "local"
LOG_LEVEL = "debug"
API_VERSION = "v2"

[[kv_namespaces]]
binding = "SESSION_STORE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # local preview namespace

[[r2_buckets]]
binding = "MEDIA"
bucket_name = "example project-media-local"

[[d1_databases]]
binding = "DB"
database_name = "example project-db-local"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

## Defining Environment Overrides

Because binding arrays are **replaced** (not merged), every environment must redeclare all bindings it uses. Use TOML `[[env.<name>.kv_namespaces]]` array-of-tables syntax.

```toml
# Staging environment — overrides name, vars, and all binding IDs
[env.staging]
name = "example project-api-staging"

[env.staging.vars]
APP_ENV = "staging"
LOG_LEVEL = "info"
# API_VERSION inherits from top-level? NO — vars ARE shallow-merged.
# So API_VERSION = "v2" is inherited here automatically.

[[env.staging.kv_namespaces]]
binding = "SESSION_STORE"
id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01"

[[env.staging.r2_buckets]]
binding = "MEDIA"
bucket_name = "example project-media-staging"

[[env.staging.d1_databases]]
binding = "DB"
database_name = "example project-db-staging"
database_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

# Production-US
[env.production-us]
name = "example project-api-production-us"

[env.production-us.vars]
APP_ENV = "production"
LOG_LEVEL = "warn"

[[env.production-us.kv_namespaces]]
binding = "SESSION_STORE"
id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb01"

[[env.production-us.r2_buckets]]
binding = "MEDIA"
bucket_name = "example project-media-production"

[[env.production-us.d1_databases]]
binding = "DB"
database_name = "example project-db-production"
database_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
```

## Extracting Shared Config with TOML Anchors

TOML does not support native anchors or includes. Instead, keep shared non-binding config in the top-level table and write a generation script for the binding arrays — or use Wrangler's `--config` flag to compose multiple partial config files.

For monorepo Workers with many shared settings, a generation script keeps config DRY:

```typescript
// scripts/generate-wrangler-config.ts
import { writeFileSync } from "fs";
import { stringify } from "@iarna/toml";

const ENVS = {
  staging: {
    kvSessionId: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01",
    r2Bucket: "example project-media-staging",
    d1Id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    logLevel: "info",
  },
  "production-us": {
    kvSessionId: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb01",
    r2Bucket: "example project-media-production",
    d1Id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    logLevel: "warn",
  },
} as const;

function buildConfig() {
  const base = {
    name: "example project-api",
    main: "src/index.ts",
    compatibility_date: "2026-06-01",
    compatibility_flags: ["nodejs_compat"],
    vars: { APP_ENV: "local", LOG_LEVEL: "debug", API_VERSION: "v2" },
    kv_namespaces: [{ binding: "SESSION_STORE", id: "local-kv-id" }],
    r2_buckets: [{ binding: "MEDIA", bucket_name: "example project-media-local" }],
    d1_databases: [{ binding: "DB", database_name: "example project-db-local", database_id: "local-d1-id" }],
    env: {} as Record<string, unknown>,
  };

  for (const [name, cfg] of Object.entries(ENVS)) {
    base.env[name] = {
      name: `example project-api-${name}`,
      vars: { APP_ENV: name.startsWith("production") ? "production" : name, LOG_LEVEL: cfg.logLevel },
      kv_namespaces: [{ binding: "SESSION_STORE", id: cfg.kvSessionId }],
      r2_buckets: [{ binding: "MEDIA", bucket_name: cfg.r2Bucket }],
      d1_databases: [{ binding: "DB", database_name: `example project-db-${name}`, database_id: cfg.d1Id }],
    };
  }

  writeFileSync("wrangler.toml", stringify(base as never));
  console.log("wrangler.toml generated");
}

buildConfig();
```

Run as a pre-build step: `tsx scripts/generate-wrangler-config.ts && wrangler deploy --env production-us`.

## Validating Config Inheritance in CI

Add a CI check that deploys with `--dry-run` to catch binding misconfiguration before a real deploy:

```yaml
# .github/workflows/validate-config.yml
jobs:
  validate-wrangler-config:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - name: Validate staging config
        run: wrangler deploy --env staging --dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      - name: Validate production-us config
        run: wrangler deploy --env production-us --dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

`--dry-run` validates that all referenced binding IDs exist in the Cloudflare account and that the config parses correctly, without uploading any code.

## Anti-patterns

- Assuming `kv_namespaces`, `r2_buckets`, or `d1_databases` are merged across environments — they are not; an env block without these arrays will have no bindings at all, silently breaking the Worker.
- Duplicating `compatibility_flags` across every env block instead of setting it once at the top level — any flag added at the top level later will be ignored by envs that have their own `compatibility_flags` array.
- Storing secrets as `vars` — use `wrangler secret put` instead; secrets set via the API are not listed in `wrangler.toml` and are not committed to git.
- Using the same D1 `database_id` for both staging and production — a migration run against staging will mutate the production database.
- Hardcoding Worker names without environment suffixes — two envs deploying the same name will overwrite each other's Worker scripts.

## Gotchas

- `vars` IS shallow-merged: an env block only needs to specify the vars it wants to override or add; unspecified vars inherit from the top level.
- All array-of-tables fields (`kv_namespaces`, `d1_databases`, `r2_buckets`, `services`, `durable_objects.bindings`) are **replaced**, not merged. Document this explicitly for all contributors.
- `wrangler dev` without `--env` uses the top-level (local) config. Forgetting `--env staging` in a local test will use local binding IDs.
- `wrangler.toml` is evaluated at deploy time, not at Worker runtime. Environment variable substitution (like `${MY_VAR}`) is not supported in `wrangler.toml`; use `wrangler secret` or `vars` with literal values.
- The `name` field determines the Worker script name in Cloudflare. Changing `name` in an env block deploys a NEW Worker, not an update to the existing one, leaving the old Worker script running until manually deleted.

## Verification

Run `wrangler deploy --env staging --dry-run --json | jq '.bindings'` and confirm that all expected bindings (KV, R2, D1) appear with the correct staging IDs. Compare the output against a known-good manifest stored in `ci/expected-bindings.staging.json` to catch drift.

## Related

- wrangler-environments-staging-production.md
- wrangler-secrets-bulk-management-ci.md
- workers-d1-migration-ci-pipeline.md
- git-config-conditional-includes-workers-environments.md
- multi-environment-branch-strategy.md

## Sources

- https://developers.cloudflare.com/workers/wrangler/configuration/#environments
- https://developers.cloudflare.com/workers/wrangler/configuration/#bindings
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://toml.io/en/v1.0.0
