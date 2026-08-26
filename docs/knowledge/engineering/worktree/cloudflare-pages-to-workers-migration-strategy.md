# Cloudflare Pages to Workers Migration Strategy

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A Cloudflare Pages project has outgrown Pages' routing and middleware limitations and needs to migrate to a full Cloudflare Worker with `wrangler deploy`, retaining existing preview deployments, custom domains, and D1/KV bindings without downtime.

## Context
Cloudflare Pages Functions are Workers under the hood, but they are provisioned and deployed via the Pages platform, which has its own git integration, deploy hooks, and binding configuration in the dashboard. Workers deployed via `wrangler deploy` offer a superset of capabilities: Durable Objects, Queues, tail Workers, fine-grained cron triggers, and `wrangler.toml`-controlled environments. The migration path is additive — the Pages project remains live until the Worker is promoted behind the same custom domain, allowing gradual traffic shifting with zero-downtime cutover.

## Audit Existing Pages Project
```bash
# List all Pages projects and their settings
pnpm wrangler pages project list

# Show bindings for the project
pnpm wrangler pages project get my-app

# Export current Pages Functions source to inspect
# Pages Functions live in /functions directory by convention
ls -la functions/
```

```typescript
// scripts/audit-pages-bindings.ts
// Reads wrangler.toml-equivalent data from the Pages dashboard via REST
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

interface PagesBinding {
  name: string;
  type: "kv_namespace" | "d1_database" | "r2_bucket" | "service";
  id?: string;
}

async function fetchPagesBindings(projectName: string): Promise<PagesBinding[]> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${projectName}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${API_TOKEN}` },
  });
  const json = (await res.json()) as { result: { deployment_configs: unknown } };
  console.dir(json.result.deployment_configs, { depth: 4 });
  return [];
}

await fetchPagesBindings("my-app");
```

## Scaffold the Target wrangler.toml
```toml
# wrangler.toml — generated from Pages binding audit
name = "my-app"
main = "src/index.ts"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

# Assets (replaces Pages' static asset handling)
[assets]
directory = "dist"
binding = "ASSETS"

# Recreate KV bindings from Pages dashboard
[[kv_namespaces]]
binding = "SESSIONS"
id = "aaaa1111bbbb2222cccc3333dddd4444"

# Recreate D1 bindings
[[d1_databases]]
binding = "DB"
database_name = "my-app-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Recreate R2 bindings
[[r2_buckets]]
binding = "UPLOADS"
bucket_name = "my-app-uploads"

[env.staging]
name = "my-app-staging"
[[env.staging.kv_namespaces]]
binding = "SESSIONS"
id = "eeee5555ffff6666aaaa7777bbbb8888"
[[env.staging.d1_databases]]
binding = "DB"
database_name = "my-app-staging"
database_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

## Migrating the Request Handler
```typescript
// src/index.ts — Worker entrypoint replacing Pages Functions
import { Hono } from "hono";

export interface Env {
  ASSETS: Fetcher;
  SESSIONS: KVNamespace;
  DB: D1Database;
  UPLOADS: R2Bucket;
}

const app = new Hono<{ Bindings: Env }>();

// Replicate Pages _middleware.ts logic
app.use("*", async (c, next) => {
  const token = c.req.header("CF-Access-Authenticated-User-Email");
  if (token) c.set("userEmail" as never, token);
  await next();
});

// Replicate Pages Functions routes from /functions/**/*.ts
app.get("/api/health", (c) => c.json({ ok: true }));

app.get("/api/user/:id", async (c) => {
  const user = await c.env.DB.prepare("SELECT * FROM users WHERE id = ?")
    .bind(c.req.param("id"))
    .first();
  if (!user) return c.notFound();
  return c.json(user);
});

// Fall through to static assets (replaces Pages' automatic asset serving)
app.get("*", async (c) => {
  return c.env.ASSETS.fetch(c.req.raw);
});

export default app;
```

## GitHub Actions: Parallel Deploy During Migration
```yaml
# .github/workflows/migrate-deploy.yml
# Deploys both Pages (legacy) and Worker (new) in parallel during migration period
name: Migration Deploy

on:
  push:
    branches: [main]

jobs:
  deploy-pages:
    runs-on: ubuntu-latest
    if: vars.PAGES_MIGRATION_COMPLETE != 'true'
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 10
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm build
      - name: Deploy to Pages (legacy)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler pages deploy dist --project-name my-app

  deploy-worker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 10
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm build
      - name: Deploy Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler deploy

      - name: Smoke test Worker
        run: |
          sleep 5
          curl -sf https://my-app-worker.orchords.workers.dev/api/health \
            | jq -e '.ok == true'
```

## DNS Cutover Script
```typescript
// scripts/cutover-dns.ts
// Moves the custom domain record from Pages to the Worker
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const ZONE_ID = process.env.CF_ZONE_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;
const DOMAIN = "app.example.com";
const WORKER_NAME = "my-app";

async function cf(path: string, body?: unknown) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4${path}`,
    {
      method: body ? "POST" : "GET",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    }
  );
  return res.json();
}

// Add the custom domain to the Worker route
const route = await cf(`/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/routes`, {
  pattern: DOMAIN + "/*",
  zone_id: ZONE_ID,
});
console.log("Route added:", route);
```

## Anti-patterns
- Deleting the Pages project before verifying the Worker serves all routes correctly — Pages is the live origin until the DNS cutover completes
- Copying `/functions/_middleware.ts` verbatim into the Worker without adapting to Hono/`addEventListener` request lifecycle — middleware execution order differs
- Forgetting to migrate `_headers` and `_redirects` files — these are Pages-specific; in a Worker, implement them as middleware or `wrangler.toml` route rules
- Using `CLOUDFLARE_ACCOUNT_ID` as an environment variable in the Worker code — this is a build-time CI variable, not a runtime binding

## Gotchas
- Pages and Workers share the KV and D1 namespaces when the same binding IDs are configured, but the bindings must be re-declared in `wrangler.toml` — they are not automatically inherited
- The `CF-Connecting-IP` and `CF-Ray` headers behave identically, but `CF-Access-*` headers require the same Access policy to be applied to the Worker route
- Cloudflare Workers Sites (legacy `wrangler.toml` `[site]` key) is a different migration path from Pages — do not confuse it with the `[assets]` binding used in Workers Assets
- Preview deployments in Pages are per-branch; in Workers, achieve the same with `--env preview` and a branch-named environment in `wrangler.toml`

## Verification
```bash
# Smoke test the Worker before DNS cutover
curl -sf https://my-app.orchords.workers.dev/api/health

# Compare Pages vs Worker response headers
diff \
  <(curl -sI https://my-app.pages.dev/api/health) \
  <(curl -sI https://my-app.orchords.workers.dev/api/health)

# After cutover, confirm Pages is no longer serving traffic
pnpm wrangler pages deployment list --project-name my-app | head -5
pnpm wrangler deployments list | head -5
```

## Related
- `/documentation/docs/policies/worktree/wrangler-environments-staging-production.md`
- `/documentation/docs/policies/worktree/github-actions-wrangler-deploy-pipeline.md`
- `/documentation/docs/policies/worktree/trunk-based-development-cloudflare-workers.md`
- `/documentation/docs/policies/worktree/git-branching-cloudflare-preview-environments.md`
- `/documentation/docs/policies/worktree/workers-d1-migration-ci-pipeline.md`

## Sources
- https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/
- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/configuration/routing/routes/
