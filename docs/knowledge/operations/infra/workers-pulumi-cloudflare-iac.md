# Managing Cloudflare Workers Infrastructure with Pulumi (TypeScript)

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your team manually clicks through the Cloudflare dashboard or runs ad-hoc `wrangler` commands to deploy Workers, create KV namespaces, and attach D1 databases. There is no reproducible state, no diff preview before apply, and no audit trail. A new environment (staging, preview, canary) requires repeating all steps by hand.

## Context

Pulumi's `@pulumi/cloudflare` provider maps the full Cloudflare REST API surface to strongly-typed TypeScript resources. A `pulumi up` produces a plan diff, executes only the delta, and stores state in Pulumi Cloud (or self-hosted S3/R2). Secrets are encrypted at rest in the stack state and injected at deploy time — no plaintext in source control.

Key provider version: `@pulumi/cloudflare` ^5.x (wraps Cloudflare Terraform provider v4).

## Solution

### 1. Bootstrap a new Pulumi project

```bash
mkdir infra && cd infra
pulumi new typescript --name example project-infra --stack prod
npm install @pulumi/cloudflare @pulumi/pulumi
```

### 2. Authenticate

```bash
# Store as stack secrets — never as plain config
pulumi config set cloudflare:apiToken --secret   # scoped API token
pulumi config set cloudflare:accountId          # not secret, but handy
```

Create a scoped token in the Cloudflare dashboard with permissions:
- `Workers Scripts: Edit`
- `Workers KV Storage: Edit`
- `D1: Edit`
- `Zone: Read` (for custom domain)

### 3. Worker script resource

```typescript
// index.ts
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";
import * as fs from "fs";

const cfg = new pulumi.Config();
const accountId = cfg.require("cloudflareAccountId");
const zoneId   = cfg.require("zoneId");

// Read compiled worker bundle
const workerScript = new cloudflare.WorkerScript("api-worker", {
  accountId,
  name: `example project-api-${pulumi.getStack()}`,
  content: fs.readFileSync("../dist/worker.js", "utf-8"),
  module: true, // ES module format
  compatibilityDate: "2024-09-23",
  compatibilityFlags: ["nodejs_compat"],
});
```

### 4. KV namespace and binding

```typescript
const sessionKv = new cloudflare.WorkersKvNamespace("session-kv", {
  accountId,
  title: `example project-sessions-${pulumi.getStack()}`,
});

// Attach binding to the Worker
const workerScriptWithBindings = new cloudflare.WorkerScript("api-worker", {
  accountId,
  name: `example project-api-${pulumi.getStack()}`,
  content: fs.readFileSync("../dist/worker.js", "utf-8"),
  module: true,
  compatibilityDate: "2024-09-23",
  kvNamespaceBindings: [{
    name: "SESSION_STORE",         // env var name inside worker
    namespaceId: sessionKv.id,
  }],
});
```

### 5. D1 database

```typescript
const db = new cloudflare.D1Database("main-db", {
  accountId,
  name: `example project-db-${pulumi.getStack()}`,
});

// Reference in Worker bindings
// Add to WorkerScript resource:
d1DatabaseBindings: [{
  name: "DB",
  databaseId: db.id,
}],
```

### 6. Custom domain via Worker route

```typescript
// Workers route on an existing zone
const route = new cloudflare.WorkerRoute("api-route", {
  zoneId,
  pattern: `api.example.com/*`,
  scriptName: workerScriptWithBindings.name,
});

// OR use a Workers custom domain (no zone pattern needed)
const customDomain = new cloudflare.WorkerDomain("api-domain", {
  accountId,
  hostname: `api.example.com`,
  service:  workerScriptWithBindings.name,
  zoneId,
});
```

### 7. Stack secrets management

```typescript
// Read a stack secret and inject as Worker secret binding
const stripeKey = cfg.requireSecret("stripeSecretKey");

// Secret text bindings (encrypted at runtime, not visible in logs)
secretTextBindings: [{
  name: "STRIPE_SECRET_KEY",
  text: stripeKey,
}],
```

Set from CLI:
```bash
pulumi config set stripeSecretKey sk_live_xxx --secret
```

### 8. pulumi up in CI (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Pulumi Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install deps
        run: npm ci
        working-directory: infra

      - name: Build worker
        run: npm run build   # outputs dist/worker.js

      - name: Pulumi Up
        uses: pulumi/actions@v5
        with:
          command: up
          stack-name: example-org/example-repo/prod
          work-dir: infra
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Implementation Details

- Pulumi stores the state graph in Pulumi Cloud or an S3/R2 backend. For R2: `pulumi login s3://my-bucket?endpoint=https://ACCOUNT.r2.cloudflarestorage.com`.
- `WorkerScript.content` must be the fully bundled output. Use `esbuild` or `wrangler build` as a pre-step.
- `module: true` is required for ES module Workers; omit for Service Worker format.
- `compatibilityDate` advances the Workers runtime feature set. Pin it per-stack and bump intentionally.
- Each Pulumi stack maps to one deployment environment. Stack config (`Pulumi.prod.yaml`, `Pulumi.staging.yaml`) holds per-env values.
- `pulumi preview` in PRs gives a safe diff before merge; wire it to a GitHub status check.

## Anti-patterns

- Do not store API tokens in `pulumi config` without `--secret`. They appear in the diff output.
- Do not share a single Worker name across stacks — Cloudflare names are global within the account; use `${pulumi.getStack()}` suffix.
- Do not import existing manually-created resources on day one without a plan; `pulumi import` can cause destructive diffs if resource attributes differ.
- Do not run `pulumi up` directly from a PR branch without `--expect-to-not-create-replacement` guards on production stacks.
- Do not use `cloudflare.WorkerRoute` and `cloudflare.WorkerDomain` on the same hostname — they conflict.

## Gotchas

- Cloudflare's API rate limits apply during `pulumi up`. With many resources, add `--parallel 1` to serialise calls.
- `D1Database` provisioning is async on Cloudflare's side; Pulumi marks it done after the API 200, but the DB may take ~10 s to be queryable.
- KV namespace IDs are stable after creation. If you delete and recreate a namespace, all data is lost — protect with `pulumi.protect: true`.
- `WorkerScript` replaces (not updates) when `name` changes; old script keeps serving until the new one is attached to a route.
- Pulumi v3 `@pulumi/cloudflare` v5 renamed several resource types from v4. Check the migration guide when upgrading.

## Verification

```bash
# Dry-run diff
pulumi preview --diff

# Check deployed worker
curl -s https://api.example.com/healthz | jq .

# Confirm KV binding
wrangler kv:namespace list

# Confirm D1
wrangler d1 info example project-db-prod

# Stack outputs
pulumi stack output
```

## Related

- `documentation/docs/policies/infra/workers-cdn-cache-purge-api.md`
- `documentation/docs/policies/infra/workers-log-drain-r2-archival.md`
- Wrangler IaC alternative: `wrangler.toml` + `wrangler deploy`

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/
- https://developers.cloudflare.com/workers/wrangler/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
