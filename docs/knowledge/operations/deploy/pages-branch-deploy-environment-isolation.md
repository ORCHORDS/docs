# Pages Branch Deploy Environment Isolation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Preview deployments on feature branches read from the same KV namespace and D1 database as production, causing test writes to corrupt live data and preview secrets to share production credentials. A PR that runs migrations against a shared staging DB wipes other developers' preview data. You need each branch environment to be fully isolated — separate KV, D1, and secrets per branch — with clean-up on PR close.

## Context

Cloudflare Pages preview deployments are automatically created for every push to a non-production branch. By default, all preview deployments share the bindings declared in the Pages project's "Preview" environment configuration — there is no per-branch binding scoping built into the platform. True isolation requires: (1) per-branch KV namespaces provisioned dynamically, (2) per-branch D1 databases seeded from migrations, (3) branch-specific secrets injected via the Cloudflare API, and (4) a teardown routine when the branch is deleted or the PR is closed. This is achieved by combining GitHub Actions PR lifecycle events with the Cloudflare REST API for Pages project binding management.

## 1. Provision Script — KV Namespace Per Branch

```typescript
// scripts/provision-branch-env.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const PAGES_PROJECT = process.env.PAGES_PROJECT!;
const BRANCH = process.env.BRANCH_NAME!; // e.g. "feat/payments"
const SAFE_BRANCH = BRANCH.replace(/[^a-z0-9]/gi, "-").toLowerCase().slice(0, 40);

async function cf(method: string, path: string, body?: unknown): Promise<unknown> {
  const res = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
    method,
    headers: { Authorization: `Bearer ${CF_API_TOKEN}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json() as { success: boolean; result: unknown; errors: { message: string }[] };
  if (!json.success) throw new Error(json.errors.map(e => e.message).join(", "));
  return json.result;
}

// Create isolated KV namespace for this branch
const kv = await cf("POST", `/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces`, {
  title: `preview-${SAFE_BRANCH}-cache`,
}) as { id: string };
console.log(`KV namespace created: ${kv.id}`);
```

## 2. Provision Script — D1 Database Per Branch

```typescript
// Continuing scripts/provision-branch-env.ts
import { execSync } from "child_process";

const d1 = await cf("POST", `/accounts/${CF_ACCOUNT_ID}/d1/database`, {
  name: `preview-${SAFE_BRANCH}-db`,
}) as { uuid: string };
console.log(`D1 database created: ${d1.uuid}`);

// Apply migrations to the fresh preview database
execSync(
  `npx wrangler d1 migrations apply --database-id ${d1.uuid} --remote`,
  { stdio: "inherit", env: { ...process.env } }
);

// Bind both resources to the Pages project's preview environment
await cf("PATCH", `/accounts/${CF_ACCOUNT_ID}/pages/projects/${PAGES_PROJECT}`, {
  deployment_configs: {
    preview: {
      kv_namespaces: { CACHE: { namespace_id: kv.id } },
      d1_databases: { DB: { id: d1.uuid } },
    },
  },
});
console.log("Preview bindings updated.");
```

## 3. Branch-Specific Secrets via Pages API

```typescript
// scripts/set-branch-secrets.ts — inject non-production credentials per branch
const previewSecrets: Record<string, string> = {
  STRIPE_SECRET_KEY: process.env.STRIPE_TEST_KEY!,
  AUTH_SECRET: crypto.randomUUID(), // unique per branch — prevents session sharing
  SENDGRID_API_KEY: process.env.SENDGRID_SANDBOX_KEY!,
};

await cf("PATCH", `/accounts/${CF_ACCOUNT_ID}/pages/projects/${PAGES_PROJECT}`, {
  deployment_configs: {
    preview: {
      env_vars: Object.fromEntries(
        Object.entries(previewSecrets).map(([k, v]) => [k, { type: "secret_text", value: v }])
      ),
    },
  },
});
console.log("Preview secrets configured.");
```

## 4. Teardown Script — Delete Resources on PR Close

```typescript
// scripts/teardown-branch-env.ts
const namespaces = await cf(
  "GET", `/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces`
) as { id: string; title: string }[];

const toDelete = namespaces.filter(ns => ns.title === `preview-${SAFE_BRANCH}-cache`);
for (const ns of toDelete) {
  await cf("DELETE", `/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${ns.id}`);
  console.log(`Deleted KV namespace: ${ns.id}`);
}

const dbs = await cf(
  "GET", `/accounts/${CF_ACCOUNT_ID}/d1/database`
) as { uuid: string; name: string }[];

const dbToDelete = dbs.find(d => d.name === `preview-${SAFE_BRANCH}-db`);
if (dbToDelete) {
  await cf("DELETE", `/accounts/${CF_ACCOUNT_ID}/d1/database/${dbToDelete.uuid}`);
  console.log(`Deleted D1 database: ${dbToDelete.uuid}`);
}
```

## 5. GitHub Actions Orchestration

```yaml
# .github/workflows/preview-env.yml
on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

jobs:
  provision:
    if: github.event.action != 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npx tsx scripts/provision-branch-env.ts
        env:
          BRANCH_NAME: ${{ github.head_ref }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN_PAGES }}
          PAGES_PROJECT: ${{ vars.PAGES_PROJECT_NAME }}
          STRIPE_TEST_KEY: ${{ secrets.STRIPE_TEST_KEY }}
          SENDGRID_SANDBOX_KEY: ${{ secrets.SENDGRID_SANDBOX_KEY }}

  teardown:
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npx tsx scripts/teardown-branch-env.ts
        env:
          BRANCH_NAME: ${{ github.head_ref }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN_PAGES }}
```

## Anti-patterns

- Sharing the production KV namespace with all preview environments — test writes pollute live session and cache data.
- Sharing a production or staging D1 with previews — schema migrations in a PR run against the shared database, potentially breaking other developers.
- Relying on environment variable prefixes (`PREVIEW_STRIPE_KEY`) instead of binding isolation — a misconfigured Worker can still reach production resources through the wrong variable.
- Never running teardown — orphaned D1 databases and KV namespaces accumulate unbounded; at scale this creates both cost and a compliance audit surface.

## Gotchas

- The Pages API `PATCH` for `deployment_configs.preview` is **project-wide**, not branch-specific — all previews share the same preview binding configuration. True per-branch isolation at the routing layer requires a dispatch Worker that injects branch context at runtime or a Pages Plugin that swaps bindings based on the `CF_PAGES_BRANCH` environment variable.
- D1 database provisioning takes several seconds; add a polling loop before running migrations to avoid a "database not ready" error.
- KV namespace titles must be unique per account — include the PR number or a short hash to handle fast branch churn with similar names.
- Secrets set via the Pages API take effect on the **next triggered deployment**, not immediately; trigger a redeploy after the provision step if time-sensitive.
- Branch names with slashes (`feat/payments`) must be sanitised before use as resource name components — the API rejects names with `/`.

## Verification

```bash
# List preview KV namespaces
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces" \
  | jq '[.result[] | select(.title | startswith("preview-"))]'

# Check Pages project current preview bindings
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PAGES_PROJECT" \
  | jq '.result.deployment_configs.preview | {kv_namespaces, d1_databases}'
```

## Related

- `cloudflare-pages-branch-deploy-preview-d1-seeding.md`
- `cloudflare-pages-preview-deployments.md`
- `pages-preview-deployment-cleanup-automation.md`
- `d1-schema-migration-sequencing-wrangler-remote.md`
- `pages-functions-env-var-management.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/branch-build-controls/
- https://developers.cloudflare.com/pages/functions/bindings/
- https://developers.cloudflare.com/api/resources/pages/subresources/projects/methods/edit/
- https://developers.cloudflare.com/d1/build-with-d1/local-development/
