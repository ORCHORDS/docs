# Hyperdrive Connection String Rotation Zero-Downtime

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A security audit required rotation of the PostgreSQL credentials used by a production Cloudflare Hyperdrive configuration. The naïve approach — update the Hyperdrive config with the new connection string via `wrangler hyperdrive update`, then revoke the old credentials — caused a 47-second window of `connection refused` errors as in-flight Worker requests attempted to use the Hyperdrive connection pool that was being drained and reconnected. A zero-downtime rotation procedure was needed.

## Context

Cloudflare Hyperdrive acts as a regional connection pool and query cache layer between Workers and an origin PostgreSQL (or compatible) database. Each Hyperdrive configuration stores the full database connection string (host, port, user, password, database). When the connection string is updated via API or Wrangler, Hyperdrive must drain existing connections, establish new ones using the updated credentials, and promote the new pool — a process that takes 10–60 seconds depending on pool size and origin latency.

Workers bind to a specific Hyperdrive config ID (`HYPERDRIVE = { binding = "DB", id = "..." }`). If only one Hyperdrive config exists, there is no blue-green swap possible at the Hyperdrive layer. The zero-downtime approach requires maintaining **two** Hyperdrive configs and performing a Worker deployment that switches the binding.

---

## 1. Architecture: Two-Config Blue-Green Pattern

```
                      ┌─────────────────────────────────────────┐
                      │  Cloudflare Workers                      │
                      │                                          │
  (before rotation)   │   env.DB → hyperdrive-config-blue       │
  (after rotation)    │   env.DB → hyperdrive-config-green      │
                      └─────────────────────────────────────────┘
                             │                         │
                    ┌────────┴──────┐         ┌────────┴──────┐
                    │  Hyperdrive   │         │  Hyperdrive   │
                    │  (blue)       │         │  (green)      │
                    │  user: app_v1 │         │  user: app_v2 │
                    └──────┬────────┘         └──────┬────────┘
                           │                         │
                           └────────────┬────────────┘
                                        │
                                ┌───────▼────────┐
                                │  PostgreSQL     │
                                │  (Neon / Supabase│
                                │   / self-hosted) │
                                └────────────────┘
```

Maintain a `blue` and a `green` Hyperdrive config at all times. The active one is referenced in `wrangler.toml`; the standby is ready to receive updated credentials.

---

## 2. Initial Setup: Provisioning Two Configs

```bash
# Create the blue config (current active)
wrangler hyperdrive create hyperdrive-blue \
  --connection-string "postgresql://app_v1:secret_v1@db.example.com:5432/prod"

# Create the green config (standby — same creds initially)
wrangler hyperdrive create hyperdrive-green \
  --connection-string "postgresql://app_v1:secret_v1@db.example.com:5432/prod"
```

```toml
# wrangler.toml — Worker references the active config by ID
[[hyperdrive]]
binding = "DB"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # blue config ID
```

---

## 3. Zero-Downtime Rotation Procedure

```typescript
// scripts/rotate-hyperdrive-credentials.ts
// Prerequisites:
//   - New DB user/password already created in PostgreSQL
//   - STANDBY_HYPERDRIVE_ID is the config NOT currently in use
//   - ACTIVE_HYPERDRIVE_ID is the config currently in use

import { execSync } from "node:child_process";

const STANDBY_ID = process.env.STANDBY_HYPERDRIVE_ID!;
const ACTIVE_ID = process.env.ACTIVE_HYPERDRIVE_ID!;
const NEW_CONN = process.env.NEW_CONNECTION_STRING!; // postgresql://app_v2:secret_v2@...
const WORKER_NAME = process.env.CF_WORKER_NAME!;

async function rotateCredentials() {
  // Step 1: Update STANDBY config with new credentials (no traffic hits it yet)
  console.log("Step 1: Updating standby Hyperdrive config with new credentials...");
  execSync(
    `wrangler hyperdrive edit ${STANDBY_ID} --connection-string "${NEW_CONN}"`,
    { stdio: "inherit" }
  );

  // Step 2: Wait for Hyperdrive to establish pool on standby
  console.log("Step 2: Waiting 30 s for standby pool to warm up...");
  await new Promise((r) => setTimeout(r, 30_000));

  // Step 3: Update wrangler.toml to point binding at standby config
  console.log("Step 3: Swapping Worker binding to standby config...");
  const toml = (await import("node:fs")).readFileSync("wrangler.toml", "utf8");
  const updated = toml.replace(ACTIVE_ID, STANDBY_ID);
  (await import("node:fs")).writeFileSync("wrangler.toml", updated);

  // Step 4: Deploy Worker — this atomically shifts all new requests to standby
  console.log("Step 4: Deploying Worker with new Hyperdrive binding...");
  execSync(`wrangler deploy`, { stdio: "inherit" });

  // Step 5: Let old connections drain (Hyperdrive drains within ~30 s)
  console.log("Step 5: Waiting 60 s for old config connections to drain...");
  await new Promise((r) => setTimeout(r, 60_000));

  // Step 6: Revoke old credentials in PostgreSQL
  console.log("Step 6: Revoking old DB user...");
  // Execute via psql or your migration tool:
  // execSync(`psql $OLD_CONN -c "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_v1; DROP USER app_v1;"`)

  // Step 7: Update old (now-standby) config to new creds so it's ready for next rotation
  console.log("Step 7: Syncing old config to new credentials for future use...");
  execSync(
    `wrangler hyperdrive edit ${ACTIVE_ID} --connection-string "${NEW_CONN}"`,
    { stdio: "inherit" }
  );

  console.log("Rotation complete. Swap ACTIVE_ID and STANDBY_ID for next rotation.");
}

rotateCredentials().catch((e) => { console.error(e); process.exit(1); });
```

---

## 4. Health-Check During Rotation

Poll the Worker's health endpoint during the rotation to detect any connection failures immediately.

```typescript
// scripts/poll-health-during-rotation.ts
async function pollHealth(workerUrl: string, durationMs: number, intervalMs = 2000) {
  const end = Date.now() + durationMs;
  let failures = 0;

  while (Date.now() < end) {
    try {
      const res = await fetch(`${workerUrl}/health`);
      if (!res.ok) {
        failures++;
        console.error(`[${new Date().toISOString()}] Health check FAILED: ${res.status}`);
      } else {
        const body = await res.json() as { db: string };
        console.log(`[${new Date().toISOString()}] OK — db: ${body.db}`);
      }
    } catch (e) {
      failures++;
      console.error(`[${new Date().toISOString()}] Health check ERROR:`, e);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }

  console.log(`\nPolling complete. Failures: ${failures}`);
  if (failures > 0) throw new Error("Health check failures detected during rotation");
}
```

```typescript
// Worker health endpoint
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      try {
        const result = await env.DB.prepare("SELECT 1 AS ok").first<{ ok: number }>();
        return Response.json({ status: "ok", db: result?.ok === 1 ? "connected" : "error" });
      } catch (e) {
        return Response.json({ status: "error", db: String(e) }, { status: 503 });
      }
    }
    // ... rest of handler
    return new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. Terraform / IaC Approach

If credentials are managed via Terraform (Cloudflare provider), the rotation is safer because Terraform can update the standby resource and plan the Worker binding change in a single `apply`.

```hcl
# main.tf
resource "cloudflare_hyperdrive_config" "blue" {
  account_id = var.account_id
  name       = "hyperdrive-blue"
  origin = {
    database = "prod"
    host     = var.db_host
    port     = 5432
    scheme   = "postgresql"
    user     = var.db_user_blue
    password = <redacted-secret>
  }
}

resource "cloudflare_hyperdrive_config" "green" {
  account_id = var.account_id
  name       = "hyperdrive-green"
  origin = {
    database = "prod"
    host     = var.db_host
    port     = 5432
    scheme   = "postgresql"
    user     = var.db_user_green
    password = <redacted-secret>
  }
}

# Rotate by changing var.active_hyperdrive_slot between "blue" and "green"
locals {
  active_hyperdrive_id = var.active_hyperdrive_slot == "blue"
    ? cloudflare_hyperdrive_config.blue.id
    : cloudflare_hyperdrive_config.green.id
}
```

---

## Anti-patterns

- Updating the single active Hyperdrive config in-place and expecting zero downtime — there is always a pool-drain window of 10–60 seconds.
- Revoking old credentials before confirming the new Hyperdrive pool is healthy — if the new credentials have a typo or wrong host, you have a full outage with no rollback.
- Using the same Hyperdrive config ID for both old and new credentials — the config ID is immutable; you must create a new one or update an existing standby.
- Setting `cacheDisabled = true` in Hyperdrive during rotation to "reduce stale data risk" — disabling the query cache also removes the connection pooling benefit, increasing load on the origin during an already sensitive period.
- Storing the connection string in the Worker's environment variables directly as a fallback "just in case" — this bypasses Hyperdrive entirely and exposes credentials in the Worker's env, which are visible in the dashboard.

## Gotchas

- `wrangler hyperdrive edit` silently succeeds even if the new connection string is unreachable. Always verify with a Worker health check before revoking old credentials.
- Hyperdrive does not support read replicas natively — if you use pgBouncer or pgpool, the rotation must target the pooler's credentials, not the database's.
- The Cloudflare Terraform provider (`cloudflare_hyperdrive_config`) as of v4 does not support `origin.password` in state (it is write-only). Plan carefully when importing existing configs.
- Hyperdrive caches query results keyed by query text and parameters. After a schema migration accompanying the credential rotation, purge the Hyperdrive cache explicitly via the API or set `cacheDisabled = true` temporarily.
- Worker bindings reference Hyperdrive config IDs, not names. A typo in the ID in `wrangler.toml` causes a silent fallback to `undefined` at runtime, resulting in `TypeError: Cannot read properties of undefined`.

## Verification

```bash
# Confirm which Hyperdrive config the deployed Worker uses
wrangler deployments list --name my-worker | head -3

# List all Hyperdrive configs and their IDs
wrangler hyperdrive list

# Test standby config connectivity before swapping (Workers preview)
wrangler dev --test-scheduled  # or hit /health on a preview URL

# After rotation: confirm old user can no longer connect
psql "postgresql://app_v1:secret_v1@db.example.com:5432/prod" -c "SELECT 1;"
# Expected: connection rejected / authentication failed
```

## Related

- `cloudflare-storage-primitive-selection.md`
- `developer-experience-dx-cloudflare-workers.md`
- `never-store-secrets-in-env-files.md`
- `rotate-credentials-after-every-breach.md`
- `zero-downtime-deployment-workers.md`

## Sources

- Cloudflare Hyperdrive docs: https://developers.cloudflare.com/hyperdrive/
- Hyperdrive configuration reference: https://developers.cloudflare.com/hyperdrive/configuration/
- Wrangler hyperdrive commands: https://developers.cloudflare.com/workers/wrangler/commands/#hyperdrive
- Cloudflare Terraform provider — hyperdrive_config: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/hyperdrive_config
