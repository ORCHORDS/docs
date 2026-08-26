# terraform-workspace-patterns

**Issue:** Using Terraform workspaces to manage multiple environments from one codebase
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams copy Terraform configs per environment causing drift. Workspaces allow one codebase to manage staging and production with different variable values and isolated state.

## Pattern / Solution
Basic workspace operations:
```bash
terraform workspace list
terraform workspace new staging
terraform workspace new production
terraform workspace select production
terraform workspace show
```

Workspace-aware variables:
```hcl
locals {
  env = terraform.workspace

  instance_counts = {
    staging    = 1
    production = 3
  }

  instance_types = {
    staging    = "t3.small"
    production = "m6i.xlarge"
  }
}

resource "aws_instance" "app" {
  count         = local.instance_counts[local.env]
  instance_type = local.instance_types[local.env]
  tags = {
    Environment = local.env
  }
}
```

Per-workspace tfvars files:
```bash
# Use explicit var-file per workspace
terraform apply -var-file="vars/${terraform.workspace}.tfvars"

# In CI:
ENV=production terraform workspace select $ENV
terraform apply -var-file="vars/$ENV.tfvars" -auto-approve
```

S3 backend state isolation per workspace:
```
# State files created automatically:
s3://mybucket/env:/staging/terraform.tfstate
s3://mybucket/env:/production/terraform.tfstate
```

## Gotchas
- `default` workspace is used when no workspace is selected; never deploy production from default
- Workspace name is not available in `backend` configuration blocks — you cannot dynamically set the S3 key per workspace there
- Terraform Cloud workspaces are a different concept from CLI workspaces; they are separate projects with separate runs
- Large environment differences (different resource types, providers) are better served by separate root modules, not workspaces
- `terraform destroy` in the wrong workspace destroys the wrong environment; add workspace assertion in CI

## Related
- `terraform-remote-backend.md`
- `terraform-modules-structure.md`
- `environment-promotion-gates.md`
