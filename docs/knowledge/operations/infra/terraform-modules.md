# terraform-modules

**Issue:** Terraform modules — reuse, composition
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write Terraform. The same config is repeated for
each environment. You change it in 5 places. You miss
1. The environment drifts.

## Root cause
**Without modules, code is duplicated.** Use modules.

**Source:** Terraform docs.

## The "module" pattern

For a module:
```
/modules
  /service
    /main.tf
    /variables.tf
    /outputs.tf
    /README.md
```

The module is reusable.

## The "module" syntax

For a module:
```hcl
# modules/service/main.tf
resource "cloudflare_worker_script" "main" {
  name    = var.name
  content = file(var.worker_file)

  plain_text_binding {
    name = "ENV"
    text = var.env
  }
}

resource "cloudflare_d1_database" "main" {
  name = "${var.name}-db"
}

# modules/service/variables.tf
variable "name" {
  type = string
}

variable "env" {
  type = string
}

variable "worker_file" {
  type = string
}

# modules/service/outputs.tf
output "worker_id" {
  value = cloudflare_worker_script.main.id
}

output "database_id" {
  value = cloudflare_d1_database.main.id
}
```

The module is a unit.

## The "use module" pattern

For using the module:
```hcl
# production/main.tf
module "api" {
  source = "../modules/service"

  name = "api"
  env = "production"
  worker_file = "../dist/api.js"
}

module "worker" {
  source = "../modules/service"

  name = "worker"
  env = "production"
  worker_file = "../dist/worker.js"
}
```

The module is reused.

## The "module versioning" pattern

For versioning, use Git:
```hcl
module "api" {
  source = "git::https://github.com/myorg/modules.git//service?ref=v1.2.3"

  name = "api"
  env = "production"
}
```

The version is pinned.

## The "module composition" pattern

For composition, nested modules:
```hcl
# modules/app/main.tf
module "api" {
  source = "../service"
  name = "${var.name}-api"
  env = var.env
  worker_file = "${var.dist_dir}/api.js"
}

module "db" {
  source = "../database"
  name = "${var.name}-db"
  size = var.db_size
}
```

The modules are composed.

## The "module testing" pattern

For testing:
```hcl
# tests/api.tftest.hcl
run "test_api_creation" {
  command = plan

  assert {
    condition = cloudflare_worker_script.main.name == "test-api"
    error_message = "Worker name should be test-api"
  }
}
```

The module is tested.

**Source:** Terraform test:
https://developer.hashicorp.com/terraform/language/tests

## The "remote state" pattern

For remote state:
```hcl
# main.tf
terraform {
  backend "s3" {
    bucket = "my-terraform-state"
    key    = "production/terraform.tfstate"
    region = "us-east-1"
    dynamodb_table = "terraform-locks"
  }
}
```

The state is remote + locked.

**Source:** Terraform S3 backend:
https://developer.hashicorp.com/terraform/language/settings/backends/s3

## The "module registry" pattern

For a private registry:
- **Terraform Cloud:** HashiCorp's
- **GitLab:** Self-hosted
- **Self-hosted:** Custom

The modules are published.

## The "module anti-pattern" anti-patterns

### 1. No module
- **Issue:** Duplicated code
- **Fix:** Module

### 2. No versioning
- **Issue:** Breaking changes
- **Fix:** Pin versions

### 3. No testing
- **Issue:** Bugs ship
- **Fix:** Terraform test

### 4. Local state
- **Issue:** Lost state
- **Fix:** Remote state

### 5. Side effects in module
- **Issue:** Hidden dependencies
- **Fix:** Explicit inputs/outputs

## Verification
- **Test:** Module applies
- **Test:** Module is testable
- **Test:** Version is pinned
- **Live:** State is healthy
- **Audit:** Quarterly review

## Gotchas
- **The "no module" anti-pattern.** Use modules.
- **The "no versioning" anti-pattern.** Pin versions.
- **The "no testing" anti-pattern.** Test modules.

## Related
- `infra/self-hosted-runner-queue-stuck.md`
- `infra/secrets-rotation-runbook.md`
- `infra/pnpm-workspaces-monorepo.md`
- `infra/next-static-export-pages.md`
- `infra/wrangler-deploys.md`
- Terraform: https://developer.hashicorp.com/terraform/
