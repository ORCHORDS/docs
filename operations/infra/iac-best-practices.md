# iac-best-practices

**Issue:** Infrastructure as Code — Terraform / OpenTofu / Pulumi
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write Terraform. The code grows. One apply takes
20 minutes. A typo in staging applies to production.
You can't reuse modules. The state is in someone's
laptop. You wish you had a structure.

## Root cause
**Without structure, IaC is chaos.** Follow the
patterns.

**Source:** Terraform docs:
https://developer.hashicorp.com/terraform/

## The "21 best practices" pattern

For 21 best practices:
1. **Remote state with locking**
2. **Use existing modules**
3. **Import existing infra**
4. **No hard-coding**
5. **Format + validate**
6. **Consistent naming**
7. **Tag consistently**
8. **Policy as code**
9. **Secrets management**
10. **Test code**
11. **Debug + troubleshoot**
12. **Small reusable modules**
13. **Loops + conditionals**
14. **Functions**
15. **Dynamic blocks**
16. **Use workspaces carefully**
17. **Lifecycle block**
18. **Variable validation**
19. **Helper tools**
20. **IDE extensions**
21. **AI safely**

The practices are 21.

## The "remote state" pattern

For remote state:
```hcl
terraform {
  backend "s3" {
    bucket = "my-tf-state"
    key    = "production/terraform.tfstate"
    region = "us-east-1"
    dynamodb_table = "tf-locks"
    encrypt = true
  }
}
```

The state is remote + locked.

**Source:** S3 backend:
https://developer.hashicorp.com/terraform/language/settings/backends/s3

## The "directory structure" pattern

For the project structure:
```
infrastructure/
modules/
  networking/
  compute/
  database/
  monitoring/
environments/
  production/
    networking/
    compute/
    database/
  staging/
    networking/
  global/
    iam/
    dns/
```

Each subdir is an independent root module with its
own state.

## The "resource vs service module" pattern

For modules:
- **Resource module:** Single resource type
- **Service module:** Composes resource modules
- **Root module:** Calls service modules

```hcl
# rds-instance/main.tf
resource "aws_db_instance" "main" {
  // ...
}

# postgres-service/main.tf
module "rds_instance" {
  source = "../rds-instance"
  // ...
}

module "subnet_group" {
  source = "../subnet-group"
  // ...
}

# production/database/main.tf
module "postgres" {
  source = "../../modules/postgres-service"
  // ...
}
```

The modules are layered.

## The "module size" pattern

For module size:
- **Resource module:** ~150 lines
- **Service module:** ~500 lines
- **Monolithic:** 2,000+ lines (bad)

| Design | Plan time | Blast radius |
|---|---|---|
| Monolithic (2000+ lines) | 7-15 min | Entire stack |
| Service modules (500) | 2-4 min | One service |
| Resource modules (150) | < 1 min | One resource |

Smaller is better.

## The "module input/output" pattern

For module design:
```hcl
# Module
variable "name" {
  type = string
  validation {
    condition = length(var.name) > 0
    error_message = "Name cannot be empty."
  }
}

output "id" {
  value = aws_resource.main.id
}

output "arn" {
  value = aws_resource.main.arn
}
```

The interface is clean.

## The "naming convention" pattern

For naming:
- **Underscores:** As separator
- **Lowercase:** Letters
- **No resource type in name:** `main` not `aws_db_instance_main`
- **Singular:** For single values
- **Plural:** For lists/maps

The naming is consistent.

## The "tagging" pattern

For tags:
```hcl
provider "aws" {
  default_tags {
    tags = {
      Environment = "production"
      Owner       = "platform-team"
      CostCenter  = "engineering"
      ManagedBy   = "terraform"
    }
  }
}
```

The tags are consistent.

## The "lifecycle block" pattern

For lifecycle:
```hcl
resource "aws_db_instance" "main" {
  // ...
  lifecycle {
    prevent_destroy = true
    create_before_destroy = true
    ignore_changes = [
      password,  // Managed externally
    ]
  }
}
```

The lifecycle is controlled.

## The "CI pipeline" pattern

For CI:
1. **Format:** `terraform fmt -check`
2. **Validate:** `terraform validate`
3. **Lint:** `tflint` + `checkov`
4. **Plan:** `terraform plan -out=tfplan`
5. **Policy:** OPA / Conftest
6. **Apply:** On merge

The pipeline is gated.

## The "policy as code" pattern

For OPA:
```rego
package terraform.policies

deny[msg] {
  resource := input.resource.aws_s3_bucket[name]
  not resource.server_side_encryption_configuration

  msg := sprintf("S3 bucket %s must have encryption", [name])
}
```

The policies are enforced.

## The "drift detection" pattern

For drift:
```bash
# Cron: every 4-6 hours
terraform plan -detailed-exitcode
# Exit 2 = drift
```

Drift is detected.

## The "state backup" pattern

For backup:
- **S3 versioning:** Enabled
- **State recovery:** Tested

The state is backed up.

## The "secret management" pattern

For secrets, never in state:
- **Use SOPS:** Encrypt vars
- **Use Vault / AWS Secrets Manager:** Dynamic
- **Never in TF output:** Use a secret manager

The secrets are external.

## The "test pyramid" pattern

For IaC tests:
| Layer | Tool | When | What |
|---|---|---|---|
| Static | Checkov, tflint | Pre-commit, CI | Security + syntax |
| Plan | OPA / Conftest | CI | Policy compliance |
| Integration | Terratest | CI nightly | Runtime |

The tests are layered.

## The "workspaces" anti-pattern

For workspaces:
- **Issue:** Easy to mis-apply
- **Fix:** Directory-based per env

Workspaces are confusing.

## The "monolithic" anti-pattern

For one big root module:
- **Plan time:** 7-15 min
- **Blast radius:** Entire infra
- **Drift:** Hard to detect

Small + isolated is better.

## The "state in git" anti-pattern

For state in git:
- **Issue:** Merge conflicts, secrets
- **Fix:** Remote backend only

The state is never in git.

## The "manual state" anti-pattern

For manual state:
```bash
# ❌ Bad: bypasses plan-review-apply
terraform state mv old new
```

Manual state is risky.

## The "no policy" anti-pattern

For no policy:
- **Issue:** Inconsistent security
- **Fix:** OPA / Conftest / Sentinel

Policies are required.

## The "no tags" anti-pattern

For no tags:
- **Issue:** Can't allocate cost
- **Fix:** Default tags

The tags are required.

## The "no tests" anti-pattern

For no tests:
- **Issue:** Bugs ship
- **Fix:** Test pyramid

Tests are required.

## Verification
- **Test:** Plan is reviewed
- **Test:** Policies are enforced
- **Test:** Drift is detected
- **Live:** State is healthy
- **Audit:** Quarterly review

## Gotchas
- **The "monolithic" anti-pattern.** Small modules.
- **The "no policy" anti-pattern.** OPA.
- **The "no tests" anti-pattern.** Test pyramid.

## Related
- `infra/terraform-modules.md`
- `infra/secrets-rotation-runbook.md`
- `deploy/gitops.md`
- `deploy/canary-deployments.md`
- `infra/github-self-hosted-runners.md`
- Terraform: https://developer.hashicorp.com/terraform/
- Spacelift: https://spacelift.io/blog/terraform-best-practices
- Zop: https://zop.dev/resources/blogs/infrastructure-as-code-best-practices-terraform-pulumi-and-opentofu-in-2026/
