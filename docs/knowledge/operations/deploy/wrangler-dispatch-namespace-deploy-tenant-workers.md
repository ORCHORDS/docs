# Wrangler Dispatch Namespace Deploy for Multi-Tenant Workers

- **Date:** 2026-08-24
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your SaaS platform lets customers deploy custom Worker logic. You need a CI pipeline that builds each tenant's Worker bundle, validates it, and deploys it into a shared dispatch namespace using the `wrangler` CLI — without granting tenants access to your Cloudflare account or maintaining per-tenant `wrangler.toml` files.

---

## Context

Cloudflare Workers for Platforms exposes a `dispatch-namespace` concept: a named pool of Workers uploaded under your account that are invisible to `wrangler deploy` default flows. Since Wrangler v3.40, the flag `--dispatch-namespace <name>` on `wrangler deploy` targets these namespaces directly from CI without a REST API client. Each tenant Worker lives at a logical name inside the namespace (`<namespace>/<script-name>`). The dispatcher Worker — your platform's entry point — resolves requests to the correct tenant script via the `DispatchNamespace` binding.

This article covers the wrangler CLI-driven pipeline for creating namespaces, deploying tenant Workers into them, and validating the deployment, distinct from direct REST API upload patterns.

---

## 1. Create and List Dispatch Namespaces via Wrangler

```bash
# Create the namespace once (idempotent in scripts — use || true)
wrangler dispatch-namespace create my-platform-tenants || true

# List all namespaces to verify
wrangler dispatch-namespace list
# Output:
# NAME                    NAMESPACE_ID
# my-platform-tenants     <uuid>

# Retrieve a specific namespace
wrangler dispatch-namespace get my-platform-tenants
```

Store the namespace name in CI environment variables, not hardcoded in `wrangler.toml`.

---

## 2. Tenant Worker `wrangler.toml` Template

Each tenant bundle shares a template configuration. The `--dispatch-namespace` flag overrides the deployment target at CI time, so the toml needs only the build config:

```toml
# tenant-template/wrangler.toml
name = "TENANT_PLACEHOLDER"        # overridden by --name at deploy time
main = "dist/index.js"
compatibility_date = "2026-07-01"
compatibility_flags = ["nodejs_compat"]

[build]
command = "npm run build"

# No routes, no domains — the dispatcher Worker handles routing
```

No per-tenant `wrangler.toml` is committed to source control. The CI pipeline injects the tenant ID at deploy time.

---

## 3. GitHub Actions: Per-Tenant Deployment Job

```yaml
# .github/workflows/tenant-deploy.yml
name: Deploy Tenant Worker

on:
  repository_dispatch:
    types: [tenant-deploy]
  workflow_dispatch:
    inputs:
      tenant_id:
        description: "Tenant slug (e.g. acme-corp)"
        required: true
      namespace:
        description: "Dispatch namespace name"
        required: true
        default: "my-platform-tenants"

jobs:
  deploy-tenant:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # OIDC for Cloudflare

    steps:
      - uses: actions/checkout@v4
        with:
          # Tenant code lives in a private submodule or artifact
          path: tenant-src

      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: tenant-src/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: tenant-src

      - name: Build tenant Worker
        run: npm run build
        working-directory: tenant-src

      - name: Validate bundle size
        run: |
          BUNDLE_SIZE=$(stat -c%s tenant-src/dist/index.js)
          MAX_SIZE=$((1 * 1024 * 1024))  # 1 MB Workers script limit
          if [ "$BUNDLE_SIZE" -gt "$MAX_SIZE" ]; then
            echo "Bundle too large: ${BUNDLE_SIZE} bytes (max ${MAX_SIZE})"
            exit 1
          fi
          echo "Bundle size OK: ${BUNDLE_SIZE} bytes"

      - name: Deploy to dispatch namespace
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_DISPATCH_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          TENANT_ID: ${{ github.event.inputs.tenant_id || github.event.client_payload.tenant_id }}
          NAMESPACE: ${{ github.event.inputs.namespace || github.event.client_payload.namespace }}
        run: |
          npx wrangler deploy \
            --name "$TENANT_ID" \
            --dispatch-namespace "$NAMESPACE" \
            --compatibility-date "2026-07-01" \
            --no-bundle
        working-directory: tenant-src
```

---

## 4. Minimal-Scope API Token for Dispatch Deployment

```typescript
// scripts/create-dispatch-token.ts
// Run once to document the required token scopes.
// In Cloudflare dashboard: API Tokens → Create Token → Custom Token

const REQUIRED_PERMISSIONS = [
  // Workers Scripts: Edit — required for wrangler deploy --dispatch-namespace
  "workers_scripts:edit",
  // Workers for Platforms: Edit — required to write into a namespace
  "workers_for_platforms:edit",
  // Account Settings: Read — required by wrangler for account resolution
  "account_settings:read",
] as const;

// The token must be scoped to:
//   Account Resources: Include → <your account>
//   Zone Resources: Include → All zones (or None if no routes)
console.log("Required scopes:", REQUIRED_PERMISSIONS);
```

Use a dedicated token with `workers_for_platforms:edit` — the standard `workers_scripts:edit` alone is insufficient for namespace uploads.

---

## 5. Dispatcher Worker: Routing to Namespace Scripts

```typescript
// platform/src/dispatcher.ts
export interface Env {
  TENANT_NAMESPACE: DispatchNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // Extract tenant from subdomain: acme-corp.your-platform.com
    const tenantId = url.hostname.split(".")[0];

    if (!tenantId || tenantId === "www") {
      return new Response("Tenant not found", { status: 404 });
    }

    try {
      const tenantWorker = env.TENANT_NAMESPACE.get(tenantId, {
        outbound: {
          // Pass platform context to tenant Worker via outbound binding
          params: { platformVersion: "2026-08", tenantId },
        },
      });
      return await tenantWorker.fetch(request);
    } catch (err: unknown) {
      if (err instanceof Error && err.message.includes("does not exist")) {
        return new Response(`Tenant '${tenantId}' is not deployed`, {
          status: 502,
        });
      }
      throw err;
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 6. Verify Deployment via Wrangler List

```bash
#!/usr/bin/env bash
# scripts/verify-tenant-deploy.sh
set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace> <tenant_id>}"
TENANT_ID="${2:?Usage: $0 <namespace> <tenant_id>}"

echo "Verifying tenant '$TENANT_ID' in namespace '$NAMESPACE'..."

DEPLOYED=$(
  wrangler dispatch-namespace get "$NAMESPACE" 2>/dev/null \
  | jq -r ".scripts[] | select(.id == \"$TENANT_ID\") | .id" 2>/dev/null || true
)

if [ -z "$DEPLOYED" ]; then
  echo "ERROR: Tenant '$TENANT_ID' not found in namespace '$NAMESPACE'"
  exit 1
fi

echo "OK: Tenant '$TENANT_ID' is deployed in namespace '$NAMESPACE'"
```

---

## Anti-patterns

- **Granting tenants `workers_scripts:edit`** — they can overwrite other tenants' scripts. Use a platform-controlled CI pipeline for all namespace uploads.
- **One namespace per tenant** — namespaces have limits; one namespace for all tenants scales better. Isolate tenants by script name within a single namespace.
- **Hardcoding `--dispatch-namespace` in `wrangler.toml`** — makes it impossible to test locally without a namespace. Pass the flag at CI deploy time.
- **Skipping bundle validation** — a 10 MB tenant bundle will fail at the Cloudflare API with a cryptic 413 error. Validate size before invoking wrangler.

---

## Gotchas

- `wrangler deploy --dispatch-namespace` requires **Wrangler v3.40+**. Earlier versions only support namespace management via REST API.
- Dispatch namespace scripts do **not** support `cron` triggers, `routes`, or `custom_domains`. The dispatcher Worker owns all ingress.
- Deleting a tenant script from the namespace does not affect traffic immediately if the dispatcher has cached the `DispatchNamespace.get()` result. Add a cache-busting query param or use `waitUntil` to purge.
- The `--name` flag passed to `wrangler deploy` sets the script name inside the namespace, not the account-level Worker name. Both can coexist with the same slug.

---

## Verification

```bash
# 1. Confirm namespace exists
wrangler dispatch-namespace get my-platform-tenants

# 2. Confirm tenant script is listed (requires jq)
wrangler dispatch-namespace get my-platform-tenants | jq '.scripts | length'

# 3. Send a test request through the dispatcher Worker
curl -s -o /dev/null -w "%{http_code}" \
  https://acme-corp.your-platform.com/health

# 4. Tail dispatcher logs to see routing decisions
wrangler tail platform-dispatcher --format=pretty
```

---

## Related

- `workers-for-platforms-dispatch-namespace-deploy.md` — REST API approach to tenant Worker uploads
- `workers-for-platforms-tenant-isolation-deploy.md` — tenant isolation patterns
- `wrangler-api-token-minimum-scope-production-deploy.md` — minimum token scopes for CI
- `workers-service-bindings-deployment-ordering.md` — service binding ordering when dispatcher depends on other Workers

---

## Sources

- Cloudflare Docs — Workers for Platforms: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Cloudflare Docs — wrangler dispatch-namespace: https://developers.cloudflare.com/workers/wrangler/commands/#dispatch-namespace
- Cloudflare Docs — DispatchNamespace binding: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
