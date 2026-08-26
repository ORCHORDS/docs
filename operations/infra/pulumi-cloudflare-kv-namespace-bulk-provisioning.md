# Pulumi Cloudflare KV Namespace Bulk Provisioning

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A platform team manages dozens of Workers, each needing its own KV namespace (or a
predictable set of namespaces: `{service}-{env}-sessions`, `{service}-{env}-cache`,
`{service}-{env}-config`). Creating namespaces one at a time via the dashboard causes
naming inconsistencies, missing preview namespaces, and undocumented bindings. Pulumi's
TypeScript-first model lets you derive namespace names from a service registry list and
provision the full matrix — including preview/non-preview pairs and Worker bindings —
in a single `pulumi up`.

## Context

Cloudflare Workers KV has two resource concepts:

- **Namespace** — `cloudflare.WorkersKvNamespace`, an account-scoped named bucket.
- **Binding** — the `kvNamespaceBindings` array on `cloudflare.WorkerScript` that maps
  a namespace to an environment variable name inside the Worker.

Preview namespaces are separate resources from production namespaces. When using
`wrangler`, the `preview_id` in `wrangler.toml` points to a distinct namespace used
during `wrangler dev` sessions. Pulumi manages both through the same resource type;
the naming convention distinguishes them.

Unlike Terraform, Pulumi allows normal TypeScript loops — `for...of`, `Array.map`,
`pulumi.all()` — to create resource sets from an array of inputs without workarounds
like `for_each` limitations.

## 1. Service Registry and Namespace Matrix

```typescript
// service-registry.ts
export interface Service {
  name: string;         // e.g. "auth", "checkout", "catalog"
  kvStores: string[];   // e.g. ["sessions", "cache", "config"]
}

export const services: Service[] = [
  { name: "auth",     kvStores: ["sessions", "rate-limit"] },
  { name: "checkout", kvStores: ["sessions", "cart-cache"] },
  { name: "catalog",  kvStores: ["product-cache", "config"] },
];
```

## 2. Bulk Namespace Provisioning

```typescript
// kv-namespaces.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import { services } from "./service-registry";

const cfConfig = new pulumi.Config("cloudflare");
const accountId = cfConfig.require("accountId");
const stack = pulumi.getStack(); // "staging" | "production"

export interface NamespaceBundle {
  serviceName: string;
  storeName: string;
  production: cloudflare.WorkersKvNamespace;
  preview: cloudflare.WorkersKvNamespace;
}

export const namespaceBundles: NamespaceBundle[] = services.flatMap((service) =>
  service.kvStores.map((store) => {
    const key = `${service.name}-${store}-${stack}`;

    const production = new cloudflare.WorkersKvNamespace(key, {
      accountId,
      title: `${service.name}-${store}-${stack}`,
    });

    const preview = new cloudflare.WorkersKvNamespace(`${key}-preview`, {
      accountId,
      title: `${service.name}-${store}-${stack}-preview`,
    });

    return {
      serviceName: service.name,
      storeName: store,
      production,
      preview,
    };
  })
);

// Index by service name for easy lookup in Worker definitions
export const namespacesByService = namespaceBundles.reduce<
  Record<string, NamespaceBundle[]>
>((acc, bundle) => {
  acc[bundle.serviceName] ??= [];
  acc[bundle.serviceName].push(bundle);
  return acc;
}, {});
```

## 3. Binding Namespaces to Workers

```typescript
// workers.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import { namespacesByService } from "./kv-namespaces";

const cfConfig = new pulumi.Config("cloudflare");
const accountId = cfConfig.require("accountId");
const stack = pulumi.getStack();

function buildKvBindings(
  serviceName: string
): cloudflare.types.input.WorkerScriptKvNamespaceBinding[] {
  const bundles = namespacesByService[serviceName] ?? [];
  return bundles.map((b) => ({
    // Convention: STORE_NAME env var, e.g. SESSIONS, RATE_LIMIT
    name: b.storeName.replace(/-/g, "_").toUpperCase(),
    namespaceId: b.production.id,
  }));
}

export const authWorker = new cloudflare.WorkerScript("auth-worker", {
  accountId,
  name: `auth-worker-${stack}`,
  content: new pulumi.asset.FileAsset("./dist/auth/index.js"),
  module: true,
  kvNamespaceBindings: buildKvBindings("auth"),
});

export const checkoutWorker = new cloudflare.WorkerScript("checkout-worker", {
  accountId,
  name: `checkout-worker-${stack}`,
  content: new pulumi.asset.FileAsset("./dist/checkout/index.js"),
  module: true,
  kvNamespaceBindings: buildKvBindings("checkout"),
});
```

## 4. Generating wrangler.toml KV Sections from Pulumi Outputs

Teams often want a generated `wrangler.toml` for local dev that matches the provisioned
namespace IDs. Use a Pulumi `Command` resource (from `@pulumi/command`) to write the
file after `pulumi up`:

```typescript
// wrangler-codegen.ts
import * as pulumi from "@pulumi/pulumi";
import { local } from "@pulumi/command";
import { namespacesByService } from "./kv-namespaces";

const authBundles = namespacesByService["auth"] ?? [];

// Build the [[kv_namespaces]] TOML fragment
const kvToml = pulumi.all(
  authBundles.flatMap((b) => [b.production.id, b.preview.id])
).apply((ids) => {
  let out = "";
  authBundles.forEach((b, i) => {
    out +=
      `[[kv_namespaces]]\n` +
      `binding = "${b.storeName.replace(/-/g, "_").toUpperCase()}"\n` +
      `id = "${ids[i * 2]}"\n` +
      `preview_id = "${ids[i * 2 + 1]}"\n\n`;
  });
  return out;
});

new local.Command("write-auth-wrangler-kv", {
  create: kvToml.apply(
    (toml) => `printf '%s' '${toml.replace(/'/g, "'\\''")}' > ./services/auth/wrangler.kv.toml`
  ),
});
```

## 5. Bulk Namespace Output for Auditing

```typescript
// outputs.ts
import * as pulumi from "@pulumi/pulumi";
import { namespaceBundles } from "./kv-namespaces";

// Emit a structured map of all provisioned namespaces
export const allNamespaces = pulumi.all(
  namespaceBundles.map((b) =>
    pulumi.all([b.production.id, b.preview.id]).apply(([prodId, prevId]) => ({
      key: `${b.serviceName}__${b.storeName}`,
      productionId: prodId,
      previewId: prevId,
    }))
  )
).apply((list) => Object.fromEntries(list.map((item) => [item.key, item])));

pulumi.export("kvNamespaces", allNamespaces);
```

```bash
# Print all namespace IDs after pulumi up
pulumi stack output kvNamespaces --json | jq 'to_entries[] | "\(.key): \(.value.productionId)"'
```

## 6. Lifecycle Protection on Production Namespaces

```typescript
// kv-namespaces.ts (production guard)
const production = new cloudflare.WorkersKvNamespace(key, {
  accountId,
  title: `${service.name}-${store}-${stack}`,
}, {
  protect: stack === "production",   // prevent accidental destroy
  retainOnDelete: stack === "production",
});
```

## Anti-patterns

- **Using a single shared namespace across services** — a bug in one service can
  corrupt or evict keys from another. Always provision per-service namespaces.
- **Hardcoding namespace IDs in wrangler.toml** — IDs change when a namespace is
  recreated. Generate the TOML from Pulumi outputs or use the `wrangler.toml` only as
  a local-dev override, not as the authoritative binding source.
- **Omitting preview namespaces** — without a `preview_id`, `wrangler dev` writes to
  the production namespace. Always provision paired preview namespaces, even if they
  start empty.
- **Forgetting `retainOnDelete`** — a `pulumi destroy` or resource rename will attempt
  to delete the namespace. KV data is permanently lost on deletion; use
  `retainOnDelete: true` in production.
- **Naming namespaces generically** — "cache" or "sessions" without a service prefix
  causes collisions when two teams share an account. Use
  `{service}-{store}-{environment}` as the title.

## Gotchas

- Renaming a `WorkersKvNamespace` title in Pulumi triggers a delete + create because
  `title` is part of the resource's identity. All stored keys are lost. Use
  `aliases` if you need to rename without recreating.
- The Cloudflare account has a default limit of 100 KV namespaces. At ≥ 20 services
  × 3 stores × 2 environments = 120 namespaces, you will need to request a limit increase
  before `pulumi up` succeeds.
- KV bindings in `cloudflare.WorkerScript` reference namespace IDs (not titles). A race
  between namespace creation and Worker deployment can cause binding failures; Pulumi
  resolves this automatically through output dependencies, but avoid
  `pulumi.output(namespace.id).apply(id => ...)` patterns that bypass the DAG.
- `pulumi stack output kvNamespaces` is only available after the first successful
  `pulumi up`. CI pipelines that need namespace IDs before deployment should read from
  the Pulumi backend directly via the Automation API.

## Verification

```bash
# Count provisioned namespaces
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces?per_page=100" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result | length'

# List namespaces matching a service prefix
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces?per_page=100" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | select(.title | startswith("auth-"))'

# Confirm Worker bindings
wrangler bindings --name "auth-worker-staging"
```

## Related

- `cloudflare-workers-kv-namespace-terraform.md` — Terraform alternative
- `cloudflare-kv-write-read-consistency-patterns.md` — KV consistency model and patterns
- `pulumi-cloudflare-workers-infrastructure-as-code.md` — Workers IaC fundamentals
- `pulumi-cloudflare-workers-service-bindings.md` — service-to-service bindings

## Sources

- `cloudflare.WorkersKvNamespace` Pulumi resource: https://www.pulumi.com/registry/packages/cloudflare/api-docs/workerskvnamespace/
- Workers KV binding reference: https://developers.cloudflare.com/workers/runtime-apis/kv/
- Pulumi resource options (protect, retainOnDelete): https://www.pulumi.com/docs/concepts/options/
