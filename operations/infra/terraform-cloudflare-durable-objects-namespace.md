# Terraform Cloudflare Durable Objects Namespace Management
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Teams deploying Workers with Durable Objects manage DO class bindings ad-hoc with
wrangler or via dashboard clicks. When multiple Workers share DO namespaces, IaC drift
becomes a support burden: class renames silently destroy object instances, migration
blocks get forgotten, and namespace IDs get hard-coded into downstream config.
Encoding DO lifecycle in Terraform closes the gap.

## Context

Cloudflare Terraform provider v4+ exposes Durable Objects bindings through the
`cloudflare_workers_script` resource. Each `durable_object_namespace_binding` block
ties a binding name to a DO class defined in a Worker bundle. Migrations (new classes,
renamed classes, deleted classes) require a `migrations` block inside the script
resource to preserve stored object data across deployments. Skipping it does not error
at `terraform apply` time; it fails silently at runtime when the first stub is created.

Key primitives:
- `cloudflare_workers_script` – deploys the Worker bundle with DO class declarations
- `durable_object_namespace_binding` – attaches a named DO namespace to the script
- `migrations` block – declares class evolution so the runtime migrates stored objects
- `cloudflare_workers_script_bindings` data source – reads namespace IDs post-create

## Declaring a Worker with a Durable Object Namespace

```hcl
# terraform/modules/durable-objects/variables.tf
variable "account_id"    { type = string }
variable "worker_name"   { type = string }
variable "worker_bundle" { type = string }   # path to compiled .js bundle

# terraform/modules/durable-objects/main.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

resource "cloudflare_workers_script" "counter" {
  account_id  = var.account_id
  script_name = var.worker_name
  content     = file(var.worker_bundle)
  module      = true   # required for ES module Workers

  durable_object_namespace_binding {
    name       = "COUNTER_NAMESPACE"   # binding name in Worker env
    class_name = "CounterDO"           # exported class name in the bundle
  }

  # migrations block required for every new class
  migrations {
    tag         = "v1"
    new_classes = ["CounterDO"]
  }
}
```

Tags must be lexicographically increasing strings. Use `"v1"`, `"v2"`, `"v3"`.
Never reuse or skip a tag; Cloudflare enforces uniqueness at the account level.

## Managing DO Class Renames and Migrations

Renaming a DO class without a migration block destroys all existing object instances.
Declare the rename before deploying the new bundle:

```hcl
resource "cloudflare_workers_script" "session_store" {
  account_id  = var.account_id
  script_name = "session-store-worker"
  content     = file("${path.module}/dist/session-store.js")
  module      = true

  durable_object_namespace_binding {
    name       = "SESSIONS"
    class_name = "SessionDOv2"   # renamed from SessionDO
  }

  # v1 was: new_classes = ["SessionDO"]
  # v2 renames it
  migrations {
    tag = "v2"
    renamed_classes {
      from = "SessionDO"
      to   = "SessionDOv2"
    }
  }
}
```

After all objects have migrated and the old class is unused, add a deletion step:

```hcl
  migrations {
    tag             = "v3"
    deleted_classes = ["SessionDO"]
  }
```

Keep all prior migration blocks in the resource; the runtime needs the full history.
Stack them in ascending tag order within the same `cloudflare_workers_script` resource.

## Cross-Worker Namespace References

A common pattern is a central DO namespace consumed by multiple Workers. Declare the
namespace in one script and reference it by `script_name` in others:

```hcl
resource "cloudflare_workers_script" "presence" {
  account_id  = var.account_id
  script_name = "presence-worker"
  content     = file("${path.module}/dist/presence.js")
  module      = true

  durable_object_namespace_binding {
    name       = "PRESENCE"
    class_name = "PresenceDO"
  }

  migrations {
    tag         = "v1"
    new_classes = ["PresenceDO"]
  }
}

# api-worker binds to the same namespace without owning the class
resource "cloudflare_workers_script" "api" {
  account_id  = var.account_id
  script_name = "api-worker"
  content     = file("${path.module}/dist/api.js")
  module      = true

  durable_object_namespace_binding {
    name        = "PRESENCE"
    class_name  = "PresenceDO"
    script_name = cloudflare_workers_script.presence.script_name
    # environment = "production"  # if the owning script is in a named env
  }
}
```

Export the namespace ID so downstream stacks can reference it:

```hcl
data "cloudflare_workers_script_bindings" "presence_bindings" {
  account_id  = var.account_id
  script_name = cloudflare_workers_script.presence.script_name
}

output "presence_namespace_id" {
  description = "Durable Object namespace ID for PRESENCE class"
  value = one([
    for b in data.cloudflare_workers_script_bindings.presence_bindings.bindings :
    b.namespace_id if b.name == "PRESENCE"
  ])
}
```

## Environment-Specific Namespaces with Workspaces

Staging and production must never share a DO namespace. Use Terraform workspaces to
create fully isolated sets of Worker scripts and namespaces:

```hcl
# terraform/environments/durable-objects/main.tf
locals {
  env         = terraform.workspace   # "staging" or "production"
  worker_name = "counter-worker-${local.env}"
}

resource "cloudflare_workers_script" "counter" {
  account_id  = var.account_id
  script_name = local.worker_name
  content     = file("${path.module}/../../dist/counter.js")
  module      = true

  durable_object_namespace_binding {
    name       = "COUNTER"
    class_name = "CounterDO"
  }

  migrations {
    tag         = "v1"
    new_classes = ["CounterDO"]
  }
}
```

```bash
terraform workspace select staging
terraform apply -var="account_id=$CF_ACCOUNT_ID_STAGING"

terraform workspace select production
terraform apply -var="account_id=$CF_ACCOUNT_ID_PROD"
```

## Anti-patterns

- **Omitting the `migrations` block on first deploy** – causes runtime error
  `10021: Durable Objects class "X" not declared in migrations` when the first stub
  is created. Terraform apply succeeds; production breaks silently.
- **Reusing migration tags** – Cloudflare rejects duplicate tags with error `10023`.
  Incrementing out of order (v3 → v1) is also rejected.
- **Hard-coding namespace IDs** in downstream Terraform instead of using the data
  source output – breaks when the owning script is recreated (e.g. `script_name`
  changed).
- **Declaring DO bindings without `script_name` on consumer Workers** – silently
  creates an orphaned second namespace instead of sharing the owning script's namespace.
- **Setting `module = false`** on ES module Workers – migration blocks are silently
  ignored and DO creation fails at runtime.

## Gotchas

- Deleting a `cloudflare_workers_script` resource permanently destroys the namespace
  and all stored DO data. There is no soft-delete. Protect production scripts with
  `lifecycle { prevent_destroy = true }`.
- The Cloudflare provider cannot import existing DO namespaces created outside Terraform
  via wrangler. You must `terraform import` the script resource and then reconcile
  binding metadata manually.
- `migrations` is a list of blocks; Terraform evaluates them in declaration order.
  Always place new migration blocks after existing ones.
- Named environments (Workers Environments) have separate namespace IDs from the
  default namespace; always specify `environment` on cross-script bindings when the
  owning script uses environments.

## Verification

```bash
# Confirm migrations block appears in plan
terraform plan -out=plan.tfplan
terraform show plan.tfplan | grep -A 10 "migrations"

# After apply: list DO namespaces via API
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/durable_objects/namespaces" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | {id, name, class, script}'

# Verify binding in Worker TypeScript at runtime
# const id = env.COUNTER_NAMESPACE.idFromName("user:123");
# const stub = env.COUNTER_NAMESPACE.get(id);
# const resp = await stub.fetch(request);
```

## Related

- `cloudflare-durable-objects-stateful-edge.md` – application-layer DO design patterns
- `wrangler-toml-multi-environment-config.md` – wrangler-side multi-env DO bindings
- `terraform-cloudflare-provider-workers-d1.md` – D1 database binding lifecycle
- `terraform-workspace-multi-account-cloudflare.md` – workspace-per-environment strategy
- `cloudflare-workers-api-token-scoping.md` – least-privilege token for Terraform deployments

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_script
- https://developers.cloudflare.com/durable-objects/api/
- https://developers.cloudflare.com/workers/configuration/migrations/
- https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- https://developers.cloudflare.com/durable-objects/platform/bindings/
