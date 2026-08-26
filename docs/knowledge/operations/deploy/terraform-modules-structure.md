# terraform-modules-structure

**Issue:** Structuring Terraform modules for reusability, versioning, and team collaboration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Monolithic Terraform configs become unmaintainable. Modules without versioning cause unpredictable breakage. This entry covers the file layout and calling conventions for a module registry approach.

## Pattern / Solution
Module directory layout:
```
modules/
  vpc/
    main.tf
    variables.tf
    outputs.tf
    versions.tf      # required_providers block
    README.md        # terraform-docs generated
  eks-cluster/
    main.tf
    variables.tf
    outputs.tf
    versions.tf
    modules/         # sub-modules (private)
      node-group/
        main.tf

environments/
  staging/
    main.tf          # root module, calls published modules
    terraform.tfvars
    backend.tf
  production/
    main.tf
    terraform.tfvars
    backend.tf
```

Module versioning with Git tags:
```hcl
# environments/production/main.tf
module "vpc" {
  source  = "git::https://github.com/myorg/terraform-modules.git//modules/vpc?ref=v1.3.0"

  cidr_block         = var.vpc_cidr
  availability_zones = var.azs
}

# Or Terraform Registry:
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
}
```

variables.tf with validation:
```hcl
variable "environment" {
  type        = string
  description = "Deployment environment"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Must be staging or production."
  }
}

variable "instance_count" {
  type    = number
  default = 2
  validation {
    condition     = var.instance_count >= 1 && var.instance_count <= 10
    error_message = "Instance count must be 1-10."
  }
}
```

Generate docs:
```bash
terraform-docs markdown table --output-file README.md ./modules/vpc/
```

## Gotchas
- Never use `source = "../../../modules/vpc"` in production; use versioned references
- `outputs.tf` must export everything callers might need; adding outputs later is non-breaking but requires module version bump
- Avoid provider configuration inside modules; pass provider aliases from the root
- `count` and `for_each` in module calls cannot use values known only at apply time

## Related
- `terraform-remote-backend.md`
- `terraform-workspace-patterns.md`
- `terraform-import-existing.md`
