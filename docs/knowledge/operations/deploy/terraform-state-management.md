# terraform-state-management

**Issue:** Storing and managing Terraform state safely so multiple engineers and CI pipelines can collaborate without corruption
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Local state files checked into git cause merge conflicts, expose secrets, and cannot be locked for concurrent access. Remote state with locking is mandatory for any team usage of Terraform.

## Pattern / Solution
**Remote backend — S3 + DynamoDB (AWS)**
```hcl
# backend.tf
terraform {
  backend "s3" {
    bucket         = "acme-terraform-state"
    key            = "services/api/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
```

**Create the backend resources (bootstrap, run once)**
```bash
# S3 bucket with versioning + encryption
aws s3api create-bucket --bucket acme-terraform-state --region us-east-1
aws s3api put-bucket-versioning \
  --bucket acme-terraform-state \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
  --bucket acme-terraform-state \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# DynamoDB table for state locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

**State file organisation — one state per environment per service**
```
state/
  api/prod/terraform.tfstate
  api/staging/terraform.tfstate
  infra/networking/terraform.tfstate
  infra/databases/terraform.tfstate
```

**State operations**
```bash
# Import existing resource into state (not created by Terraform)
terraform import aws_s3_bucket.assets acme-prod-assets

# Remove resource from state without destroying it
terraform state rm aws_s3_bucket.legacy

# Move resource between modules
terraform state mv module.old.aws_instance.web module.new.aws_instance.web

# List all resources in state
terraform state list
```

## Gotchas
- Never manually edit `.tfstate` files — use `terraform state` commands
- State files contain plaintext secrets (database passwords, private keys) — ensure the S3 bucket is private and encrypted
- `terraform force-unlock <lock-id>` should only be used after confirming no other process holds the lock
- Workspace isolation (`terraform workspace`) is an alternative to separate state files but adds complexity — prefer separate state paths for production environments

## Related
- `terraform-drift-detection.md`
- `infrastructure-cost-tagging.md`
- `gitops.md`
