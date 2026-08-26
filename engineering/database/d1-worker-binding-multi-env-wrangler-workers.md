# D1 Multi-Environment Binding — Wrangler Configuration Patterns for Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You maintain separate D1 databases for local development, staging, and production but end up
manually swapping database IDs in `wrangler.toml` before each deployment, or accidentally point
a staging deploy at the production database. You want an explicit, version-controlled configuration
where each environment unambiguously names its own D1 binding with no manual editing required at
deploy time.

## Context

Wrangler 3 supports named environments via `[env.<name>]` stanzas in `wrangler.toml` (or
`wrangler.jsonc`). Each environment stanza can override or extend the top-level bindings
section. For D1, this means each environment gets its own `[[env.<name>.d1_databases]]` block
with its own `database_id`.

Key concepts:

- The **top-level** `[[d1_databases]]` stanza is used when no `--env` flag is supplied (local
  development default).
- `wrangler deploy --env staging` and `wrangler deploy --env production` each resolve their own
  database IDs without touching the others.
- TypeScript code binds to the logical **binding name** (e.g., `DB`) not to a database ID, so
  the same application code runs against different databases per environment.
- Secrets and vars can also be environment-scoped, making it straightforward to co-locate
  environment-specific configuration.

## wrangler.toml Structure

```toml
# wrangler.toml
name = "myapp"
main = "src/index.ts"
compatibility_date = "2024-09-23"

# ── Local / default environment ──────────────────────────────────────────────
[[d1_databases]]
binding     = "DB"
database_name = "myapp-local"
database_id   = "00000000-0000-0000-0000-000000000000"  # local placeholder

[vars]
ENVIRONMENT = "local"
LOG_LEVEL   = "debug"

# ── Staging ──────────────────────────────────────────────────────────────────
[env.staging]
[[env.staging.d1_databases]]
binding       = "DB"
database_name = "myapp-staging"
database_id   = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

[env.staging.vars]
ENVIRONMENT = "staging"
LOG_LEVEL   = "info"

# ── Production ───────────────────────────────────────────────────────────────
[env.production]
[[env.production.d1_databases]]
binding       = "DB"
database_name = "myapp-production"
database_id   = "11111111-2222-3333-4444-555555555555"

[env.production.vars]
ENVIRONMENT = "production"
LOG_LEVEL   = "warn"
```

## TypeScript Environment Types

```typescript
// src/types/env.ts
export interface Env {
  DB: D1Database;
  ENVIRONMENT: "local" | "staging" | "production";
  LOG_LEVEL: "debug" | "info" | "warn" | "error";
}
```

## Worker Entry Point

```typescript
// src/index.ts
import type { Env } from "./types/env";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // env.DB always points to the correct database for the deployed environment
    const { results } = await env.DB.prepare("SELECT 1 AS ok").all<{ ok: number }>();
    return Response.json({
      environment: env.ENVIRONMENT,
      db_ok: results[0]?.ok === 1,
    });
  },
} satisfies ExportedHandler<Env>;
```

## Local Development with `--local`

```bash
# Uses the top-level binding; D1 data lives in .wrangler/state/v3/d1/
wrangler dev --local

# Explicitly use local D1 (same as default for wrangler dev)
wrangler d1 execute myapp-local --local --command "SELECT name FROM sqlite_master;"
```

```typescript
// For integration tests, reference the local binding by name
// vitest.config.ts (using @cloudflare/vitest-pool-workers)
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // No --env means the top-level (local) DB binding is used in tests
      },
    },
  },
});
```

## CI/CD Deploy Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main, staging]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Run migrations — staging
        if: github.ref == 'refs/heads/staging'
        run: npx wrangler d1 migrations apply myapp-staging --env staging --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Deploy Worker — staging
        if: github.ref == 'refs/heads/staging'
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Run migrations — production
        if: github.ref == 'refs/heads/main'
        run: npx wrangler d1 migrations apply myapp-production --env production --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Deploy Worker — production
        if: github.ref == 'refs/heads/main'
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Runtime Environment Guard

```typescript
// src/middleware/env-guard.ts
import type { Env } from "../types/env";

// Prevent destructive mutations from running outside production safely
export function assertSafeEnv(env: Env, allowedEnvs: Env["ENVIRONMENT"][]): void {
  if (!allowedEnvs.includes(env.ENVIRONMENT)) {
    throw new Error(
      `Operation not allowed in environment '${env.ENVIRONMENT}'. ` +
      `Allowed: ${allowedEnvs.join(", ")}`
    );
  }
}

// Usage: only run truncation in local/staging
// assertSafeEnv(env, ["local", "staging"]);
```

## Confirming Active Binding at Runtime

```typescript
// src/diagnostics/db-info.ts
import type { Env } from "../types/env";

interface DbInfoRow {
  name: string;
}

export async function getActiveDbName(env: Env): Promise<string> {
  // sqlite_master exists on every SQLite database; use it to confirm which DB is bound
  const rows = await env.DB.prepare(
    "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name LIMIT 10"
  ).all<DbInfoRow>();
  return rows.results.map((r) => r.name).join(", ");
}
```

## wrangler.jsonc Alternative (for comments)

```jsonc
// wrangler.jsonc
{
  "name": "myapp",
  "main": "src/index.ts",
  "compatibility_date": "2024-09-23",
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "myapp-local",
      "database_id": "00000000-0000-0000-0000-000000000000"
    }
  ],
  "env": {
    "staging": {
      "d1_databases": [
        {
          "binding": "DB",
          "database_name": "myapp-staging",
          "database_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        }
      ],
      "vars": { "ENVIRONMENT": "staging" }
    },
    "production": {
      "d1_databases": [
        {
          "binding": "DB",
          "database_name": "myapp-production",
          "database_id": "11111111-2222-3333-4444-555555555555"
        }
      ],
      "vars": { "ENVIRONMENT": "production" }
    }
  }
}
```

## Anti-patterns

- **Single database ID for all environments** — using the production database ID as a fallback
  means a misconfigured staging deploy can corrupt production data.
- **Environment selection via `ENVIRONMENT` var alone** — the binding (`database_id`) controls
  which database is actually used; an `ENVIRONMENT` var mismatch just causes confusion without
  preventing wrong-database access.
- **Hardcoding database IDs in application code** — the database ID should live only in
  `wrangler.toml`; application code should use the binding name `DB` exclusively.
- **Sharing migration state across environments** — run `wrangler d1 migrations apply` per
  environment separately; a migration applied to staging should never automatically apply to
  production.
- **Using `--remote` in local tests** — always test with `--local`; `--remote` consumes remote
  D1 quota and risks data mutation on shared environments.

## Gotchas

- **Environment names are arbitrary strings** but Wrangler routes `wrangler deploy` (no `--env`)
  to the top-level config, not to any named environment; name your environments deliberately.
- **`wrangler d1 migrations apply`** requires the `--env` flag to target the correct database;
  omitting it runs against the default (top-level) binding, which may be your local stub.
- **`database_id` is not secret** — it is a public identifier on the Cloudflare platform;
  access is controlled by your API token, not by the ID. Do not treat it as a credential.
- **Local D1 state persists across `wrangler dev` restarts** in `.wrangler/state/v3/d1/`;
  delete that directory to start fresh, or use `--persist-to` to point at a clean directory.

## Verification

```bash
# Confirm staging binding resolves to the correct database
wrangler d1 execute myapp-staging --env staging --remote \
  --command "SELECT name FROM sqlite_master WHERE type='table';"

# Confirm production binding
wrangler d1 execute myapp-production --env production --remote \
  --command "SELECT COUNT(*) AS tables FROM sqlite_master WHERE type='table';"

# List all D1 databases in the account to verify names/IDs
wrangler d1 list
```

## Related

- `d1-migrations-wrangler-ci-cd.md`
- `d1-schema-versioning-wrangler-migrations.md`
- `d1-seeding-ci-cd-pipelines.md`
- `d1-connection-pooling-workers.md`
- `d1-service-binding-access-isolation-workers.md`

## Sources

- Wrangler environments docs: https://developers.cloudflare.com/workers/wrangler/environments/
- D1 Wrangler commands: https://developers.cloudflare.com/d1/reference/wrangler-commands/
- D1 binding reference: https://developers.cloudflare.com/d1/get-started/#4-bind-your-worker-to-your-d1-database
- Cloudflare Workers types: https://github.com/cloudflare/workers-types
