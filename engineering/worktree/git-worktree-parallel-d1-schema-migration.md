# git worktree Parallel D1 Schema Migration Development

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your team is building a new Cloudflare Workers feature that requires a D1 schema change. While you are mid-migration-authoring your main checkout is blocked: you cannot run the existing test suite against the stable schema, review a colleague's PR, or reproduce a production bug without first undoing your in-progress migration file. You want to author and test a D1 migration in one isolated environment while keeping your stable checkout fully usable for everything else.

## Context

Cloudflare D1 migrations are SQL files stored in a `migrations/` directory and applied in order by `wrangler d1 migrations apply`. Each migration has a version number (e.g. `0004_add_user_roles.sql`) and is tracked in the D1 `d1_migrations` table. Developing a migration involves iterative write-apply-test cycles that pollute local state.

`git worktree` creates a second working tree from the same repository with its own checkout and its own file-system path. Combined with Wrangler's `--local` flag (which stores D1 state in `.wrangler/state/`) you can run completely isolated D1 environments per worktree. Each worktree has its own `.wrangler/` directory because Wrangler resolves state paths relative to the `wrangler.toml` location.

---

## Setting Up the Migration Worktree

```bash
# From the repository root
git worktree add ../my-repo-migration feature/add-user-roles

cd ../my-repo-migration
```

Install dependencies (node_modules are not shared):

```bash
pnpm install
```

Verify worktrees:

```bash
git worktree list
# /path/to/project            abc1234 [main]
# /path/to/project  def5678 [feature/add-user-roles]
```

---

## Creating the D1 Migration File

```bash
# Inside the migration worktree
npx wrangler d1 migrations create my-db add-user-roles
# Created migration: migrations/0004_add_user_roles.sql
```

Author the migration:

```sql
-- migrations/0004_add_user_roles.sql
CREATE TABLE user_roles (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'viewer')),
  granted_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  granted_by  TEXT REFERENCES users(id)
);

CREATE INDEX idx_user_roles_user_id ON user_roles(user_id);
```

Apply to the local D1 instance in the migration worktree only:

```bash
npx wrangler d1 migrations apply my-db --local
# Applied migration 0004_add_user_roles.sql
```

The stable worktree at `/path/to/project still has its `.wrangler/state/` pointing at schema version 0003. The two environments do not interfere.

---

## Writing the Worker Code Against the New Schema

```typescript
// src/handlers/roles.ts  (authored in the migration worktree)
export interface Env {
  DB: D1Database;
}

export async function getUserRoles(
  userId: string,
  env: Env
): Promise<{ role: string; grantedAt: number }[]> {
  const { results } = await env.DB.prepare(
    "SELECT role, granted_at FROM user_roles WHERE user_id = ? ORDER BY granted_at DESC"
  )
    .bind(userId)
    .all<{ role: string; granted_at: number }>();

  return results.map((r) => ({ role: r.role, grantedAt: r.granted_at }));
}

export async function grantRole(
  userId: string,
  role: "admin" | "editor" | "viewer",
  grantedBy: string,
  env: Env
): Promise<void> {
  await env.DB.prepare(
    "INSERT INTO user_roles (user_id, role, granted_by) VALUES (?, ?, ?)"
  )
    .bind(userId, role, grantedBy)
    .run();
}
```

Run the dev server in the migration worktree with the migrated local DB:

```bash
npx wrangler dev --local --persist-to .wrangler/state
```

---

## Running Tests in Both Worktrees Simultaneously

Use different ports to run both dev servers at the same time:

```bash
# Terminal A — stable main worktree
cd /path/to/project
npx wrangler dev --local --port 8787

# Terminal B — migration worktree
cd /path/to/project
npx wrangler dev --local --port 8788
```

Vitest configuration in the migration worktree points at the local Worker:

```typescript
// vitest.config.ts (migration worktree)
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "miniflare",
    environmentOptions: {
      d1Databases: ["DB"],
      d1Persist: ".wrangler/state/v3/d1",
    },
  },
});
```

```typescript
// src/handlers/roles.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { getUserRoles, grantRole } from "./roles";

describe("user roles", () => {
  it("grants and retrieves roles", async () => {
    await grantRole("user-1", "editor", "admin-1", env);
    const roles = await getUserRoles("user-1", env);
    expect(roles).toHaveLength(1);
    expect(roles[0].role).toBe("editor");
  });
});
```

---

## Merging and Applying to Remote D1

Once the PR is approved and merged, apply the migration to staging:

```bash
# Back on main after merge
npx wrangler d1 migrations apply my-db --env staging
# ✔ Applied 1 migration(s) to staging
```

Then to production:

```bash
npx wrangler d1 migrations apply my-db --env production
```

In CI, gate the apply behind a manual approval step:

```yaml
# .github/workflows/d1-migrate.yml
jobs:
  migrate-production:
    environment: production          # requires manual approval in GitHub
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx wrangler d1 migrations apply my-db --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Anti-patterns

- **Sharing `.wrangler/state/` between worktrees**: Symlinking or copying state between worktrees defeats the isolation. Each worktree must maintain its own local D1 state to avoid schema version conflicts.
- **Running `migrations apply --remote` during development iteration**: Remote D1 has real data. Use `--local` for all iterative development; apply remotely only after the migration is fully tested and reviewed.
- **Using `--local` without `--persist-to`**: Without explicit persistence, Wrangler may store state in a temporary path that is wiped on restart, losing your applied migration state between dev server restarts.
- **Numbering migrations manually out of sequence**: If the main branch gains migration `0004` while your branch has its own `0004`, you will have a collision. Use `wrangler d1 migrations create` (which auto-sequences) rather than manually naming files.

---

## Gotchas

- `node_modules` are not shared between worktrees. Each worktree needs its own `pnpm install`. Consider `pnpm`'s content-addressable store (`~/.pnpm-store`) to avoid re-downloading packages.
- `wrangler.toml` is read from the worktree's directory. If it contains `migrations_dir = "migrations"` the path is resolved relative to `wrangler.toml`, so each worktree correctly reads its own migrations directory.
- The `d1_migrations` table is created in the D1 database itself. In local mode each worktree has its own SQLite file under `.wrangler/state/v3/d1/`, so they track applied migrations independently.
- `git worktree add` fails if the branch name already has a worktree checked out elsewhere. Use `git worktree list` to audit before adding.
- D1 local state is stored in `.wrangler/` which is typically `.gitignore`d. Confirm this before committing.

---

## Verification

```bash
# List worktrees
git worktree list

# Confirm isolated D1 states
ls /path/to/project
ls /path/to/project
# Should show different SQLite files with different sizes if schemas differ

# Check applied migrations in migration worktree
npx wrangler d1 execute my-db --local \
  --command "SELECT * FROM d1_migrations ORDER BY id;"

# Run tests in migration worktree
cd /path/to/project
pnpm test
```

---

## Related

- `workers-d1-migration-ci-pipeline.md`
- `git-worktree-parallel-hotfix-development.md`
- `git-worktree-lockfile-isolation.md`
- `cloudflare-workers-vitest-miniflare-testing.md`
- `wrangler-environments-staging-production.md`

---

## Sources

- developers.cloudflare.com/d1/reference/migrations/
- developers.cloudflare.com/workers/wrangler/commands/#d1
- git-scm.com/docs/git-worktree
- developers.cloudflare.com/workers/testing/vitest-integration/
