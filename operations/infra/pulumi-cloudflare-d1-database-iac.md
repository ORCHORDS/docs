# Pulumi Cloudflare D1 Database IaC Management

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You manage Cloudflare D1 SQLite databases as code using Pulumi, need to provision databases per environment, bind them to Workers, run schema migrations in CI, and enforce lifecycle protection on production databases — all from a single Pulumi TypeScript program.

## Context

Cloudflare D1 is a serverless SQLite-on-the-edge database, replicated to PoPs near your Workers. The `@pulumi/cloudflare` package (≥ 5.x) exposes `cloudflare.D1Database` for creating databases and `cloudflare.WorkerScript` accepts `d1DatabaseBindings` in its args. Unlike Terraform, Pulumi programs are TypeScript-first, enabling typed binding structures and programmatic multi-database provisioning. Schema migrations are out of scope for Pulumi itself — they are CI pipeline responsibilities via `wrangler d1 migrations apply`.

## 1. Provider Setup and Stack Configuration

```typescript
// index.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

const config = new pulumi.Config("cloudflare");
const accountId = config.require("accountId");
const stack = pulumi.getStack(); // "staging" | "production"
```

```bash
# Set per-stack configuration
pulumi config set cloudflare:accountId <ACCOUNT_ID> --stack staging
pulumi config set --secret cloudflare:apiToken <TOKEN> --stack staging
```

## 2. Provisioning D1 Databases

```typescript
// databases.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

const stack = pulumi.getStack();

export const appDb = new cloudflare.D1Database("app-db", {
  accountId: accountId,
  name: `app-${stack}`,
}, {
  protect: stack === "production", // prevent accidental destroy
});

export const analyticsDb = new cloudflare.D1Database("analytics-db", {
  accountId: accountId,
  name: `analytics-${stack}`,
}, {
  protect: stack === "production",
});

export const appDbId = appDb.id;
export const analyticsDbId = analyticsDb.id;
```

The `protect` resource option prevents `pulumi destroy` or replacement on production. For staging it is omitted so tear-down is frictionless.

## 3. Worker with D1 Bindings

```typescript
// worker.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as fs from "fs";
import { appDb, analyticsDb } from "./databases";

const workerScript = new cloudflare.WorkerScript("api-worker", {
  accountId: accountId,
  name: `api-worker-${stack}`,
  content: fs.readFileSync("dist/worker.js", "utf-8"),
  d1DatabaseBindings: [
    {
      name: "APP_DB",
      databaseId: appDb.id,
    },
    {
      name: "ANALYTICS_DB",
      databaseId: analyticsDb.id,
    },
  ],
  compatibilityDate: "2024-09-23",
  compatibilityFlags: ["nodejs_compat"],
});
```

Worker TypeScript consuming D1:

```typescript
// src/worker.ts
interface Env {
  APP_DB: D1Database;
  ANALYTICS_DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === "/users") {
      const { results } = await env.APP_DB
        .prepare("SELECT id, name, email FROM users WHERE active = 1 LIMIT 50")
        .all<{ id: number; name: string; email: string }>();

      return Response.json(results);
    }

    if (pathname === "/log-event" && request.method === "POST") {
      const body = await request.json<{ event: string; userId: number }>();
      ctx.waitUntil(
        env.ANALYTICS_DB
          .prepare("INSERT INTO events (event, user_id, ts) VALUES (?, ?, ?)")
          .bind(body.event, body.userId, Date.now())
          .run()
      );
      return new Response(null, { status: 202 });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## 4. Programmatic Multi-Database Pattern

For SaaS tenants or feature flags requiring isolated databases:

```typescript
// multi-tenant.ts
const tenants = ["acme", "globex", "initech"];

const tenantDatabases = tenants.map(
  (tenant) =>
    new cloudflare.D1Database(`db-${tenant}`, {
      accountId: accountId,
      name: `tenant-${tenant}-${stack}`,
    }, {
      protect: stack === "production",
    })
);

// Export a map of tenant -> database ID for downstream lookup
export const tenantDbIds = pulumi.all(
  tenantDatabases.map((db) => db.id)
).apply((ids) =>
  Object.fromEntries(tenants.map((t, i) => [t, ids[i]]))
);
```

This pattern is impossible to express cleanly in Terraform without `count` / `for_each` loops and is a primary reason to prefer Pulumi for dynamic resource sets.

## 5. Stack References for Cross-Stack Database IDs

When the database layer is a separate Pulumi stack from the Worker layer:

```typescript
// infra/databases/index.ts  (database stack)
export const appDbId = appDb.id;

// infra/workers/index.ts  (worker stack)
import * as pulumi from "@pulumi/pulumi";

const dbStack = new pulumi.StackReference(
  `org/cloudflare-databases/${stack}`
);
const appDbId = dbStack.getOutput("appDbId");

const apiWorker = new cloudflare.WorkerScript("api-worker", {
  accountId: accountId,
  name: `api-worker-${stack}`,
  content: fs.readFileSync("dist/worker.js", "utf-8"),
  d1DatabaseBindings: [
    { name: "APP_DB", databaseId: appDbId.apply(String) },
  ],
});
```

## 6. CI Migration Step After Pulumi Up

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Pulumi Up
  run: pulumi up --yes --stack ${{ env.STACK }}
  env:
    PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}

- name: Export D1 database name
  id: d1
  run: |
    DB_NAME=$(pulumi stack output appDbName --stack ${{ env.STACK }})
    echo "db_name=$DB_NAME" >> "$GITHUB_OUTPUT"

- name: Apply D1 migrations
  run: |
    wrangler d1 migrations apply "${{ steps.d1.outputs.db_name }}" \
      --env ${{ env.STACK }}
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

Add `name` as a stack output alongside `id`:

```typescript
export const appDbName = appDb.name;
export const appDbId = appDb.id;
```

## Anti-patterns

- **Running `wrangler d1 migrations apply` before `pulumi up`** — the database may not yet exist; always gate migrations on a confirmed Pulumi output.
- **Sharing one D1 database across staging and production stacks** — a migration on staging can alter schema that production Workers depend on. Each stack must own its own database resource.
- **Storing the D1 database UUID in application source code** — the ID changes on replace. Always read it from Pulumi stack outputs or KV/secrets at deploy time.
- **Omitting `protect: true` on production** — a `pulumi destroy` or inadvertent resource replacement wipes all data. D1 has no automatic backup restore path via Pulumi.
- **Creating databases inside `pulumi.all().apply()`** — resource creation inside `.apply()` is an anti-pattern in Pulumi; it makes preview diffs unreliable. Create resources at the top level.

## Gotchas

- `cloudflare.D1Database` names must be unique per account, not just per stack. Prefix with stack name to avoid collisions.
- D1 database IDs are UUIDs assigned by Cloudflare. You cannot specify them; always reference via `db.id` output.
- `pulumi preview` shows the database as unchanged even after external data modifications — Pulumi tracks only resource configuration, not row data.
- The `@pulumi/cloudflare` provider may lag behind the Cloudflare Terraform provider in resource availability by weeks to months. Check the provider changelog before assuming a new Cloudflare feature is Pulumi-available.
- D1 is billed per database, not per query. Avoid programmatically creating thousands of tenant databases; prefer row-level tenancy with a single database for accounts with > 100 tenants.

## Verification

```bash
# Confirm stack outputs
pulumi stack output --stack staging

# Verify database exists in Cloudflare
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/d1/database" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq '.result[] | select(.name | startswith("app-staging"))'

# Run a test query against staging D1
wrangler d1 execute app-staging \
  --command "SELECT COUNT(*) as cnt FROM users" \
  --env staging

# Confirm Worker binding
wrangler worker get api-worker-staging --json | jq '.bindings[] | select(.type=="d1")'
```

## Related

- `terraform-cloudflare-provider-workers-d1.md` — Terraform equivalent for D1 provisioning
- `pulumi-cloudflare-workers-infrastructure-as-code.md` — general Pulumi Workers patterns
- `pulumi-cloudflare-provider-advanced.md` — provider configuration, ESC secrets
- `pulumi-esc-secrets-config-management.md` — managing API tokens and config per stack
- `hyperdrive-postgresql-pulumi-iac.md` — Pulumi-managed Hyperdrive alongside D1

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/api-docs/d1database/
- https://developers.cloudflare.com/d1/get-started/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://www.pulumi.com/docs/concepts/options/protect/
- https://www.pulumi.com/docs/concepts/stack/#stackreferences
