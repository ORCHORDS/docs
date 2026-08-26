# Workers for Platforms Dispatch Namespace Deployment

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
SaaS platforms that let customers deploy custom serverless logic need a way to upload, version, and route tenant Workers without provisioning a separate Cloudflare account per tenant or exposing account-level credentials to customers.

## Context
Workers for Platforms (WfP) introduces two primitives: a dispatch namespace (a shared pool of named Workers) and a dynamic dispatch binding (`DispatchNamespace`). A "user Worker" is uploaded to the namespace via the Cloudflare REST API and is invisible to standard `wrangler deploy` flows. A "dispatcher Worker" — owned by the platform — receives incoming requests, resolves the tenant identifier, and calls `dispatchNamespace.get(tenantId)` to route to the correct user Worker. This pattern is used for code execution sandboxes, custom webhook handlers, and per-tenant API middleware.

## Platform Dispatcher Worker

```typescript
// platform/src/dispatcher.ts
export interface Env {
  CUSTOMER_WORKERS: DispatchNamespace;
  DB: D1Database;
}

interface TenantRecord {
  tenant_id: string;
  worker_script_name: string;
  enabled: number;
}

async function resolveTenantScript(
  hostname: string,
  env: Env
): Promise<string | null> {
  const row = await env.DB.prepare(
    "SELECT tenant_id, worker_script_name, enabled FROM tenants WHERE hostname = ? LIMIT 1"
  )
    .bind(hostname)
    .first<TenantRecord>();

  if (!row || !row.enabled) return null;
  return row.worker_script_name;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const hostname = new URL(request.url).hostname;
    const scriptName = await resolveTenantScript(hostname, env);

    if (!scriptName) {
      return new Response("Tenant not found or disabled", { status: 404 });
    }

    try {
      const userWorker = env.CUSTOMER_WORKERS.get(scriptName, {
        outbound: {
          service: "outbound-filter",
          environment: "production",
        },
      });
      return await userWorker.fetch(request);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(JSON.stringify({ error: message, scriptName, hostname }));
      return new Response("Worker execution error", { status: 502 });
    }
  },
};
```

## Platform wrangler.toml

```toml
# platform/wrangler.toml
name = "orchords-platform-dispatcher"
main = "src/dispatcher.ts"
compatibility_date = "2026-08-01"

[[dispatch_namespaces]]
binding = "CUSTOMER_WORKERS"
namespace = "orchords-tenants"

[[d1_databases]]
binding = "DB"
database_name = "orchords-platform"
database_id = "platform-d1-database-id"

[[services]]
binding = "outbound-filter"
service = "orchords-outbound-filter"
environment = "production"
```

## Uploading Tenant Workers via REST API

Tenant Workers are deployed through the Accounts API, not Wrangler. This flow is called from your platform's backend on each tenant code-save event.

```typescript
// platform/src/services/tenant-deploy.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const NAMESPACE = "orchords-tenants";

interface DeployTenantOptions {
  scriptName: string;
  scriptContent: string;
  compatibilityDate?: string;
  bindings?: Array<{ type: string; name: string; [key: string]: unknown }>;
}

export async function deployTenantWorker(opts: DeployTenantOptions): Promise<void> {
  const {
    scriptName,
    scriptContent,
    compatibilityDate = "2026-08-01",
    bindings = [],
  } = opts;

  const metadata = {
    main_module: "worker.js",
    compatibility_date: compatibilityDate,
    bindings,
  };

  const form = new FormData();
  form.append(
    "metadata",
    new Blob([JSON.stringify(metadata)], { type: "application/json" }),
    "metadata.json"
  );
  form.append(
    "worker.js",
    new Blob([scriptContent], { type: "application/javascript+module" }),
    "worker.js"
  );

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${scriptName}`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
      body: form,
    }
  );

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Tenant deploy failed [${resp.status}]: ${body}`);
  }

  console.log(`Deployed tenant worker: ${scriptName}`);
}

export async function deleteTenantWorker(scriptName: string): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${scriptName}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
    }
  );
  if (!resp.ok && resp.status !== 404) {
    throw new Error(`Delete failed [${resp.status}]: ${await resp.text()}`);
  }
  console.log(`Deleted tenant worker: ${scriptName}`);
}
```

## Tenant Script Validation Before Upload

Run a validation step to catch obviously broken tenant scripts before they reach the namespace.

```typescript
// platform/src/services/tenant-validate.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;

export async function validateTenantScript(scriptContent: string): Promise<{
  valid: boolean;
  errors: string[];
}> {
  // Use the Workers script validation endpoint (dry-run compile)
  const form = new FormData();
  const metadata = { main_module: "worker.js", compatibility_date: "2026-08-01" };
  form.append(
    "metadata",
    new Blob([JSON.stringify(metadata)], { type: "application/json" }),
    "metadata.json"
  );
  form.append(
    "worker.js",
    new Blob([scriptContent], { type: "application/javascript+module" }),
    "worker.js"
  );

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/__validate`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
      body: form,
    }
  );

  const json = (await resp.json()) as {
    success: boolean;
    errors: Array<{ message: string }>;
  };

  return {
    valid: json.success,
    errors: json.errors?.map((e) => e.message) ?? [],
  };
}
```

## Namespace Provisioning Script

Provision the dispatch namespace once per environment; do not recreate it on each deploy.

```bash
#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-orchords-tenants}"
ACCOUNT_ID="${CF_ACCOUNT_ID:?CF_ACCOUNT_ID must be set}"
API_TOKEN="${CF_API_TOKEN:?CF_API_TOKEN must be set}"

echo "Creating dispatch namespace: $NAMESPACE"
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/dispatch/namespaces" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$NAMESPACE\"}" | jq '.result'

echo "Deploying platform dispatcher..."
npx wrangler deploy --config platform/wrangler.toml
```

## Anti-patterns
- Using `wrangler deploy` to upload tenant Workers — it targets your default namespace, not the dispatch namespace
- Granting tenants direct Cloudflare API access — they must deploy through your platform's validated upload endpoint
- Skipping the validation step — an invalid tenant script silently returns 502 from the dispatcher
- Reusing the same `scriptName` for different tenants — namespace script names must be globally unique within the namespace
- Storing tenant scripts as raw strings in D1 — use R2 for script storage and pass presigned download URLs to the deploy service

## Gotchas
- Dispatch namespace Workers do not appear in the standard Workers dashboard list; they are only visible under the namespace view
- `dispatchNamespace.get()` is synchronous in type but the returned stub's `.fetch()` is async and can throw on cold starts or missing scripts
- Tenant Workers in a namespace inherit the namespace's compatibility date unless the upload metadata overrides it
- Outbound service bindings on the dispatcher Worker do not automatically apply to tenant Workers unless explicitly configured per-namespace
- Deleting a namespace with active tenant Workers is immediate and non-recoverable; scripts are not archived

## Verification
```bash
# List all scripts in the dispatch namespace
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/dispatch/namespaces/orchords-tenants/scripts" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '[.result[] | .id]'

# Test routing through the dispatcher
curl -s -H "Host: tenant-a.example.com" \
  "https://orchords-platform-dispatcher.orchords-platform-dispatcher.workers.dev/"

# Check script exists before routing
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/dispatch/namespaces/orchords-tenants/scripts/tenant-a-worker" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.success'
```

## Related
- `workers-service-bindings-deployment-ordering.md`
- `workers-binding-version-management.md`
- `serverless-deploy-cloudflare-workers.md`
- `multi-tenant-routing-patterns.md`

## Sources
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
- https://developers.cloudflare.com/api/operations/namespace-worker-script-upload-worker-module
