# Local Dev for Pages Functions with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

When developing Cloudflare Pages Functions that query D1 databases, `wrangler pages dev` must be told which local D1 binding to use, otherwise function calls to `env.DB` throw `TypeError: env.DB is undefined`. This article covers the full local-dev loop: binding setup, seed data, hot-reload, and inspector-based debugging.

## Context

- Cloudflare Pages (Functions in `functions/` directory)
- D1 database already created (`wrangler d1 create my-db`)
- Node 20, Wrangler 3.x
- TypeScript functions

---

## Step 1 — wrangler.toml for Pages

Pages projects support `wrangler.toml` from Wrangler 3.9+. Place it at the repo root:

```toml
# wrangler.toml
name = "my-pages-app"
pages_build_output_dir = "./dist"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # from `wrangler d1 list`
```

The `database_id` is only used for remote operations. Local dev creates a SQLite file under `.wrangler/state/v3/d1/`.

---

## Step 2 — Start Local Dev Server

```bash
# Bind D1 to the local miniflare SQLite instance
wrangler pages dev dist --d1 DB=my-db

# With a custom port and live-reload for the Pages build output
wrangler pages dev dist \
  --d1 DB=my-db \
  --port 8788 \
  --live-reload

# If using a framework (Vite, Astro, etc.) point to the dev server instead
wrangler pages dev http://localhost:5173 \
  --d1 DB=my-db \
  --port 8788
```

Wrangler proxies requests to the asset server and intercepts `/api/*` (or any route matched by `functions/`) through the Workers runtime.

---

## Step 3 — Pages Function Typing

```typescript
// functions/api/users.ts

export interface Env {
  DB: D1Database;
}

export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const { results } = await ctx.env.DB.prepare(
    "SELECT id, name, email FROM users ORDER BY created_at DESC LIMIT 50"
  ).all();

  return Response.json(results);
};

export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  const body = await ctx.request.json<{ name: string; email: string }>();

  const stmt = ctx.env.DB.prepare(
    "INSERT INTO users (name, email) VALUES (?1, ?2) RETURNING id"
  );

  const row = await stmt.bind(body.name, body.email).first<{ id: number }>();

  if (!row) {
    return new Response("Insert failed", { status: 500 });
  }

  return Response.json({ id: row.id }, { status: 201 });
};
```

---

## Step 4 — Seed Script

Create a SQL seed file and apply it to the local D1 instance before starting dev:

```sql
-- db/seed.sql
CREATE TABLE IF NOT EXISTS users (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name      TEXT    NOT NULL,
  email     TEXT    NOT NULL UNIQUE,
  created_at TEXT   DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO users (name, email) VALUES
  ('Alice Nguyen',  'alice@example.com'),
  ('Bob Okonkwo',  'bob@example.com'),
  ('Carol Reyes',  'carol@example.com');
```

```bash
# Apply seed to the local D1 database (not remote)
wrangler d1 execute my-db --local --file db/seed.sql

# Verify
wrangler d1 execute my-db --local --command "SELECT * FROM users"
```

Wrap the seed step in a package.json script:

```json
{
  "scripts": {
    "db:seed": "wrangler d1 execute my-db --local --file db/seed.sql",
    "dev": "npm run db:seed && wrangler pages dev dist --d1 DB=my-db --port 8788"
  }
}
```

---

## Step 5 — Migration Workflow

```bash
# Create a new migration file
mkdir -p db/migrations
cat > db/migrations/0001_create_users.sql << 'EOF'
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  email      TEXT    NOT NULL UNIQUE,
  created_at TEXT    DEFAULT (datetime('now'))
);
EOF

# Apply migration locally
wrangler d1 migrations apply my-db --local

# Apply migration to remote (production)
wrangler d1 migrations apply my-db --remote
```

Track migrations in `wrangler.toml`:

```toml
[[d1_databases]]
binding          = "DB"
database_name    = "my-db"
database_id      = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir   = "db/migrations"
```

---

## Step 6 — Hot-reload Behaviour

Wrangler 3.x watches the `functions/` directory and reloads the runtime on file changes without restarting the D1 local state. The SQLite file persists between reloads at:

```
.wrangler/state/v3/d1/miniflare-D1DatabaseObject/<hash>/db.sqlite
```

To reset local state completely:

```bash
rm -rf .wrangler/state
npm run db:seed
```

---

## Step 7 — Debugging With --inspector-port

```bash
# Open the V8 inspector on port 9229
wrangler pages dev dist \
  --d1 DB=my-db \
  --inspector-port 9229
```

In Chrome, open `chrome://inspect` and click **Open dedicated DevTools for Node**. Set breakpoints directly in the TypeScript source (source maps are handled by Wrangler locally).

Alternatively, attach VS Code:

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "node",
      "request": "attach",
      "name": "Attach to Wrangler Pages Dev",
      "port": 9229,
      "sourceMaps": true,
      "resolveSourceMapLocations": ["${workspaceFolder}/**"]
    }
  ]
}
```

Trigger a request to the function, then step through with the VS Code debugger while inspecting `ctx.env.DB` bindings live.

---

## Step 8 — Inspecting Local D1 With Drizzle Studio (Optional)

```typescript
// drizzle.config.ts  — points at the local miniflare SQLite
import type { Config } from "drizzle-kit";

export default {
  schema: "./src/db/schema.ts",
  out: "./db/migrations",
  dialect: "sqlite",
  dbCredentials: {
    url: ".wrangler/state/v3/d1/miniflare-D1DatabaseObject/<hash>/db.sqlite",
  },
} satisfies Config;
```

```bash
npx drizzle-kit studio
# Opens browser at http://localhost:4983
```

---

## Anti-patterns

- Passing `--remote` to `wrangler pages dev` — Pages dev always runs locally; `--remote` applies only to `wrangler dev` for plain Workers.
- Hardcoding `database_id` in function code instead of using `env.DB` — the binding is the portable abstraction.
- Using `--persist-to` with an absolute path inside the Docker container but a relative path in package.json scripts — always use relative paths anchored to the project root.
- Seeding directly into the production D1 by accidentally omitting `--local`.
- Running migrations with `--remote` before testing with `--local` — always validate locally first.

## Gotchas

- D1 local uses SQLite, which lacks some Postgres-style SQL features; test edge cases (e.g., `RETURNING`) explicitly.
- The local D1 SQLite path changes if the database binding name changes — rename the binding and delete `.wrangler/state` to avoid stale data.
- `wrangler pages dev` does not support `--env staging` — environment-specific bindings must be configured separately.
- `ctx.waitUntil()` is a no-op in local dev; background tasks terminate immediately after the response.

---

## Verification

```bash
# Confirm D1 binding is reachable from the function
curl http://localhost:8788/api/users | jq '. | length'

# Insert a test row
curl -X POST http://localhost:8788/api/users \
  -H 'Content-Type: application/json' \
  -d '{"name": "Test User", "email": "test@example.com"}'

# Confirm row is in local SQLite
wrangler d1 execute my-db --local \
  --command "SELECT * FROM users WHERE email='test@example.com'"
```

---

## Related

- `documentation/docs/policies/devtools/workers-d1-studio-query-inspect.md`
- `documentation/docs/policies/devtools/workers-source-map-upload-wrangler-debug.md`

## Sources

- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/pages/functions/bindings/#d1-databases
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#pages-dev
- https://developers.cloudflare.com/d1/best-practices/local-development/
