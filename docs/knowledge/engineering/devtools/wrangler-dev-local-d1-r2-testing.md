# Wrangler Dev Local D1 SQLite + R2 Filesystem Bindings Testing

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Local development against a live Cloudflare D1 database or real R2 bucket is slow,
costs real money per query, and makes tests non-deterministic. Developers need a fully
offline-capable dev loop where the Next.js frontend and the Cloudflare Worker backend
run side-by-side without hitting production infrastructure.

## Context

example project (example.com) is a Next.js + Cloudflare Workers monorepo managed with pnpm
workspaces. The Workers package exposes a D1 database binding (`DB`) and an R2 bucket
binding (`ASSETS`). During local development both bindings must resolve to offline
simulators so the full request path can be exercised without network access or cloud
billing.

`wrangler dev --local` (Wrangler 3+) uses Miniflare 3 under the hood. D1 is emulated
with a SQLite file on disk; R2 is emulated with a directory on disk. The Next.js dev
server runs separately on its own port; the Worker dev server runs on a different port
and is proxied by Next.js rewrites or a local reverse proxy.

Key versions as of this writing:

| Tool        | Minimum version |
|-------------|-----------------|
| wrangler    | 3.78.0          |
| miniflare   | 3.20240 (bundled) |
| @cloudflare/workers-types | 4.x |
| Node.js     | 20 LTS          |
| pnpm        | 9.x             |

## Local D1 SQLite Binding

Wrangler stores the local D1 database in `.wrangler/state/v3/d1/` by default.

### wrangler.toml configuration

```toml
name = "example project-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding = "DB"
database_name = "example project-dev"
database_id = "00000000-0000-0000-0000-000000000000"   # placeholder for local
```

For local-only work the `database_id` value is ignored when `--local` is active.
Use a placeholder UUID so wrangler does not complain about a missing field.

### Running with local D1

```bash
# From the workers package directory
pnpm wrangler dev --local --persist-to .wrangler/state

# Or from the monorepo root using the workspace script
pnpm --filter @example project/worker dev:local
```

`--persist-to` keeps the SQLite file across restarts. Without it, state is wiped on
each start.

### Seeding local D1

Wrangler exposes a local D1 query command when the dev server is running:

```bash
# Apply migrations
pnpm wrangler d1 migrations apply example project-dev --local

# One-off seed query
pnpm wrangler d1 execute example project-dev --local \
  --command "INSERT INTO users (id, email) VALUES ('u1', 'dev@example.com')"

# From a SQL file
pnpm wrangler d1 execute example project-dev --local --file ./seed.sql
```

The SQLite file lives at `.wrangler/state/v3/d1/example project-dev/db.sqlite`. It can be
opened with any SQLite browser (TablePlus, DB Browser) for inspection.

### D1 binding inside the Worker

```typescript
// workers/src/index.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { results } = await env.DB.prepare(
      "SELECT * FROM users LIMIT 10"
    ).all();
    return Response.json(results);
  },
};
```

No code change is needed between local and production; the binding name resolves
differently based on the runtime context.

## Local R2 Filesystem Binding

R2 is emulated with a directory. The bucket directory is created automatically under
`.wrangler/state/v3/r2/`.

### wrangler.toml configuration

```toml
[[r2_buckets]]
binding = "ASSETS"
bucket_name = "example project-assets-dev"
```

### Seeding local R2

```bash
# Upload a file to the local bucket via wrangler
pnpm wrangler r2 object put example project-assets-dev/logo.png \
  --file ./public/logo.png --local

# List objects in local bucket
pnpm wrangler r2 object list example project-assets-dev --local
```

Files are stored at `.wrangler/state/v3/r2/example project-assets-dev/`. Each object becomes a
file on disk; metadata is stored alongside in a sidecar `.metadata` directory.

### R2 binding inside the Worker

```typescript
export interface Env {
  ASSETS: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading /
    const obj = await env.ASSETS.get(key);
    if (!obj) return new Response("Not Found", { status: 404 });
    return new Response(obj.body, {
      headers: { "content-type": obj.httpMetadata?.contentType ?? "application/octet-stream" },
    });
  },
};
```

## Port Sharing with Next.js Dev Server

Next.js dev server defaults to port 3000. The Worker dev server defaults to port 8787.
Use Next.js rewrites to proxy Worker requests through the same origin to avoid CORS
issues during development.

### next.config.ts rewrite rule

```typescript
// apps/web/next.config.ts
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/worker/:path*",
        destination: "http://localhost:8787/:path*",
      },
    ];
  },
};

export default nextConfig;
```

The frontend calls `/api/worker/users` and Next.js forwards it to the Worker on 8787.
No CORS headers needed in the Worker for same-origin rewritten requests.

### pnpm dev script (monorepo root)

```json
{
  "scripts": {
    "dev": "pnpm run --parallel --filter @example project/web dev --filter @example project/worker dev:local"
  }
}
```

Or with `concurrently`:

```bash
npx concurrently \
  "pnpm --filter @example project/web dev" \
  "pnpm --filter @example project/worker wrangler dev --local --persist-to .wrangler/state"
```

### Port conflict ASCII table

| Service           | Default port | Env override          |
|-------------------|--------------|-----------------------|
| Next.js           | 3000         | `PORT=3001`           |
| Wrangler Worker   | 8787         | `--port 8788`         |
| Wrangler Inspector| 9229         | `--inspector-port 9230` |
| Miniflare livereload | 9400      | internal, not exposed |

## .dev.vars Secrets

`.dev.vars` is the Wrangler equivalent of `.env.local`. It injects secret values into
the Worker runtime during local development without touching `wrangler.toml`.

### .dev.vars format

```
JWT_SECRET=supersecret-dev-only
STRIPE_SECRET_KEY=sk_test_...
RESEND_API_KEY=re_test_...
DATABASE_URL=sqlite:///.wrangler/state/v3/d1/example project-dev/db.sqlite
```

`.dev.vars` is loaded automatically by `wrangler dev --local`. No flag needed.

### .gitignore entry

```
# workers/.gitignore
.dev.vars
.wrangler/state/
```

Never commit `.dev.vars`. Use a `.dev.vars.example` with placeholder values instead.

### Accessing secrets in the Worker

```typescript
export interface Env {
  JWT_SECRET: string;
  STRIPE_SECRET_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.JWT_SECRET is populated from .dev.vars in local mode
    // and from Cloudflare secrets in production
    const token = request.headers.get("Authorization");
    // ... validate with env.JWT_SECRET
  },
};
```

## Anti-patterns

- **Hardcoding `--local` in CI pipelines**: CI should run against a staging D1 database
  with actual `wrangler d1 migrations apply` commands against a real database ID, not
  the local SQLite simulator.
- **Sharing `.wrangler/state/` between team members via git**: the SQLite file contains
  binary data and will cause merge conflicts. Each developer keeps their own local state.
- **Using real `database_id` in `wrangler.toml` and forgetting `--local`**: without
  `--local`, Wrangler will execute queries against the actual Cloudflare D1 database
  even during local dev. Always double-check the running flag.
- **Omitting `--persist-to`**: losing the local database on every restart defeats the
  purpose of local seeding. Always pin the persist path.
- **Proxying both dev servers with `ngrok`**: this exposes your local D1 state to the
  internet. Use `--local` only for local network testing.

## Gotchas

- **D1 SQLite dialect vs. production**: Miniflare's SQLite dialect may accept statements
  that Cloudflare's D1 production rejects (e.g., certain `PRAGMA` statements). Always
  run integration tests against a real Cloudflare D1 environment before release.
- **R2 presigned URLs not supported locally**: `env.ASSETS.createMultipartUpload()` and
  presigned URL generation work differently in Miniflare; end-to-end upload tests must
  run against a real bucket.
- **`wrangler dev` watches `wrangler.toml` for binding changes**: editing the toml while
  the dev server is running triggers a full reload, resetting in-memory state but not
  the persisted SQLite file.
- **`.dev.vars` values are always strings**: unlike Cloudflare secrets, there is no
  native support for JSON secret values. Parse at access time with `JSON.parse()`.
- **Inspector port collision when running two workers**: if the monorepo has two Worker
  packages, each needs a distinct `--inspector-port`.

## Verification

```bash
# 1. Confirm worker starts in local mode
pnpm wrangler dev --local --persist-to .wrangler/state 2>&1 | grep "Local"
# Expected: "[mf:inf] Ready on http://localhost:8787"

# 2. Confirm D1 responds
curl http://localhost:8787/users
# Expected: JSON array from local SQLite

# 3. Confirm R2 responds
curl http://localhost:8787/logo.png -o /tmp/logo-check.png
file /tmp/logo-check.png
# Expected: PNG image data

# 4. Confirm .dev.vars loaded
curl http://localhost:8787/debug/env-check
# This endpoint should return 200 if JWT_SECRET is non-empty

# 5. Confirm Next.js proxy works
curl http://localhost:3000/api/worker/users
# Expected: same JSON array, proxied through Next.js
```

## Related

- `wrangler-dev-local-mocking.md` — general Wrangler mocking patterns
- `vitest-workers-miniflare-testing-setup.md` — unit tests against Miniflare
- `turborepo-cloudflare-workers-pipeline.md` — pipeline caching for wrangler builds
- `cloudflare-tunnel-dev.md` — exposing local worker to external services (webhooks)
- `dotenv-local-setup.md` — Next.js `.env.local` patterns

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/d1/get-started/#develop-locally-with-wrangler
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://miniflare.dev/storage/d1
- https://developers.cloudflare.com/workers/configuration/secrets/#local-development-with-secrets
