# Terraform Cloudflare Provider: Workers, D1, and KV

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Teams manually clicking through the Cloudflare dashboard to
provision Workers scripts, D1 databases, and KV namespaces end
up with undocumented, environment-specific drift. Reproducing a
production environment for staging becomes a half-day task.

## Context

The `cloudflare/cloudflare` Terraform provider (v4.x) covers the
full surface of Cloudflare's developer platform. This entry covers
declaring Workers scripts, D1 databases, and KV namespaces as
Terraform resources, authenticating via `CF_API_TOKEN`, deciding
when to generate `wrangler.toml` from Terraform outputs vs.
committing a static file, managing remote state on Cloudflare R2
or AWS S3, and importing resources that were created out-of-band.

All examples target provider `~> 4.0` and Terraform `>= 1.6`.

## 1. Provider and Authentication

Set the Cloudflare API token as an environment variable rather
than hardcoding it in the provider block:

```bash
export CF_API_TOKEN="<token-with-workers-d1-kv-permissions>"
```

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
  required_version = ">= 1.6"
}

provider "cloudflare" {
  # CF_API_TOKEN is read automatically; do not set api_token
  # here unless reading from a secrets manager reference.
}
```

The token needs the following permissions: **Workers Scripts
(Edit)**, **D1 (Edit)**, **Workers KV Storage (Edit)**, and
**Account (Read)**.

## 2. Declaring Workers, D1, and KV Resources

```hcl
variable "account_id"    { type = string }
variable "zone_id"       { type = string }
variable "worker_script" { type = string } # file path

# --- KV namespace ---
resource "cloudflare_workers_kv_namespace" "cache" {
  account_id = var.account_id
  title      = "example project-cache"
}

# --- D1 database ---
resource "cloudflare_d1_database" "main" {
  account_id = var.account_id
  name       = "example project-main"
}

# --- Workers script ---
resource "cloudflare_workers_script" "api" {
  account_id = var.account_id
  name       = "example project-api"
  content    = file(var.worker_script)

  kv_namespace_binding {
    name         = "CACHE"
    namespace_id = cloudflare_workers_kv_namespace.cache.id
  }

  d1_database_binding {
    name        = "DB"
    database_id = cloudflare_d1_database.main.id
  }

  plain_text_binding {
    name = "ENVIRONMENT"
    text = "production"
  }
}
```

The `content` argument accepts the raw ES-module or service-worker
JavaScript. For builds that produce a dist file, use a
`data "local_file"` or a `null_resource` build trigger instead of
`file()`.

## 3. Remote State: R2 Backend

Storing state in Cloudflare R2 keeps everything inside one vendor
boundary and avoids cross-cloud egress fees:

```hcl
terraform {
  backend "s3" {
    # R2 exposes an S3-compatible API.
    bucket                      = "tf-state-example project"
    key                         = "workers/terraform.tfstate"
    region                      = "auto"
    endpoint                    = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true
    # Credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
    # set to your R2 API token pair.
  }
}
```

Create the R2 bucket once with `wrangler r2 bucket create
tf-state-example project` before the first `terraform init`.

## 4. wrangler.toml: Generate or Commit?

Two valid approaches:

| Approach | Pros | Cons |
|---|---|---|
| Commit static `wrangler.toml` | Simple local `wrangler dev` | KV/D1 IDs must be kept in sync manually |
| Generate from Terraform outputs | Single source of truth | Requires `terraform output` step in CI |

Generate with a `local_file` resource when IDs must stay in sync:

```hcl
resource "local_file" "wrangler_toml" {
  filename = "${path.module}/../wrangler.toml"
  content  = <<-TOML
    name = "example project-api"
    main = "dist/index.js"
    compatibility_date = "2026-08-01"

    [[kv_namespaces]]
    binding     = "CACHE"
    id          = "${cloudflare_workers_kv_namespace.cache.id}"

    [[d1_databases]]
    binding     = "DB"
    database_id = "${cloudflare_d1_database.main.id}"
    database_name = "example project-main"
  TOML
}
```

Commit the generated file so that `wrangler dev` works without a
prior `terraform apply`.

## 5. Importing Existing Resources

Resources created via the dashboard or `wrangler` can be pulled
into state without re-creating them:

```bash
# KV namespace
terraform import \
  cloudflare_workers_kv_namespace.cache \
  "<ACCOUNT_ID>/<NAMESPACE_ID>"

# D1 database
terraform import \
  cloudflare_d1_database.main \
  "<ACCOUNT_ID>/<DATABASE_ID>"

# Workers script
terraform import \
  cloudflare_workers_script.api \
  "<ACCOUNT_ID>/example project-api"
```

Run `terraform plan` immediately after each import to confirm zero
diff before committing the import to the state file.

## Anti-patterns

- Storing `CF_API_TOKEN` in `.tfvars` files committed to source
  control. Use environment variables or a secrets manager.
- Using `terraform apply` to deploy Worker code on every commit.
  Use `wrangler deploy` for fast iterations; use Terraform only to
  manage the resource bindings and configuration.
- Sharing a single KV namespace or D1 database across staging and
  production in the same Terraform workspace. Use separate
  workspaces or separate state files.

## Gotchas

- `cloudflare_workers_script` replaces the deployed script on
  every `apply` if `content` changes. Ensure the build artifact is
  stable (deterministic output) to avoid spurious replacements.
- D1 database creation via Terraform does not run migrations. Run
  `wrangler d1 migrations apply` as a separate CI step after
  `terraform apply`.
- The R2 S3-compatible backend requires `force_path_style = true`;
  virtual-hosted-style URLs are not supported by R2.

## Verification

```bash
# Confirm provider version
terraform version

# Validate config
terraform validate

# Preview changes
terraform plan -out=tfplan

# Apply
terraform apply tfplan

# Confirm Worker is live
curl https://example project-api.<account>.workers.dev/health
```

## Related

- `cloudflare-workers-local-dev.md`
- `d1-migrations-ci.md`
- `r2-static-assets-terraform.md`

## Source URLs (verified 2026-08-17)

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/r2/examples/terraform/
