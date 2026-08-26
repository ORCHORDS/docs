# Running `wrangler dev --remote` Against a Staging Environment

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Local `wrangler dev` (miniflare) mocks D1, KV, and R2 — but your bug only reproduces against real data or when testing against a staging dataset that does not exist locally. You need to run your Worker code locally while it makes live requests to staging-bound Cloudflare resources without deploying a new version.

---

## Context

`wrangler dev --remote` runs your Worker source locally but executes it on Cloudflare's infrastructure, binding to the real resources named in the active environment's `wrangler.toml`. Combined with `--env staging`, it loads the `[env.staging]` stanza, giving you access to staging D1 databases, KV namespaces, and R2 buckets. The Worker process still hot-reloads from your local file system, so you get a fast edit loop. The critical tradeoff is that **writes are real** — any KV `put`, D1 `INSERT`, or R2 `put` in remote mode persists to the staging namespace. Use `--var` to inject local overrides for secrets without touching Wrangler's secret store.

---

## Section 1 — wrangler.toml staging environment configuration

```toml
# wrangler.toml
name = "my-worker"
main = "src/worker.ts"
compatibility_date = "2025-08-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "my-db-production"
database_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

[[kv_namespaces]]
binding = "KV"
id = "<production-kv-id>"

# Staging environment overrides
[env.staging]
name = "my-worker-staging"

[[env.staging.d1_databases]]
binding = "DB"
database_name = "my-db-staging"
database_id = "11111111-2222-3333-4444-555555555555"

[[env.staging.kv_namespaces]]
binding = "KV"
id = "<staging-kv-id>"

[[env.staging.r2_buckets]]
binding = "BUCKET"
bucket_name = "my-bucket-staging"

[env.staging.vars]
LOG_LEVEL = "debug"
ENVIRONMENT = "staging"
```

---

## Section 2 — Running remote dev and injecting local secrets

```bash
# Basic remote dev against staging
wrangler dev --remote --env staging

# Override the default port and bind to all interfaces (useful in Docker / Codespaces)
wrangler dev --remote --env staging --ip 0.0.0.0 --port 8788

# Inject a secret locally without writing to Wrangler's secret store
# --var takes KEY=VALUE pairs; values shadow wrangler.toml [vars] and secrets
wrangler dev --remote --env staging \
  --var API_KEY="local-test-key-abc123" \
  --var STRIPE_SECRET="sk_test_xxxx"

# Run with verbose logging to inspect subrequest routing
wrangler dev --remote --env staging --log-level debug
```

```typescript
// src/worker.ts — no code changes needed for remote mode
import type { Env } from './types/env';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.DB, env.KV, env.BUCKET are the REAL staging resources in remote mode
    const value = await env.KV.get('ping');
    return new Response(`KV ping = ${value ?? 'null'}`, { status: 200 });
  },
} satisfies ExportedHandler<Env>;

// Smoke-test helper — call this endpoint first to verify staging bindings work
// GET /__ping → {"kv":"pong","d1_tables":["users","sessions"]}
export async function handlePing(env: Env): Promise<Response> {
  const kv = await env.KV.get('ping');

  const tables = await env.DB.prepare(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
  ).all<{ name: string }>();

  return Response.json({
    kv,
    d1_tables: tables.results.map((r) => r.name),
  });
}
```

---

## Section 3 — Verifying bindings and inspecting remote traffic

```bash
# Start remote dev in one terminal
wrangler dev --remote --env staging --port 8788

# In a second terminal, verify the KV binding is staging
curl -s http://localhost:8788/__ping | jq .

# Check which D1 database is responding
curl -s http://localhost:8788/__ping | jq '.d1_tables'

# Confirm a specific KV key exists in staging
wrangler kv key get ping \
  --namespace-id "<staging-kv-id>" \
  --env staging

# List recent D1 queries (requires wrangler ≥ 3.60)
wrangler d1 info my-db-staging --env staging

# Tail live logs from the remotely-executing Worker
# (opens a second log stream — separate terminal)
wrangler tail --env staging --format pretty
```

---

## Anti-patterns

- **Using `--remote` without `--env staging` in shared accounts** — without the env flag, Wrangler defaults to the production `wrangler.toml` bindings; you will read and write production data.
- **Storing staging secrets in `.dev.vars`** — `.dev.vars` only applies to local (miniflare) mode; remote mode ignores that file entirely. Use `--var` for ephemeral overrides or `wrangler secret put --env staging` for persistent ones.
- **Leaving `--remote` on in watch loops** — each file change triggers a remote upload; on slow connections this stalls the edit cycle. Use local mode for tight iteration and switch to remote only for integration verification.

---

## Gotchas

- Remote mode **counts against your Cloudflare plan's Workers request quota** — every `curl` or browser hit to `localhost:8788` is routed through Cloudflare's edge.
- KV writes in remote mode are **immediately durable**; there is no rollback. Seed staging KV with test data you are willing to overwrite.
- `--ip 0.0.0.0` is required when running inside a Docker container or GitHub Codespace; the default `127.0.0.1` bind is unreachable from the host.
- `wrangler dev --remote` requires you to be authenticated (`wrangler login` or `CLOUDFLARE_API_TOKEN` env var); it will silently fall back to local mode if unauthenticated.
- Hot-reload in remote mode re-uploads the compiled bundle — source maps are available in the edge console but `console.log` output appears in the `wrangler tail` stream, not the local terminal.

---

## Verification

```bash
# Confirm wrangler version supports --remote (≥ 3.x)
wrangler --version

# Authenticate if needed
wrangler login

# List available environments defined in wrangler.toml
wrangler deploy --dry-run --env staging 2>&1 | head -20

# Start remote dev
wrangler dev --remote --env staging

# Hit the local port (proxied to Cloudflare edge)
curl -v http://localhost:8787/

# Confirm you are hitting staging D1, not production
curl http://localhost:8787/__ping | jq '.d1_tables'
```

---

## Related

- `workers-secrets-dotenv-wrangler-local.md`
- `workers-vitest-type-coverage-report.md`

---

## Sources

- Wrangler dev remote mode — https://developers.cloudflare.com/workers/wrangler/commands/#dev
- Wrangler environments — https://developers.cloudflare.com/workers/wrangler/environments/
- wrangler dev `--var` flag — https://developers.cloudflare.com/workers/wrangler/commands/#dev
