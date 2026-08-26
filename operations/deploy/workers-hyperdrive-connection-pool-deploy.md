# Workers Hyperdrive Connection Pool Deploy Strategy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Worker that queries a remote PostgreSQL or MySQL database cold-starts a new TCP+TLS connection on every request. At scale this adds 200–400 ms of latency and exhausts the database's `max_connections`. Hyperdrive solves this by maintaining a persistent, regional connection pool that Workers reuse — but wiring it correctly across `dev`, `staging`, and `production` environments without leaking credentials or binding the wrong pool requires a deliberate deploy strategy.

## Context

Hyperdrive configs are account-level objects identified by a UUID. Each config points to a single connection string and exposes a binding name the Worker uses at runtime. Because the UUID is environment-specific (each Cloudflare environment gets its own config), `wrangler.toml` must reference the correct ID per environment. Misconfiguring the binding causes the Worker to fall back to direct connections silently in local dev but fail in production when the actual database rejects unauthenticated requests.

---

## 1. Provision Hyperdrive Configs per Environment

Create separate Hyperdrive configs for each environment. Never share a production config with staging.

```bash
# staging
wrangler hyperdrive create example project-staging-pg \
  --connection-string "postgresql://user:pass@staging-db.example.com:5432/example project"

# production
wrangler hyperdrive create example project-prod-pg \
  --connection-string "postgresql://user:pass@prod-db.example.com:5432/example project"
```

Save the returned UUIDs; they are the binding targets in `wrangler.toml`.

---

## 2. Wire Bindings in wrangler.toml

```toml
name = "example project-api"
compatibility_date = "2025-09-01"

# default (local dev — no Hyperdrive, use direct URL from .dev.vars)
[[hyperdrive]]
binding = "DB"
localConnectionString = "postgresql://localhost:5432/example project_dev"

[env.staging]
[[env.staging.hyperdrive]]
binding = "DB"
id     = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # staging UUID

[env.production]
[[env.production.hyperdrive]]
binding = "DB"
id     = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"  # production UUID
```

The `binding` name (`DB`) stays identical across all environments so Worker source code needs no branching.

---

## 3. Worker Query Pattern

```typescript
import postgres from "postgres";

export interface Env {
  DB: Hyperdrive;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.DB.connectionString is injected by Hyperdrive at runtime.
    // The sql client reuses pooled connections from the regional proxy.
    const sql = postgres(env.DB.connectionString, {
      max: 5,           // per-isolate soft cap; Hyperdrive manages the real pool
      idle_timeout: 20,
      connect_timeout: 10,
    });

    try {
      const rows = await sql`SELECT id, name FROM tenants LIMIT 10`;
      return Response.json(rows);
    } finally {
      await sql.end({ timeout: 5 });
    }
  },
};
```

---

## 4. CI/CD Deploy Gate — Validate Config Existence Before Deploy

Add a pre-deploy step that verifies the target Hyperdrive UUID exists in the account before `wrangler deploy` runs. A stale UUID causes a runtime panic, not a deploy error.

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Validate Hyperdrive config
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    HYPERDRIVE_ID: ${{ secrets.HYPERDRIVE_PROD_ID }}
  run: |
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
      "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/hyperdrive/configs/$HYPERDRIVE_ID")
    if [ "$STATUS" != "200" ]; then
      echo "Hyperdrive config $HYPERDRIVE_ID not found (HTTP $STATUS). Aborting deploy."
      exit 1
    fi

- name: Deploy Worker
  run: wrangler deploy --env production
```

---

## 5. Connection Pool Health Gate Post-Deploy

After deploy, smoke-test pool connectivity with a dedicated endpoint rather than a real query. This separates pool health from application logic errors.

```typescript
// src/routes/healthz.ts
export async function handleHealth(env: Env): Promise<Response> {
  const sql = postgres(env.DB.connectionString, { max: 1, connect_timeout: 5 });
  try {
    await sql`SELECT 1`;
    return new Response("ok", { status: 200 });
  } catch (err) {
    return new Response(`db_error: ${(err as Error).message}`, { status: 503 });
  } finally {
    await sql.end({ timeout: 3 });
  }
}
```

```bash
# Post-deploy verification
curl -f https://example project-api.example.com/healthz || (echo "Pool health gate failed"; exit 1)
```

---

## 6. Rotating the Database Password Without Downtime

Hyperdrive caches connections. To rotate credentials:

1. Update the secret in your vault.
2. Call the Hyperdrive API to patch the connection string:
   ```bash
   wrangler hyperdrive update $HYPERDRIVE_PROD_ID \
     --connection-string "postgresql://user:NEW_PASS@prod-db.example.com:5432/example project"
   ```
3. Hyperdrive drains existing connections over 30 s and opens new ones with the updated password. No Worker redeploy needed.
4. Revoke the old password only after the Hyperdrive status shows 0 connections using it.

---

## Anti-patterns

- Hardcoding the connection string directly in Worker code instead of using `env.DB.connectionString` — bypasses the pool entirely.
- Sharing a single Hyperdrive config UUID across staging and production — a staging traffic spike can exhaust production's pool.
- Not capping `max` on the sql client — each isolate instance opens its own connections through Hyperdrive, multiplying the real pool size unexpectedly.
- Using `wrangler dev --remote` without a local connection string fallback — breaks offline development.

## Gotchas

- Hyperdrive does **not** support Unix socket connections; only TCP-based databases are supported.
- The `connectionString` exposed via `env.DB.connectionString` changes format between Hyperdrive API versions; always read it at runtime, never cache it across requests.
- Hyperdrive pools are regional. A Worker in a region with no cached connection still pays the cold-start cost on the first request to that region.
- `wrangler.toml` `[[hyperdrive]]` stanzas under `[env.X]` must use `[[env.X.hyperdrive]]` syntax — not `[[hyperdrive]]` — or Wrangler silently ignores them.

## Verification

```bash
# 1. Confirm binding appears in deployed Worker metadata
wrangler deployments list --env production | head -5

# 2. Hit the health endpoint
curl -s https://example project-api.example.com/healthz

# 3. Check Hyperdrive metrics in the dashboard for active connections > 0
wrangler hyperdrive get $HYPERDRIVE_PROD_ID
```

## Related

- `workers-binding-version-management.md`
- `secrets-rotation-deploy-coordination.md`
- `workers-d1-pre-deploy-migration-safety.md`
- `deploy-cold-start-prewarming.md`
- `zero-downtime-database-migrations.md`

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/connect-to-postgres/
- https://developers.cloudflare.com/workers/wrangler/configuration/#hyperdrive
- https://developers.cloudflare.com/hyperdrive/platform/limits/
