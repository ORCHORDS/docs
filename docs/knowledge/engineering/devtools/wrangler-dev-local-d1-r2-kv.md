# wrangler-dev-local-d1-r2-kv

**Issue:** Running `wrangler dev` without explicit local-persistence flags
means every restart drops the D1 database state, the KV store is empty,
R2 objects vanish, and `.dev.vars` secrets are silently ignored — making
iterative development feel like starting from scratch on every hot-reload.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
wrangler dev
  ✓  Starting local server…
  ✓  D1 database "db" created (in-memory)
  ✗  KV namespace "CACHE" not persisted — data lost between restarts
  ✗  R2 bucket "assets" returns 404 for objects written last session
```

Seed scripts run on every dev start because the database is ephemeral.
`.dev.vars` values appear `undefined` inside the Worker because the file
was placed in the wrong directory or named incorrectly. Mobile device
testing on the local server fails because `wrangler dev` binds to
`127.0.0.1` instead of the machine's LAN IP.

## Context

Wrangler 3 runs a full local Cloudflare runtime via Miniflare v3 under
the hood. All bindings — D1, KV, R2, Queues, Durable Objects — have
local implementations backed by SQLite or the local filesystem, but
persistence must be opted into explicitly with `--persist-to` or the
equivalent `wrangler.toml` stanza. The `.dev.vars` file is the local
analogue of Cloudflare Workers Secrets: it is loaded only when present
in the project root (same directory as `wrangler.toml`).

## Persisting D1 locally

Wrangler stores the local D1 database as a SQLite file under
`.wrangler/state/v3/d1/`. The path is stable across restarts when
`--local` and `--persist-to` are set.

```toml
# wrangler.toml
[[d1_databases]]
binding     = "DB"
database_name = "example project-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

```bash
# Dev start — SQLite file survives restarts
wrangler dev --local --persist-to .wrangler/state
```

Or lock the default persist path permanently in `wrangler.toml`:

```toml
[dev]
persist_to = ".wrangler/state"   # Wrangler ≥ 3.22
```

Apply migrations on the local database:

```bash
# Run all pending migrations against the local SQLite DB
wrangler d1 migrations apply example project-db --local

# Run a seed script
wrangler d1 execute example project-db --local --file ./db/seed.sql
```

Add the local SQLite file to `.gitignore`:

```
.wrangler/state/
```

## Persisting KV locally

Local KV is stored as SQLite rows under `.wrangler/state/v3/kv/`.
With `--persist-to` it survives restarts and shares data across Workers
in the same project.

```toml
[[kv_namespaces]]
binding = "CACHE"
id      = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

```bash
# Inspect local KV contents from the CLI
wrangler kv key list --binding CACHE --local
wrangler kv key get "my-key" --binding CACHE --local
wrangler kv key put "my-key" "hello" --binding CACHE --local
```

For example project's session cache pattern, pre-populate the KV store after
`wrangler dev` starts in a second terminal:

```bash
node scripts/seed-kv.mjs   # uses @cloudflare/workers-types + REST API
```

## Mocking R2 locally

Local R2 uses the filesystem under `.wrangler/state/v3/r2/`. Objects
written during one dev session are available in the next.

```toml
[[r2_buckets]]
binding    = "ASSETS"
bucket_name = "example project-assets"
```

```bash
# Upload a local file into the local R2 bucket
wrangler r2 object put example project-assets/logo.png \
  --file ./public/logo.png \
  --local

# List objects in the local bucket
wrangler r2 object list example project-assets --local
```

For large fixture sets, a one-time seed helper works better than manual
CLI calls:

```ts
// scripts/seed-r2.ts
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

// Uses the Wrangler Unstable API (wrangler >=3.35)
const { unstable_dev } = await import("wrangler");
const worker = await unstable_dev("src/index.ts", { local: true });
// OR seed via R2 REST API with CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN
```

## .dev.vars secrets

`.dev.vars` is a dotenv-format file loaded by `wrangler dev` as
Workers Secrets. It must live at the root of the Worker package — the
directory that contains `wrangler.toml`.

```bash
# apps/worker/.dev.vars
DATABASE_URL="postgresql://localhost:5432/example project_dev"
STRIPE_SECRET_KEY="sk_test_xxxxxxxxxxxxxxxxxxxx"
JWT_SECRET="dev-only-not-a-real-secret"
OPENAI_API_KEY="<redacted-secret>"
```

Verify values are injected:

```ts
// src/index.ts
export default {
  fetch(request: Request, env: Env) {
    // env.JWT_SECRET should equal the value in .dev.vars
    console.log("jwt_secret present:", !!env.JWT_SECRET);
    return new Response("ok");
  },
};
```

Never commit `.dev.vars` — add it to `.gitignore`:

```
*.dev.vars
.dev.vars
```

For the pnpm monorepo, each Worker package has its own `.dev.vars`.
Shared secrets can be symlinked: `ln -s ../../.dev.vars.shared apps/worker/.dev.vars`.

## Mobile simulator integration

By default `wrangler dev` binds to `127.0.0.1:8787` — inaccessible from
a phone or iOS Simulator on the local network. Two approaches:

**LAN binding (physical device):**

```bash
wrangler dev --ip 0.0.0.0 --port 8787
# Worker is now reachable at http://192.168.x.x:8787
```

Then point the mobile app or simulator at the LAN IP. For Next.js dev
running on port 3000, run both simultaneously:

```json
// package.json (root)
{
  "scripts": {
    "dev": "concurrently \"pnpm --filter @example project/worker dev\" \"pnpm --filter @example project/web dev\""
  }
}
```

**Cloudflare Tunnel (any device, no LAN required):**

```bash
cloudflared tunnel --url http://localhost:8787
# Prints a public https://xxxxx.trycloudflare.com URL
```

Set the tunnel URL as the API base in the mobile app's `.env.local`:

```
NEXT_PUBLIC_API_URL=https://xxxxx.trycloudflare.com
EXPO_PUBLIC_API_URL=https://xxxxx.trycloudflare.com
```

## Wrangler dev flags reference

| Flag | Purpose |
|---|---|
| `--local` | Force local Miniflare runtime (default in Wrangler 3) |
| `--persist-to <path>` | Directory for SQLite / file state |
| `--ip 0.0.0.0` | Bind to all interfaces for mobile access |
| `--port <n>` | Override default port 8787 |
| `--env <name>` | Load a named `[env.name]` block from wrangler.toml |
| `--live-reload` | Reload browser/mobile on Worker change |
| `--inspector-port <n>` | Chrome DevTools protocol port for breakpoints |

## Anti-patterns

- **No `persist-to`** — database and KV state is lost on every `Ctrl+C`,
  forcing seed re-runs and making bug reproduction harder.
- **Committing `.dev.vars`** — exposes local API keys; use `.gitignore`
  and document required keys in `.dev.vars.example`.
- **Using production D1 `database_id` in dev** — `wrangler dev --remote`
  runs against the real production database; always use `--local` for
  iterative development.
- **Hardcoding `127.0.0.1` in the mobile app** — breaks on all physical
  devices; use an env var that switches between localhost and LAN IP.
- **Running `wrangler d1 migrations apply` without `--local`** — runs
  the migration against the production D1 database.

## Gotchas

- `.wrangler/state/v3/` schema changes between Wrangler minor versions;
  if local queries fail after upgrading, delete the state directory and
  re-seed.
- `wrangler dev --remote` uses real Cloudflare compute; latency is higher
  and every request counts against the account's Workers usage.
- KV `list()` in the local runtime does not paginate identically to
  production — test pagination logic with a remote preview environment.
- `.dev.vars` values are strings; if the production secret is a JSON blob,
  parse it explicitly: `JSON.parse(env.CONFIG)`.
- Miniflare's local R2 does not enforce the 5 TB per-object limit or
  multipart upload rules — test large-object paths in a staging R2 bucket.

## Verification

```bash
# Confirm D1 persists across restarts
wrangler d1 execute example project-db --local --command "INSERT INTO users(id) VALUES (1)"
# Stop wrangler dev, restart, then:
wrangler d1 execute example project-db --local --command "SELECT * FROM users"
# Expect: row with id=1

# Confirm .dev.vars is loaded
curl http://localhost:8787/debug/env
# Worker endpoint that returns JSON of env keys (dev only)

# Confirm R2 object persists
wrangler r2 object get example project-assets/logo.png --local --pipe > /tmp/logo.png
file /tmp/logo.png   # should report PNG image
```

## Related

- `documentation/docs/policies/devtools/wrangler-dev-local-d1-r2-testing.md`
- `documentation/docs/policies/devtools/wrangler-dev-local-mocking.md`
- `documentation/docs/policies/devtools/local-https-dev-proxy-wrangler.md`
- `documentation/docs/policies/devtools/vitest-workers-miniflare-testing-setup.md`
- `documentation/docs/policies/devtools/typescript-cloudflare-workers-strict.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/d1/best-practices/local-development/
- https://developers.cloudflare.com/kv/reference/local-development/
- https://developers.cloudflare.com/r2/api/s3/api/#local-development
- https://developers.cloudflare.com/workers/configuration/secrets/#local-development-with-devvars
- https://miniflare.dev/
