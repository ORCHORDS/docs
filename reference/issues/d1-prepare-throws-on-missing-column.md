# D1 `prepare()` Throws `"no such column"` After Schema Migration Without Worker Redeploy

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 migration adds a new column to an existing table. Immediately after running the migration, API endpoints backed by that table start throwing `Error: no such column: <column_name>`, even though `SELECT * FROM pragma_table_info('<table>')` confirms the column exists in the database. Redeploying the Worker resolves the issue, but the cause is unclear.

---

## Context

Cloudflare D1 uses SQLite under the hood. The Workers runtime prepares SQL statements using `DB.prepare()`, which compiles the SQL into an internal byte-code representation. When a `prepare()` call is placed at module scope (outside any request handler), it is executed once when the Worker isolate is first instantiated and the result is cached for the lifetime of the isolate. If a D1 schema migration adds a new column *after* an existing isolate has already compiled a `SELECT` or `INSERT` statement that references that column, the cached compiled statement still contains the old schema snapshot and throws `no such column` for the new field. The isolate is only recycled on Worker redeploy or when Cloudflare's scheduler evicts it.

---

## What Went Wrong

```typescript
// src/db.ts — module-scope prepared statement (anti-pattern)
import type { D1Database } from '@cloudflare/workers-types';

let db: D1Database;

// ❌ Prepared at module initialisation time — schema snapshot is frozen
const GET_USER = db!.prepare(
  'SELECT id, email, created_at, subscription_tier FROM users WHERE id = ?'
);
// After running: ALTER TABLE users ADD COLUMN display_name TEXT;
// the column exists in D1 but GET_USER still throws "no such column: subscription_tier"
// if subscription_tier was added in a previous migration that the isolate missed.
```

```typescript
// src/handlers/users.ts
import { GET_USER } from '../db';

export async function getUser(id: string) {
  // Throws: D1_ERROR: no such column: subscription_tier
  return GET_USER.bind(id).first();
}
```

## Root Cause

D1's `prepare()` compiles the SQL statement at call time, not at query execution time. A module-scope `prepare()` runs when the isolate boots — before any request is processed. The compiled statement encodes column references against the schema as it existed at boot time.

After a `wrangler d1 migrations apply` run, the D1 database schema changes, but already-running isolates are not notified. They continue serving requests with stale compiled statements until the isolate is evicted. A Worker redeploy forces all isolates to restart, re-running module-scope code against the updated schema.

The same issue affects module-scope `prepare()` calls that reference columns added in *future* migrations — the statement compiles fine today but will fail after any migration that removes or renames a column it references.

## The Fix

### Option 1 — Lazy `prepare()` inside handler (recommended)

```typescript
// src/handlers/users.ts — fixed: prepare inside handler
import type { D1Database } from '@cloudflare/workers-types';

export async function getUser(env: { DB: D1Database }, id: string) {
  // prepare() runs per-request; always sees current schema
  const stmt = env.DB.prepare(
    'SELECT id, email, created_at, subscription_tier, display_name FROM users WHERE id = ?'
  );
  return stmt.bind(id).first();
}
```

The per-request overhead of `prepare()` in D1 is minimal — the underlying SQLite compilation is fast and D1's HTTP layer does not provide meaningful caching of compiled statements across requests anyway.

### Option 2 — Redeploy Worker immediately after every migration

```bash
# Apply migration
wrangler d1 migrations apply my-database --remote

# Immediately redeploy the Worker to recycle isolates
wrangler deploy

# Verify new column is accessible
curl https://my-worker.example.workers.dev/users/123
```

This is a process fix, not a code fix. It is fragile because a deployment window exists between the migration and the redeploy during which live requests hit stale isolates.

### Option 3 — Inject DB through handler env, never at module scope

```typescript
// src/index.ts — canonical pattern
import type { Env } from './env';
import { getUser } from './handlers/users';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const id = url.searchParams.get('id') ?? '';

    const user = await getUser(env, id);
    if (!user) return new Response('Not found', { status: 404 });

    return Response.json(user);
  },
};
```

```typescript
// src/env.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
}
```

## Verification

```bash
# 1. Apply migration
wrangler d1 migrations apply my-database --remote

# 2. Confirm new column exists in D1
wrangler d1 execute my-database --remote \
  --command "SELECT name FROM pragma_table_info('users');"

# 3. Without redeploy, hit the endpoint — should now succeed with lazy prepare()
curl -s https://my-worker.example.workers.dev/users/1 | jq '.display_name'

# 4. Confirm no stale-column errors in Workers tail
wrangler tail my-worker --format pretty 2>&1 | grep -i 'no such column'
# Expected: no output

# 5. Run integration tests
npx vitest run src/handlers/users.test.ts
```

---

## Anti-patterns

- **Module-scope `DB.prepare()` for statements with column references** — Freezes the schema at isolate boot time; any subsequent migration that touches referenced columns causes `no such column` errors until the next redeploy.
- **Running migrations without an immediate Worker redeploy in a deployment pipeline** — Creates a time window where live traffic hits isolates with a stale compiled schema. Automate `wrangler deploy` as the next step after `wrangler d1 migrations apply`.
- **Storing the `D1Database` binding in a module-level variable** — Accessing `env.DB` only inside the `fetch`/`scheduled` handler ensures the binding is always fresh and avoids class of initialization-order bugs.

---

## Gotchas

- The issue is specific to `prepare()` — `env.DB.exec()` re-parses SQL on every call and is immune to this problem, though it is less efficient for parameterised queries.
- Wrangler's local dev mode (`wrangler dev`) uses a local SQLite file. Schema changes via `wrangler d1 migrations apply --local` *do* take effect immediately because the local dev server reloads on file change. The stale-prepare bug only manifests on remote (`--remote`) deployments.
- D1 is eventually consistent across PoPs. After a migration, different Points of Presence may be on different schema versions for a brief window; a redeploy does not instantly recycle all isolates globally.
- `pragma_table_info` is a D1-supported pragma and is the correct way to inspect schema from inside a Worker: `env.DB.prepare("SELECT * FROM pragma_table_info('users')").all()`.

---

## Related

- `workers-instanceof-error-cross-realm.md`
- `workers-scheduled-handler-not-firing-local.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- D1 Migrations guide — https://developers.cloudflare.com/d1/reference/migrations/
- SQLite PREPARE statement behaviour — https://www.sqlite.org/c3ref/prepare.html
