# terraform-import-existing

**Issue:** Importing existing cloud resources into Terraform state without recreating them
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams have manually provisioned infrastructure that needs to be brought under Terraform management. Importing avoids destroying and recreating resources, which would cause downtime.

## Pattern / Solution
Classic import workflow:
```bash
# 1. Write the resource block in .tf (must match the resource exactly)
# resource "aws_s3_bucket" "assets" {
#   bucket = "myorg-assets-prod"
# }

# 2. Import the resource into state
terraform import aws_s3_bucket.assets myorg-assets-prod

# 3. Run plan — should show no changes if resource block matches reality
terraform plan

# 4. Fix any diffs by updating the .tf to match current state
```

Terraform 1.5+ import block (declarative, plan-able):
```hcl
# import.tf
import {
  to = aws_s3_bucket.assets
  id = "myorg-assets-prod"
}

resource "aws_s3_bucket" "assets" {
  bucket = "myorg-assets-prod"
}
```

```bash
terraform plan   # shows the import in the plan output
terraform apply  # imports without recreating
```

Generate config from existing resources (Terraform 1.5+):
```bash
terraform plan -generate-config-out=generated.tf
# Review generated.tf, clean up, move to appropriate .tf file
```

Bulk import script (multiple resources):
```bash
#!/bin/bash
resources=(
  "aws_security_group.web sg-abc123"
  "aws_security_group.db sg-def456"
  "aws_subnet.public_a subnet-111111"
)

for entry in "${resources[@]}"; do
  resource=$(echo $entry | cut -d' ' -f1)
  id=$(echo $entry | cut -d' ' -f2)
  terraform import "$resource" "$id"
done
```

## Gotchas
- Always `terraform plan` after import — a 0-diff plan means the resource block accurately matches state; diffs mean attributes will be changed on next apply
- `terraform import` does not generate the `.tf` code; you must write it first (unless using `-generate-config-out`)
- Some resources cannot be imported (ephemeral, auto-managed sub-resources); check the provider docs
- Import does not validate that the resource matches; mismatches silently overwrite state
- After import, enable lifecycle `prevent_destroy = true` for critical resources

## Related
- `terraform-modules-structure.md`
- `terraform-state-management.md`
- `terraform-drift-detection.md`
