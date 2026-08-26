# Hyperdrive PostgreSQL Pulumi IaC Config

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Workers need low-latency access to a PostgreSQL database hosted in AWS RDS or
Supabase. Cold connections from Workers to Postgres are slow (~50–200 ms) because every Worker
isolate opens its own TCP+TLS+auth handshake. Cloudflare Hyperdrive solves this with a regional
connection pool, but provisioning a Hyperdrive config through the dashboard across prod/staging
environments leads to drift. You need reproducible Pulumi IaC that provisions Hyperdrive,
binds it to the right Worker, and keeps credentials out of state.

## Context

Hyperdrive is a Cloudflare service that maintains persistent, pooled PostgreSQL connections from
Cloudflare's network to your origin database. Workers bind to a Hyperdrive config by name and
receive a `connectionString` that routes through the pooler instead of directly to the origin.
The Pulumi Cloudflare provider exposes `cloudflare.Hyperdrive` (package `@pulumi/cloudflare`,
class introduced in ~0.3.0 / provider ≥ 4.22). Credentials are passed as plaintext at config
creation time and are not retrievable afterward — treat them as write-only inputs.

---

## 1. Project Structure

```
infra/
  index.ts          # Pulumi program entry point
  hyperdrive.ts     # Hyperdrive config resources
  worker.ts         # Workers script + binding
  config.ts         # Pulumi config helpers
Pulumi.yaml
Pulumi.prod.yaml
Pulumi.staging.yaml
```

---

## 2. Pulumi Config Helpers

```typescript
// infra/config.ts
import * as pulumi from "@pulumi/pulumi";

const cfg = new pulumi.Config();

export const accountId    = cfg.require("cloudflareAccountId");
export const zoneId       = cfg.require("cloudflareZoneId");

// Database credentials — stored as Pulumi secrets, never in plain YAML
export const dbHost       = cfg.require("dbHost");         // e.g. db.prod.example.com
export const dbPort       = cfg.requireNumber("dbPort");   // 5432
export const dbName       = cfg.require("dbName");
export const dbUser       = cfg.require("dbUser");
export const dbPassword   = cfg.requireSecret("dbPassword"); // pulumi config set --secret
```

Set secrets before first `pulumi up`:

```bash
pulumi config set cloudflareAccountId  "abc123"
pulumi config set dbHost               "db.prod.example.com"
pulumi config set dbPort               5432
pulumi config set dbName               "myapp"
pulumi config set dbUser               "app_readonly"
pulumi config set --secret dbPassword  "s3cr3t"
```

---

## 3. Hyperdrive Config Resource

```typescript
// infra/hyperdrive.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import { accountId, dbHost, dbPort, dbName, dbUser, dbPassword } from "./config";

const stack = pulumi.getStack(); // "prod" | "staging"

export const hyperdriveConfig = new cloudflare.Hyperdrive(
  `hyperdrive-${stack}`,
  {
    accountId,
    name: `postgres-${stack}`,  // binding name referenced in Worker
    origin: {
      database: dbName,
      host: dbHost,
      password: dbPassword,
      port: dbPort,
      scheme: "postgres",
      user: dbUser,
    },
    caching: {
      // Disable query-result caching for write-heavy workloads.
      // Enable with maxAge for read-heavy analytical queries.
      disabled: false,
    },
  },
  {
    // dbPassword is a Pulumi secret Output; the resource itself is
    // also marked secret so it does not appear in plan output.
    additionalSecretOutputs: ["origin"],
  }
);

export const hyperdriveName = hyperdriveConfig.name;
export const hyperdriveId   = hyperdriveConfig.id;
```

---

## 4. Worker Script with Hyperdrive Binding

```typescript
// infra/worker.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import * as fs from "fs";
import { accountId, zoneId } from "./config";
import { hyperdriveId, hyperdriveName } from "./hyperdrive";

const stack = pulumi.getStack();

const workerScript = new cloudflare.WorkersScript(
  `api-worker-${stack}`,
  {
    accountId,
    name: `api-${stack}`,
    content: fs.readFileSync("../dist/worker.js", "utf8"),
    hyperdriveConfigBindings: [
      {
        name: "HYPERDRIVE",          // env binding name inside Worker
        id: hyperdriveId,
      },
    ],
  }
);

new cloudflare.WorkerRoute(`api-route-${stack}`, {
  zoneId,
  pattern: stack === "prod" ? "api.example.com/*" : "api-staging.example.com/*",
  scriptName: workerScript.name,
});
```

---

## 5. Worker Database Access

```typescript
// src/worker.ts  (the Workers bundle, not Pulumi code)
import { Pool } from "pg";  // use the "pg" npm package or postgres.js

interface Env {
  HYPERDRIVE: Hyperdrive;  // Cloudflare global type
}

let pool: Pool | null = null;

function getPool(env: Env): Pool {
  // Reuse pool across requests within the same isolate
  if (!pool) {
    pool = new Pool({
      connectionString: env.HYPERDRIVE.connectionString,
      // Hyperdrive handles pooling externally; keep local pool size small
      max: 5,
    });
  }
  return pool;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const db = getPool(env);
    const { rows } = await db.query(
      "SELECT id, name FROM products WHERE active = $1 LIMIT 50",
      [true]
    );
    return Response.json(rows);
  },
};
```

---

## 6. Stack-Specific Database Routing

```yaml
# Pulumi.staging.yaml
config:
  cloudflareAccountId: "abc123"
  cloudflareZoneId: "zone456"
  dbHost: "db-staging.internal.example.com"
  dbPort: 5432
  dbName: "myapp_staging"
  dbUser: "app_staging"
  # dbPassword set via: pulumi config set --secret dbPassword --stack staging
```

```yaml
# Pulumi.prod.yaml
config:
  cloudflareAccountId: "abc123"
  cloudflareZoneId: "zone789"
  dbHost: "db-prod.cluster.us-east-1.rds.amazonaws.com"
  dbPort: 5432
  dbName: "myapp"
  dbUser: "app_prod"
```

---

## Anti-patterns

- **Passing the raw origin database connection string to Workers without Hyperdrive.** Each Worker
  isolate would open its own TCP connection on every cold start, exhausting RDS `max_connections`
  under moderate concurrency.
- **Enabling Hyperdrive caching on tables with mutable data and no explicit cache invalidation.**
  Hyperdrive caches `SELECT` results by default; writes to the same rows from outside Workers will
  not invalidate the cache. Set `disabled: true` for write-heavy or consistency-critical datasets.
- **Storing `dbPassword` as a plain Pulumi config value.** Always use `pulumi config set --secret`.
  The encrypted value is safe in `Pulumi.<stack>.yaml` and the state backend; a plain value is not.
- **Recreating the `Pool` on every request.** Pulumi provisions one Hyperdrive config but each
  Worker isolate manages its own connection state. Module-level pool reuse is essential.

---

## Gotchas

- Hyperdrive credentials (password) are write-only: once created, the Cloudflare API does not
  return them. If you lose the Pulumi state or secret, you must delete and recreate the Hyperdrive
  config with updated credentials.
- Pulumi will show `[secret]` for the `origin` output block when `additionalSecretOutputs` is
  set — this is correct behavior, not an error.
- Hyperdrive currently supports PostgreSQL and MySQL. Passing a non-standard `scheme` returns a
  `400` from the Cloudflare API.
- `pg` (node-postgres) works inside Workers; `pg-native` does not (native bindings not supported
  in the Workers runtime). Use the pure-JS build: `pg` with `"browser": false` in package.json.
- Connection limits at the origin still apply. Hyperdrive pools connections per Cloudflare region,
  not globally. With 15+ Cloudflare PoPs, plan for `max_connections` = `15 × local_pool_size`.

---

## Verification

```bash
# Confirm Hyperdrive config exists
pulumi stack output hyperdriveId   # prints the config ID

# Via API
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/hyperdrive/configs" \
  | jq '.result[] | {id, name, origin: (.origin | del(.password))}'

# Check Worker binding
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/api-prod/bindings" \
  | jq '.result[] | select(.type=="hyperdrive") | {name, id}'

# No drift
pulumi preview --diff
```

---

## Related

- `pulumi-cloudflare-workers-infrastructure-as-code.md`
- `pulumi-cloudflare-provider-advanced.md`
- `pulumi-esc-secrets-config-management.md`
- `postgresql-connection-pooling-pgbouncer.md`
- `terraform-cloudflare-provider-workers-d1.md`

---

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/get-started/
- https://www.pulumi.com/registry/packages/cloudflare/api-docs/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/connecting-to-your-database/
