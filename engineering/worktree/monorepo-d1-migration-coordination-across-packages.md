# Monorepo D1 Migration Coordination Across Packages

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your monorepo has three Workers packages (`packages/api`, `packages/analytics`,
`packages/jobs`) that all bind to the same D1 database. A schema change in the `users`
table is required by `api` but breaks a query in `analytics`. Migrations are scattered
across packages, applied in an undefined order, and CI has no gate that enforces all
consumers pass before the migration lands in production.

## Context

D1 is a per-database migration log (`d1_migrations` table). When multiple packages own
migration files that target the same database, the application order matters and conflicts
are invisible until runtime. A monorepo coordination layer — a canonical `db` package
holding all migrations — makes ordering explicit, keeps consumers in sync, and gives CI
a single gate to enforce before any Worker deploys.

---

## 1. Canonical Database Package Layout

```
packages/
  db/
    migrations/
      0001_create_users.sql
      0002_add_users_avatar.sql
      0003_create_events.sql
    src/
      types.ts        # shared row types for all consumers
      schema.test.ts  # schema smoke tests via miniflare
    package.json
    wrangler.jsonc
  api/
    src/
    wrangler.jsonc    # binds DB, does NOT own migrations
  analytics/
    src/
    wrangler.jsonc    # same DB binding, no migrations
  jobs/
    src/
    wrangler.jsonc    # same DB binding, no migrations
```

All migration files live exclusively in `packages/db/migrations/`. Other packages
import column names and row types from `@repo/db/types` but never write SQL migration
files themselves.

## 2. Shared Row Types Exported from the db Package

```typescript
// packages/db/src/types.ts
export interface UserRow {
  id: string;
  email: string;
  avatar_url: string | null;
  created_at: string;
}

export interface EventRow {
  id: string;
  user_id: string;
  name: string;
  payload: string; // JSON
  ts: string;
}
```

```typescript
// packages/api/src/handlers/users.ts
import type { UserRow } from "@repo/db/types";
import type { Env } from "../env";

export async function getUser(id: string, env: Env): Promise<UserRow | null> {
  const row = await env.DB.prepare("SELECT * FROM users WHERE id = ?")
    .bind(id)
    .first<UserRow>();
  return row ?? null;
}
```

If a migration renames a column, the `types.ts` change propagates as a compile error
across all consumers before the migration is even applied.

## 3. Migration Application Script

```typescript
// packages/db/scripts/migrate.ts
import { execSync } from "node:child_process";
import { readdirSync } from "node:fs";
import path from "node:path";

const MIGRATIONS_DIR = path.join(import.meta.dirname, "../migrations");
const DB_NAME = process.env.D1_DATABASE_NAME ?? "api-db";
const ENV_FLAG = process.env.WRANGLER_ENV ? `--env ${process.env.WRANGLER_ENV}` : "";

const files = readdirSync(MIGRATIONS_DIR)
  .filter((f) => f.endsWith(".sql"))
  .sort(); // lexicographic order enforces migration sequence

for (const file of files) {
  console.log(`Applying: ${file}`);
  execSync(
    `pnpm wrangler d1 migrations apply ${DB_NAME} ${ENV_FLAG} --migrations-dir ./migrations`,
    { cwd: path.join(import.meta.dirname, ".."), stdio: "inherit" }
  );
  break; // wrangler apply is idempotent; run once for the full set
}
```

```bash
# apply to local dev DB
D1_DATABASE_NAME=api-db pnpm --filter @repo/db migrate

# apply to staging
D1_DATABASE_NAME=api-db-staging WRANGLER_ENV=staging pnpm --filter @repo/db migrate
```

## 4. Turbo Pipeline: Migrations Before Deploys

```jsonc
// turbo.json (root)
{
  "tasks": {
    "db#migrate": {
      "outputs": [],
      "env": ["D1_DATABASE_NAME", "CLOUDFLARE_API_TOKEN", "WRANGLER_ENV"]
    },
    "deploy": {
      "dependsOn": ["db#migrate", "^build"],
      "outputs": []
    }
  }
}
```

This ensures `packages/db` migrations run and succeed before any Worker's `deploy` task
starts. A migration failure blocks all deploys in the pipeline.

## 5. Cross-Package Schema Test in CI

```typescript
// packages/db/src/schema.test.ts
import { describe, it, expect, beforeAll } from "vitest";
import { unstable_dev } from "wrangler";

// Spin up a miniflare-backed worker purely to validate schema queries
describe("D1 schema contract", () => {
  let db: D1Database;

  beforeAll(async () => {
    // Use wrangler's unstable_dev to get a local D1 handle
    const worker = await unstable_dev("src/schema-worker.ts", {
      experimental: { disableExperimentalWarning: true },
      local: true,
      persist: false,
    });
    // @ts-expect-error — accessing internal binding for test purposes
    db = worker.env.DB;
  });

  it("users table has expected columns", async () => {
    const result = await db
      .prepare("PRAGMA table_info(users)")
      .all<{ name: string; type: string }>();
    const cols = result.results.map((r) => r.name);
    expect(cols).toContain("id");
    expect(cols).toContain("email");
    expect(cols).toContain("avatar_url");
  });

  it("events table references users", async () => {
    const result = await db
      .prepare("PRAGMA foreign_key_list(events)")
      .all<{ table: string }>();
    expect(result.results.some((r) => r.table === "users")).toBe(true);
  });
});
```

## 6. Migration Coordination Checklist in PR Template

```markdown
<!-- .github/PULL_REQUEST_TEMPLATE/migration.md -->
## D1 Migration Checklist

- [ ] Migration file added to `packages/db/migrations/` with next sequential prefix
- [ ] `packages/db/src/types.ts` updated to reflect column changes
- [ ] All consumer packages (`api`, `analytics`, `jobs`) compile with updated types (`tsc --noEmit`)
- [ ] `pnpm --filter @repo/db test` passes locally with updated schema
- [ ] Turbo pipeline `db#migrate` runs before any `deploy` task in CI
- [ ] Staging migration applied and smoke-tested before production deploy
```

---

## Anti-patterns

- **Placing migration files in individual Worker packages** — migration order becomes
  ambiguous; consumers can deploy against a schema that hasn't been migrated yet.
- **Sharing the D1 database binding but owning migrations in each package** — two packages
  applying migrations concurrently to the same database causes lock contention and
  duplicate migration log entries.
- **Running `wrangler d1 migrations apply` inside each Worker's deploy step** — if the
  API deploys before analytics, analytics may run against a schema it didn't anticipate.
- **Skipping TypeScript types in the db package** — SQL renames become silent runtime
  errors instead of compile-time failures across the monorepo.

## Gotchas

- `wrangler d1 migrations apply` is idempotent per migration file (it checks the
  `d1_migrations` table), but only if migration filenames are stable. Renaming an already-
  applied migration file causes it to be re-applied, corrupting data.
- Local `--local` D1 state is per-worktree when `--persist-to` is scoped. The canonical
  `packages/db` migration script must be re-run after each new worktree is provisioned.
- pnpm `--filter @repo/db` resolves the package by `name` in `package.json`, not by
  directory path. Ensure `"name": "@repo/db"` is set correctly.
- Turborepo's `db#migrate` task syntax pins migration to a specific package. If your
  Turbo version is <2.0, use `"dependsOn": ["{packages/db}#migrate"]` syntax instead.

## Verification

```bash
# Confirm migration log after apply
pnpm wrangler d1 execute api-db --command \
  "SELECT name, applied_at FROM d1_migrations ORDER BY id" --local

# Confirm types compile across all consumers
pnpm --filter "...[HEAD]" exec tsc --noEmit

# Confirm schema tests pass
pnpm --filter @repo/db test
```

## Related

- `workers-d1-migration-ci-pipeline.md`
- `git-worktree-parallel-d1-schema-migration.md`
- `monorepo-deploy-order-workers-service-bindings.md`
- `monorepo-affected-builds-2026.md`
- `turborepo-pipeline-prune-selective-build-workers.md`

## Sources

- Cloudflare D1 migrations docs — developers.cloudflare.com/d1/reference/migrations
- Turborepo task dependency docs — turbo.build/repo/docs/reference/configuration#dependson
- pnpm filter syntax — pnpm.io/filtering
