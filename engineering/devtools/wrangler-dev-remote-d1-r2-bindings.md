# Wrangler Dev with Remote D1 and R2 Bindings

- Date: 2026-08-22
- Author: example.com
- Status: production

---

## Symptom / Use-case

You're developing a Cloudflare Worker locally with `wrangler dev` but you need it to hit **real, production-like data** — a populated D1 database or an R2 bucket containing actual assets — rather than the empty local SQLite file or a mock bucket that local mode creates. The `--remote` flag and per-binding remote overrides let you point individual bindings at live Cloudflare resources while keeping everything else (CPU, latency, networking) local.

Typical scenarios:
- Integration tests against a staging D1 database seeded with representative data
- Verifying R2 presigned URL generation against a real bucket
- Debugging a data-migration Worker that must read from production (read-only) schema
- Running a Worker that depends on a D1 database too large to replicate locally in CI

---

## Context

`wrangler dev` has two primary modes:

| Mode | Flag | Where code runs | Where bindings resolve |
|------|------|-----------------|------------------------|
| Local (default) | *(none)* | Miniflare in-process | Local SQLite / in-memory |
| Remote | `--remote` | Cloudflare edge | Live Cloudflare resources |
| Hybrid | `--remote` + per-binding overrides | Cloudflare edge | Mix of local and live |

Before Wrangler 3.x, `--local` was the flag for local mode; `--remote` enabled full remote execution. Since Wrangler 3, local is the **default** and `--remote` opts into remote execution. Per-binding remote/local overrides (introduced in Wrangler 3.22) let you mix modes without going fully remote.

Important distinction: `--remote` routes **all traffic through the Cloudflare network**, so your Worker's outbound `fetch()` calls go through Cloudflare's network stack and count against your Workers Paid plan usage. Per-binding remote overrides avoid this — only the specific binding hits Cloudflare.

---

## Full Remote Mode (`--remote`)

The simplest approach: run everything on Cloudflare's edge against live resources.

```bash
# Run fully remote — all bindings resolve to real Cloudflare resources
wrangler dev --remote

# Combine with a specific environment
wrangler dev --remote --env staging
```

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "my-staging-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-staging-bucket"
```

In `--remote` mode Wrangler authenticates via `CLOUDFLARE_API_TOKEN` (or `wrangler login`) and proxies requests to the real database and bucket. Every `env.DB.prepare(...)` call executes a real D1 query against `my-staging-db`.

---

## Per-Binding Remote Overrides (Hybrid Mode)

Wrangler 3.22+ supports `--x-remote-bindings` or inline `remote = true` in the binding configuration to keep local execution while proxying only named bindings to Cloudflare.

```bash
# Keep code running locally but proxy DB and BUCKET to live Cloudflare resources
wrangler dev --x-remote-bindings DB,BUCKET
```

Or declare it in `wrangler.toml` so you don't need the CLI flag:

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "my-staging-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
# This binding proxies to Cloudflare in local dev:
remote = true

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-staging-bucket"
# This one stays local (no remote = true):
preview_bucket_name = "my-local-bucket"

[vars]
ENVIRONMENT = "staging"
```

With this config, `wrangler dev` (no flags needed) runs the Worker in Miniflare locally but proxies all `env.DB.*` calls to the real D1 database and all `env.BUCKET.*` calls stay local.

---

## Environment-Specific Remote Configurations

Use Wrangler environments to cleanly separate local-only vs. remote-connected setups:

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

# Default: fully local, good for unit/integration tests
[[d1_databases]]
binding = "DB"
database_name = "my-worker-local"
database_id = "00000000-0000-0000-0000-000000000000"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-worker-local"

# Staging env: remote bindings against staging resources
[env.staging]
[[env.staging.d1_databases]]
binding = "DB"
database_name = "my-worker-staging"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
remote = true

[[env.staging.r2_buckets]]
binding = "BUCKET"
bucket_name = "my-worker-staging"
remote = true

# Production env: read-only access, useful for debugging
[env.production]
[[env.production.d1_databases]]
binding = "DB"
database_name = "my-worker-prod"
database_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
remote = true
```

```bash
# Local dev (default):
wrangler dev

# Dev against staging data:
wrangler dev --env staging

# Debug against production (careful!):
wrangler dev --env production --remote
```

---

## Authentication for Remote Bindings

Remote bindings require a valid Cloudflare API token. Wrangler picks it up in this order:

1. `CLOUDFLARE_API_TOKEN` environment variable (preferred for CI)
2. `CLOUDFLARE_API_KEY` + `CLOUDFLARE_EMAIL` (legacy)
3. Token stored by `wrangler login` in `~/.config/.wrangler/`

For CI pipelines, create a scoped API token with only the permissions needed:

```bash
# Minimum token permissions for D1 + R2 remote dev:
# - Workers D1:Read
# - Workers R2 Storage:Read (or Edit if the Worker writes)
# - Workers Scripts:Read (needed for wrangler dev --remote)

export CLOUDFLARE_API_TOKEN="your_token_here"
wrangler dev --env staging
```

Check your token resolves correctly before a dev session:

```bash
wrangler whoami
# Should print: You are logged in with an API Token...
```

---

## D1 Remote Queries in Development

When `remote = true` is set for a D1 binding, every query your Worker makes goes over the Cloudflare API. This means:

- Latency is higher than local SQLite (expect 50–200ms round trips in dev)
- Writes are **real** — they persist in the remote database
- You must have network access (breaks offline development)

A safety pattern: use D1's transaction support and wrap exploratory dev queries in an explicit rollback:

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Wrap mutations in a transaction that can be rolled back manually
    const isDev = env.ENVIRONMENT !== 'production';

    if (isDev && request.method === 'POST') {
      // For destructive operations in dev, log but don't commit
      const stmt = env.DB.prepare('INSERT INTO items (name) VALUES (?)');
      const info = await stmt.bind('test-item').run();
      console.log('[dev] Would insert, rowsAffected:', info.meta.changes);
      // In real dev you'd commit; this is just showing the pattern
    }

    const results = await env.DB.prepare('SELECT * FROM items LIMIT 10').all();
    return Response.json(results.results);
  }
} satisfies ExportedHandler<Env>;
```

---

## R2 Remote Access Patterns

R2 remote bindings work transparently — all `env.BUCKET.*` calls proxy to the real bucket:

```typescript
// Reading from remote R2 in local dev
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading /

    // This call hits the real R2 bucket when remote = true
    const object = await env.BUCKET.get(key);

    if (!object) {
      return new Response('Not Found', { status: 404 });
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('etag', object.httpEtag);

    return new Response(object.body, { headers });
  }
} satisfies ExportedHandler<Env>;
```

For R2 writes in dev, use a dedicated staging bucket and never point at production:

```toml
[env.staging]
[[env.staging.r2_buckets]]
binding = "BUCKET"
bucket_name = "my-app-staging"  # Never my-app-production
remote = true
```

---

## Anti-Patterns

**Pointing at production D1 with write access in dev.** A typo in a migration script run via `wrangler dev --env production` will corrupt real data. Always use staging databases for remote dev.

**Checking in `CLOUDFLARE_API_TOKEN` to source control.** Use `.env` files (gitignored) or CI secrets. The token in `wrangler.toml` via `[vars]` is sent to Workers and is not appropriate for API tokens.

**Using `--remote` for all local development.** It adds network latency, consumes API quota, and requires internet access. Use per-binding `remote = true` selectively.

**Assuming remote latency matches production.** D1 remote queries in `wrangler dev --remote` go through the Cloudflare API, not the same code path as deployed Workers. Latency is not representative of production; use `wrangler tail` for production performance data.

**Forgetting that KV bindings also support `remote = true`.** The same pattern applies to KV namespaces — don't overlook them when setting up hybrid dev environments.

---

## Gotchas

- **`remote = true` requires Wrangler ≥ 3.22.** Earlier versions ignore it silently and use local mode. Pin your Wrangler version in `package.json` to avoid surprises.

- **D1 database IDs differ per environment.** Copy the correct `database_id` from the Cloudflare dashboard for each database; a wrong ID gives a cryptic "database not found" error, not a clear auth error.

- **R2 preview bucket name is only used in local mode.** When `remote = true`, `preview_bucket_name` is ignored — the real `bucket_name` is used. Don't rely on it as a safety net.

- **`wrangler dev --remote` uses a preview URL**, not your Worker's production route. Wrangler creates a temporary `*.workers.dev` preview URL for the session.

- **Workers Free plan cannot use `--remote`.** Remote mode requires Workers Paid (Bundled). You'll get an error: `Workers Lite is not supported for remote mode`.

- **Rate limits apply to remote D1 queries.** D1's API tier rate limits can throttle aggressive local tests that loop queries. Add a short sleep between test iterations or use local mode with a seeded database for load testing.

---

## Verification

```bash
# 1. Confirm Wrangler version supports remote bindings
wrangler --version
# Should be >= 3.22.0

# 2. Verify authentication
wrangler whoami

# 3. Start dev with remote staging bindings
wrangler dev --env staging

# 4. In another terminal, hit the local dev server
curl http://localhost:8787/

# 5. Check D1 query actually reached the remote database
# In the Cloudflare dashboard: D1 > your-staging-db > Metrics
# You should see a spike in read requests matching your test

# 6. Verify R2 object was served from remote bucket
curl -v http://localhost:8787/some-key
# Response headers should contain ETag from the real object
```

---

## Related

- `wrangler-dev-local-d1-r2-kv.md` — Local mode with Miniflare (no network required)
- `durable-objects-local-debugging.md` — Local Durable Objects dev patterns
- `vitest-workers-miniflare-testing-setup.md` — Unit testing with Miniflare
- `local-https-dev-proxy-wrangler.md` — HTTPS in local dev
- `opentelemetry-workers-tracing-setup.md` — Tracing Workers in staging

---

## Sources

- Wrangler Remote Bindings docs: https://developers.cloudflare.com/workers/wrangler/configuration/#d1-databases
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- R2 bindings reference: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Wrangler 3 migration guide: https://developers.cloudflare.com/workers/wrangler/migration/migrating-from-wrangler-2/
- D1 REST API (used by remote bindings): https://developers.cloudflare.com/d1/platform/rest-api/
