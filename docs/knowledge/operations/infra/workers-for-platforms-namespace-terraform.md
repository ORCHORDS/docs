# Workers for Platforms Namespace Terraform Provisioning

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You are building a multi-tenant SaaS on Cloudflare where each customer gets their own isolated
Worker script. Managing dispatch namespaces by hand in the dashboard does not scale past a handful
of tenants. You need Terraform to provision the dispatch namespace, set default and fallback
handlers, and emit the namespace binding needed by your router Worker.

## Context

Workers for Platforms (WfP) lets one "dispatch" Worker route requests to user-uploaded scripts
living in a namespace. The platform owner manages:

- The **dispatch namespace** (provisioned via API / Terraform).
- The **dispatch Worker** (the router) which calls `env.DISPATCH_NAMESPACE.get(scriptName)`.
- Customer Workers uploaded via the WfP Upload API.

Terraform covers the first two; customer script upload happens at runtime through the WfP API or
a dedicated onboarding Worker. The Cloudflare provider `cloudflare_workers_for_platforms_namespace`
resource is available from provider ≥ 4.20.

---

## 1. Dispatch Namespace Resource

```hcl
# namespace.tf
variable "cloudflare_account_id" { type = string }

resource "cloudflare_workers_for_platforms_namespace" "platform" {
  account_id = var.cloudflare_account_id
  name       = "my-saas-platform"
}

output "namespace_name" {
  value = cloudflare_workers_for_platforms_namespace.platform.name
}
```

The `name` is the binding identifier used in `wrangler.toml` and in Terraform `worker_script`
resources. Choose a name that is stable across environments (e.g. `platform-prod`,
`platform-staging`) because renaming requires destroy-and-recreate.

---

## 2. Dispatch Worker Script

```hcl
# dispatch-worker.tf
resource "cloudflare_workers_script" "dispatch" {
  account_id = var.cloudflare_account_id
  name       = "platform-dispatcher"
  content    = file("${path.module}/dist/dispatcher.js")

  dispatch_namespace_binding {
    name      = "DISPATCH_NAMESPACE"
    namespace = cloudflare_workers_for_platforms_namespace.platform.name
  }

  kv_namespace_binding {
    name         = "TENANT_MAP"
    namespace_id = cloudflare_cloudflare_workers_kv_namespace.tenant_map.id
  }
}
```

---

## 3. Dispatcher Worker Logic

```typescript
// src/dispatcher.ts
interface Env {
  DISPATCH_NAMESPACE: DispatchNamespace;
  TENANT_MAP: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const hostname = new URL(request.url).hostname;
    // e.g. "tenant-abc.platform.example.com" -> "tenant-abc"
    const tenantId = await env.TENANT_MAP.get(`host:${hostname}`);

    if (!tenantId) {
      return new Response("Unknown tenant", { status: 404 });
    }

    // Retrieve the customer's script from the namespace
    const userWorker = env.DISPATCH_NAMESPACE.get(tenantId, {
      outbound: {
        // Optionally call an outbound Worker for egress policy enforcement
        service: { name: "platform-outbound-policy" },
      },
    });

    return userWorker.fetch(request);
  },
};
```

---

## 4. Outbound Policy Worker

```hcl
# outbound-policy.tf
resource "cloudflare_workers_script" "outbound_policy" {
  account_id = var.cloudflare_account_id
  name       = "platform-outbound-policy"
  content    = file("${path.module}/dist/outbound-policy.js")
}
```

```typescript
// src/outbound-policy.ts
// Called for every subrequest made by tenant Workers
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const blocked = ["internal.example.com", "169.254.169.254"];

    if (blocked.some((h) => url.hostname.endsWith(h))) {
      return new Response("Blocked by platform policy", { status: 403 });
    }
    return fetch(request);
  },
};
```

---

## 5. CI Tenant Onboarding via WfP Upload API

After Terraform provisions the namespace, tenant scripts are uploaded at runtime — not via
Terraform, because each customer's code is unknown at plan time.

```typescript
// platform-api/src/onboard.ts
const CF_ACCOUNT = process.env.CF_ACCOUNT_ID!;
const CF_TOKEN   = process.env.CF_API_TOKEN!;
const NAMESPACE  = process.env.WFP_NAMESPACE!;  // from Terraform output

export async function uploadTenantScript(
  tenantId: string,
  scriptContent: string
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}`
    + `/workers/dispatch/namespaces/${NAMESPACE}/scripts/${tenantId}`;

  const form = new FormData();
  form.append(
    "metadata",
    new Blob([JSON.stringify({ main_module: "worker.js" })], {
      type: "application/json",
    })
  );
  form.append(
    "worker.js",
    new Blob([scriptContent], { type: "application/javascript+module" }),
    "worker.js"
  );

  const res = await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${CF_TOKEN}` },
    body: form,
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(`WfP upload failed: ${JSON.stringify(err)}`);
  }
}
```

---

## 6. Route and Domain Binding

```hcl
# routes.tf
resource "cloudflare_worker_route" "dispatcher" {
  zone_id     = var.zone_id
  pattern     = "*.platform.example.com/*"
  script_name = cloudflare_workers_script.dispatch.name
}
```

---

## Anti-patterns

- **Uploading customer scripts via Terraform.** Customer code is dynamic; encoding it in HCL or
  referencing arbitrary file paths makes state unmanageable. Use the WfP Upload API at runtime.
- **Re-using the same namespace across staging and production.** Namespaces are flat; a tenant
  named `acme` in staging will collide with `acme` in production. Add a prefix: `staging-acme`.
- **Binding DISPATCH_NAMESPACE directly to a zone Worker route without the dispatch Worker
  indirection.** The routing and policy layer must live in a dedicated dispatch Worker; the
  namespace binding is only valid there.
- **Skipping outbound policy enforcement.** Without an outbound Worker, tenant scripts can reach
  internal metadata endpoints and internal VPC services.

---

## Gotchas

- Namespaces cannot be renamed. A rename requires `terraform destroy` + `terraform apply`,
  deleting all customer scripts in the process. Plan the naming convention before launch.
- The `cloudflare_workers_for_platforms_namespace` resource does not expose a `namespace_id`
  attribute; you reference it only by `name`.
- WfP is an Enterprise feature. Attempting to create the resource on a non-WfP account returns a
  `1001` API error; Terraform will surface this as a `400 Bad Request`.
- Outbound Workers for WfP require the `dispatch_namespace_binding` to include an `outbound`
  block referencing a *separately deployed* Worker — the outbound Worker cannot be the dispatch
  Worker itself.

---

## Verification

```bash
# List namespaces via API
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/dispatch/namespaces" \
  | jq '.result[] | {name, created_on}'

# Confirm a tenant script is visible in the namespace
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/dispatch/namespaces/my-saas-platform/scripts" \
  | jq '.result[].id'

# Terraform drift check
terraform plan -detailed-exitcode
```

---

## Related

- `cloudflare-workers-kv-namespace-terraform.md`
- `terraform-cloudflare-provider-workers-d1.md`
- `pulumi-cloudflare-workers-infrastructure-as-code.md`
- `cloudflare-workers-multi-account-failover.md`
- `cloudflare-account-organization-team-access.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_for_platforms_namespace
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
