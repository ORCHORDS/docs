# terraform-remote-backend

**Issue:** Configuring Terraform remote state backends for team collaboration and locking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Local state files cause merge conflicts and make concurrent applies dangerous. Remote backends provide locking, versioning, and team access to state.

## Pattern / Solution
S3 + DynamoDB backend (AWS):
```hcl
# backend.tf
terraform {
  backend "s3" {
    bucket         = "myorg-terraform-state"
    key            = "production/eks/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:us-east-1:123456789:key/abc123"
    dynamodb_table = "terraform-state-locks"
  }
}
```

Create the S3 bucket and DynamoDB table (bootstrap with local state first):
```bash
aws s3api create-bucket \
  --bucket myorg-terraform-state \
  --region us-east-1 \
  --create-bucket-configuration LocationConstraint=us-east-1

aws s3api put-bucket-versioning \
  --bucket myorg-terraform-state \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket myorg-terraform-state \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'

aws dynamodb create-table \
  --table-name terraform-state-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

Terraform Cloud backend:
```hcl
terraform {
  cloud {
    organization = "myorg"
    workspaces {
      name = "production-eks"
    }
  }
}
```

Migrate existing local state to remote:
```bash
terraform init -migrate-state
```

Force-unlock after a crashed apply:
```bash
terraform force-unlock LOCK_ID
```

## Gotchas
- Never delete the state S3 bucket; enable MFA delete and object lock for protection
- State files contain plaintext secrets (passwords, private keys from resources); KMS encryption is mandatory
- Two engineers running `terraform apply` simultaneously will race even with DynamoDB locking if one uses `--lock=false`
- `terraform state rm` removes resources from state without destroying them — useful but irreversible
- Workspace isolation requires separate state keys; the workspace name is interpolated automatically in Terraform Cloud but must be manual in S3

## Related
- `terraform-modules-structure.md`
- `terraform-workspace-patterns.md`
- `terraform-state-management.md`
