# Terraform Cloudflare Workers Custom Domain Routing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a Cloudflare Worker that needs to serve traffic on a custom hostname (e.g.
`api.example.com`) rather than the default `*.workers.dev` subdomain. Manually
attaching custom domains through the dashboard does not scale across dozens of
Workers and zones managed by different teams. You need a repeatable, reviewable
IaC approach that provisions DNS, custom-domain bindings, and SSL all in a single
`terraform apply`.

---

## Context

Cloudflare Workers support two routing mechanisms:

| Mechanism | Resource | Scope |
|-----------|----------|-------|
| Workers Routes (pattern-based) | `cloudflare_worker_route` | Zone-level wildcard/prefix patterns |
| Custom Domains | `cloudflare_workers_domain` | Single hostname, managed SSL |

Custom Domains differ from Routes in that Cloudflare provisions a dedicated TLS
certificate and binds the Worker as the origin for that hostname — no separate Page
Rule, no Cache Rules interaction. The Terraform `cloudflare` provider (≥ 4.x) exposes
`cloudflare_workers_domain` for this purpose.

This article covers:
- Declaring the zone, Worker script, and `cloudflare_workers_domain` resources
- Managing the required DNS record alongside the domain binding
- Multi-environment routing with `for_each`
- Removing a custom domain cleanly
- Anti-patterns to avoid

---

## 1. Provider and Variable Declarations

```hcl
# versions.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
  required_version = ">= 1.9"
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

variable "cloudflare_api_token" {
  description = "API token with Zone:Edit + Workers:Edit permissions"
  type        = string
  sensitive   = true
}

variable "account_id" {
  type = string
}

variable "zone_id" {
  type = string
}

variable "zone_name" {
  description = "Root domain, e.g. example.com"
  type        = string
}
```

The API token must carry **Zone → DNS → Edit**, **Zone → Workers Routes → Edit**, and
**Account → Workers Scripts → Edit** permissions. Scope it to the specific zone(s) you
manage; never use a global API key in automation.

---

## 2. Worker Script Resource

```hcl
# worker.tf
resource "cloudflare_worker_script" "api" {
  account_id = var.account_id
  name       = "api-worker"
  content    = file("${path.module}/dist/worker.js")

  # Compatibility date keeps the runtime pinned; update deliberately.
  compatibility_date  = "2024-09-23"
  compatibility_flags = ["nodejs_compat"]

  # Bind secrets from Terraform (value comes from variable or Vault dynamic secret)
  secret_text_binding {
    name = "DB_PASSWORD"
    text = var.db_password
  }
}
```

The `content` field expects a pre-bundled ES module string. In CI, run
`wrangler deploy --dry-run --outdir dist` to produce `dist/worker.js` before
`terraform apply`.

---

## 3. Custom Domain Binding

```hcl
# domains.tf
resource "cloudflare_workers_domain" "api" {
  account_id  = var.account_id
  hostname    = "api.${var.zone_name}"
  service     = cloudflare_worker_script.api.name
  zone_id     = var.zone_id

  depends_on = [cloudflare_worker_script.api]
}
```

`cloudflare_workers_domain` registers the hostname with Workers and provisions a
managed TLS certificate automatically. No `cloudflare_certificate_pack` resource is
needed — the binding owns the certificate lifecycle.

---

## 4. Companion DNS Record

A custom domain binding does **not** create a DNS record. You must add an `A` or
`AAAA` record proxied through Cloudflare (orange-cloud) pointing to a placeholder IP:

```hcl
# dns.tf
resource "cloudflare_record" "api" {
  zone_id = var.zone_id
  name    = "api"
  type    = "A"
  value   = "192.0.2.1"   # Placeholder; Cloudflare ignores it for proxied records
  proxied = true
  ttl     = 1             # Auto TTL — required for proxied records

  depends_on = [cloudflare_workers_domain.api]
}
```

The actual IP is irrelevant because Cloudflare intercepts proxied traffic before it
reaches any origin. `192.0.2.1` (TEST-NET-1) makes the intent explicit in code review.

---

## 5. Multi-environment Routing with `for_each`

```hcl
# environments.tf
locals {
  environments = {
    production = {
      hostname_prefix = "api"
      worker_name     = "api-worker-prod"
      script_path     = "${path.module}/dist/worker-prod.js"
    }
    staging = {
      hostname_prefix = "api-staging"
      worker_name     = "api-worker-staging"
      script_path     = "${path.module}/dist/worker-staging.js"
    }
  }
}

resource "cloudflare_worker_script" "env" {
  for_each   = local.environments
  account_id = var.account_id
  name       = each.value.worker_name
  content    = file(each.value.script_path)
  compatibility_date = "2024-09-23"
}

resource "cloudflare_workers_domain" "env" {
  for_each   = local.environments
  account_id = var.account_id
  hostname   = "${each.value.hostname_prefix}.${var.zone_name}"
  service    = cloudflare_worker_script.env[each.key].name
  zone_id    = var.zone_id

  depends_on = [cloudflare_worker_script.env]
}

resource "cloudflare_record" "env" {
  for_each = local.environments
  zone_id  = var.zone_id
  name     = each.value.hostname_prefix
  type     = "A"
  value    = "192.0.2.1"
  proxied  = true
  ttl      = 1
}
```

Use separate `cloudflare_worker_script` resources per environment rather than
wrangler environments, so Terraform state tracks each independently and rollback
targets a single resource.

---

## 6. Typed TypeScript Worker for Custom-Domain Context

```typescript
// src/index.ts
export interface Env {
  DB_PASSWORD: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Custom-domain requests always arrive with the full hostname.
    // Workers.dev fallback can be blocked via wrangler.toml `workers_dev = false`.
    if (!url.hostname.endsWith(".example.com")) {
      return new Response("Forbidden", { status: 403 });
    }

    return new Response(`Hello from ${url.hostname}`, {
      headers: { "Content-Type": "text/plain" },
    });
  },
} satisfies ExportedHandler<Env>;
```

Set `workers_dev = false` in `wrangler.toml` to prevent traffic bypassing the custom
domain via the `*.workers.dev` route.

---

## Anti-patterns

- **Using `cloudflare_worker_route` for custom domains** — Routes use pattern matching
  (`*.example.com/*`) and share the zone's HTTP pipeline. Custom domains give the
  Worker full control of TLS and avoid zone-level rule interactions.
- **Storing the API token in `.tfvars` files committed to source control** — Use
  `TF_VAR_cloudflare_api_token` from CI secrets or Pulumi ESC / Vault.
- **Skipping `depends_on` between DNS record and domain binding** — A race condition
  can cause the domain binding to fail if the DNS record does not yet exist when
  Cloudflare validates the zone.
- **Using a non-proxied DNS record** — An unproxied record bypasses Cloudflare
  entirely; custom-domain TLS will not be issued.

---

## Gotchas

- `cloudflare_workers_domain` requires the hostname's zone to be **active** (NS
  delegated to Cloudflare). Partial-setup zones are not supported.
- Renaming a Worker script (`name` field) destroys and re-creates the script resource.
  Custom domain bindings referencing the old name will break until the new binding is
  applied. Use `lifecycle { create_before_destroy = true }` on the script resource.
- Custom domain certificates can take up to 60 seconds to provision after
  `terraform apply` returns. Health checks that run immediately may fail during this
  window.
- The `environment` argument on `cloudflare_workers_domain` is **not supported** as of
  provider 4.x — you must use distinct Worker script names per environment.

---

## Verification

```bash
# Confirm the domain binding appears in the API
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/domains" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | select(.hostname=="api.example.com")'

# Check that TLS is valid on the custom hostname
curl -sv https://api.example.com/ 2>&1 | grep -E "SSL|subject|issuer"

# Terraform state sanity check
terraform state list | grep workers_domain
terraform state show 'cloudflare_workers_domain.api'
```

---

## Related

- `terraform-cloudflare-workers-routes-zone-config.md`
- `terraform-cloudflare-page-rule-migration-workers-routes.md`
- `wrangler-toml-multi-environment-config.md`
- `cloudflare-workers-api-token-scoping.md`
- `workers-cold-start-bundle-size-optimization.md`

---

## Sources

- Cloudflare Terraform Provider – `cloudflare_workers_domain`: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_domain
- Cloudflare Workers Custom Domains docs: https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- Cloudflare API – Workers Domains: https://developers.cloudflare.com/api/operations/worker-domain-list-domains
