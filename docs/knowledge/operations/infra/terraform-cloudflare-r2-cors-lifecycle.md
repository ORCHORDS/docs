# Terraform Cloudflare R2 Bucket CORS and Lifecycle Rules
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

R2 buckets provisioned with `wrangler r2 bucket create` accumulate CORS policies and
lifecycle rules configured manually via dashboard or API. When buckets are recreated
(e.g. environment teardown/rebuild) those policies are lost. Teams hit CORS errors
on browser-direct uploads after a bucket recreate, or discover that lifecycle
expiration rules were never reapplied. Encoding CORS and lifecycle in Terraform closes
the configuration gap.

## Context

Cloudflare Terraform provider v4.35+ provides three R2-specific resources:

- `cloudflare_r2_bucket` – creates and manages the bucket itself
- `cloudflare_r2_bucket_cors` – manages the CORS policy (replaces the entire policy on
  each apply, not individual rules)
- `cloudflare_r2_bucket_lifecycle` – manages lifecycle rules (expiration, abort
  incomplete multipart uploads)

R2 CORS uses the S3-compatible CORS XML model internally but the Terraform resource
accepts structured HCL blocks. Lifecycle rules follow the S3 Lifecycle Configuration
schema (filter, expiration, abort incomplete multipart, noncurrent version expiration).

## Provisioning an R2 Bucket

```hcl
# terraform/modules/r2/variables.tf
variable "account_id"   { type = string }
variable "bucket_name"  { type = string }
variable "location"     {
  type    = string
  default = "WNAM"   # WNAM | ENAM | WEUR | EEUR | APAC | OC
}
variable "allowed_origins" {
  type    = list(string)
  default = ["https://app.example.com"]
}

# terraform/modules/r2/main.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

resource "cloudflare_r2_bucket" "assets" {
  account_id = var.account_id
  name       = var.bucket_name
  location   = var.location
}
```

## CORS Configuration

CORS rules for a browser-direct upload flow (presigned PUT + public GET):

```hcl
resource "cloudflare_r2_bucket_cors" "assets" {
  account_id = var.account_id
  bucket_name = cloudflare_r2_bucket.assets.name

  cors_rule {
    id = "browser-upload"
    allowed_origins = var.allowed_origins
    allowed_methods = ["GET", "PUT", "HEAD"]
    allowed_headers = ["Content-Type", "Content-MD5", "x-amz-content-sha256",
                       "x-amz-date", "x-amz-security-token", "Authorization"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }

  cors_rule {
    id = "cdn-public-read"
    allowed_origins = ["*"]
    allowed_methods = ["GET", "HEAD"]
    max_age_seconds = 86400
  }
}
```

Rules are evaluated in declaration order; the first matching rule wins. Place
restrictive authenticated-upload rules before permissive read-only rules.

For development/staging that allows all origins during testing:

```hcl
resource "cloudflare_r2_bucket_cors" "assets_dev" {
  count       = var.env == "dev" ? 1 : 0
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.assets.name

  cors_rule {
    id              = "dev-open"
    allowed_origins = ["http://localhost:3000", "http://localhost:5173"]
    allowed_methods = ["GET", "PUT", "DELETE", "HEAD", "POST"]
    allowed_headers = ["*"]
    max_age_seconds = 0
  }
}
```

## Lifecycle Rules

### Expiring temporary upload scratch space

```hcl
resource "cloudflare_r2_bucket_lifecycle" "assets" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.assets.name

  rule {
    id     = "expire-tmp"
    status = "enabled"

    filter {
      prefix = "tmp/"
    }

    expiration {
      days = 1
    }
  }

  rule {
    id     = "abort-incomplete-multipart"
    status = "enabled"

    filter {
      prefix = ""   # applies to entire bucket
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-old-versions"
    status = "enabled"

    filter {
      prefix = "uploads/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}
```

### Log archival with tiered expiration

```hcl
resource "cloudflare_r2_bucket" "logs" {
  account_id = var.account_id
  name       = "${var.env}-worker-logs"
  location   = "WEUR"
}

resource "cloudflare_r2_bucket_lifecycle" "logs" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.logs.name

  rule {
    id     = "expire-debug-logs"
    status = "enabled"

    filter {
      prefix = "debug/"
      # Optional: only apply to objects with a specific tag
      tags = {
        tier = "debug"
      }
    }

    expiration {
      days = 7
    }
  }

  rule {
    id     = "expire-info-logs"
    status = "enabled"

    filter {
      prefix = "info/"
    }

    expiration {
      days = 90
    }
  }

  rule {
    id     = "expire-audit-logs"
    status = "enabled"

    filter {
      prefix = "audit/"
    }

    expiration {
      days = 365
    }
  }

  rule {
    id     = "abort-multipart"
    status = "enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }
  }
}
```

## Full Environment Module Composition

```hcl
# terraform/environments/production/r2.tf
module "assets_bucket" {
  source = "../../modules/r2"

  account_id      = var.account_id
  bucket_name     = "prod-assets"
  location        = "WNAM"
  allowed_origins = [
    "https://app.example.com",
    "https://www.example.com",
  ]
}

module "logs_bucket" {
  source = "../../modules/r2"

  account_id      = var.account_id
  bucket_name     = "prod-logs"
  location        = "WEUR"
  allowed_origins = []   # internal; no browser CORS needed
}

output "assets_bucket_name" {
  value = module.assets_bucket.bucket_name
}
```

```hcl
# terraform/modules/r2/outputs.tf
output "bucket_name" {
  description = "R2 bucket name for use in wrangler.toml r2_buckets binding"
  value       = cloudflare_r2_bucket.assets.name
}

output "bucket_location" {
  value = cloudflare_r2_bucket.assets.location
}
```

## Wiring Bucket Name into Worker Config

```hcl
# terraform/modules/worker/main.tf
resource "cloudflare_workers_script" "api" {
  account_id  = var.account_id
  script_name = var.worker_name
  content     = file(var.bundle_path)
  module      = true

  r2_bucket_binding {
    name        = "ASSETS"
    bucket_name = var.assets_bucket_name   # pass from r2 module output
  }
}
```

## Anti-patterns

- **Applying `cloudflare_r2_bucket_cors` with no rules** – this clears all CORS rules
  (the resource manages the full policy). Remove the resource instead of emptying it to
  avoid unexpected CORS clearing on `apply`.
- **Overlapping lifecycle rule prefixes without precedence understanding** – R2
  evaluates all matching rules; a `prefix = ""` expiration rule matches every object.
  Use specific prefixes and test with `terraform plan` to check effective rule count.
- **Creating lifecycle rules on a bucket before objects exist** – valid, but causes
  confusing Terraform output ("no changes") if you expect immediate object deletion.
  Rules are evaluated on the R2 lifecycle daemon schedule, not on apply.
- **Storing R2 bucket name in Terraform outputs as sensitive = true** – bucket names
  are not secrets; treating them as sensitive masks them in plans unnecessarily.

## Gotchas

- `cloudflare_r2_bucket_cors` and `cloudflare_r2_bucket_lifecycle` are separate
  resources from `cloudflare_r2_bucket`. Deleting the bucket resource does not cascade-
  delete the CORS/lifecycle resources in the Terraform state; destroy them explicitly
  or use `depends_on` with a `lifecycle { create_before_destroy = false }` ordering.
- Lifecycle rule `status` must be `"enabled"` or `"disabled"` (lowercase string), not
  a boolean. Miscased values produce a provider error.
- R2 does not support S3-style Intelligent Tiering or Glacier transitions. Expiration is
  the only cost control available via lifecycle rules.
- CORS `expose_headers` must include `"ETag"` for browser multipart upload clients that
  verify part ETags; omitting it causes silent browser upload failures.

## Verification

```bash
# Confirm CORS policy applied via R2 S3-compatible API
AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$R2_SECRET_KEY \
aws s3api get-bucket-cors \
  --bucket prod-assets \
  --endpoint-url "https://${CF_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Confirm lifecycle rules
AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$R2_SECRET_KEY \
aws s3api get-bucket-lifecycle-configuration \
  --bucket prod-assets \
  --endpoint-url "https://${CF_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Browser CORS preflight test
curl -s -I -X OPTIONS "https://pub-xxx.r2.dev/test.txt" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  | grep -i "access-control"
```

## Related

- `r2-lifecycle-archival-glacier-strategy.md` – R2 archival and cost strategy
- `r2-cross-account-replication-workers.md` – cross-account replication patterns
- `cloudflare-workers-cost-modeling-d1-analytics.md` – R2 cost attribution
- `terraform-cloudflare-provider-workers-d1.md` – Terraform bindings for D1
- `cloudflare-r2-backup-restore-strategy.md` – backup/restore operational runbook

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket_cors
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket_lifecycle
- https://developers.cloudflare.com/r2/api/s3/cors/
- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
