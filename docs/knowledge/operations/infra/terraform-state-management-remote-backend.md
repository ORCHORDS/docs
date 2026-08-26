# Terraform State Management — Remote Backends, Locking, and Segmentation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Two engineers run `terraform apply` simultaneously and one overwrites
the other's changes, leaving infrastructure in an inconsistent state.
Your state file is stored locally on a developer's laptop — when they
go on vacation, nobody else can run Terraform. A failed apply leaves
the state file corrupted and you have no backup. Your single state file
contains 2,000 resources across production, staging, and development,
and a plan takes 10 minutes to complete.

## Context

Terraform state is a JSON file that maps your configuration to
real-world infrastructure resources. It tracks resource IDs, metadata,
and dependencies, enabling Terraform to determine what changes are
needed. In 2026, remote backends (S3 + state locking, HCP Terraform,
GCS, Azure Blob) are mandatory for team use — local state is only
acceptable for personal experiments. State locking prevents concurrent
modifications, and state segmentation (separate state files per
environment/service) limits the blast radius of errors. Terraform 1.11+
introduced S3-native locking via `use_lockfile = true`, replacing the
previous DynamoDB-based locking approach.

## Remote backend configuration

```hcl
# S3 backend with native locking (Terraform 1.11+)
terraform {
  backend "s3" {
    bucket       = "myorg-terraform-state"
    key          = "prod/networking/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true  # S3-native locking (replaces DynamoDB)

    # KMS encryption for state at rest
    kms_key_id = "arn:aws:kms:us-east-1:123456789:key/abc-123"
  }
}

# S3 backend with DynamoDB locking (legacy, pre-1.11)
terraform {
  backend "s3" {
    bucket         = "myorg-terraform-state"
    key            = "prod/networking/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}

# GCS backend
terraform {
  backend "gcs" {
    bucket = "myorg-terraform-state"
    prefix = "prod/networking"
  }
}
```

## State bucket setup

```hcl
# Bootstrap: create state bucket (run once, local state)
resource "aws_s3_bucket" "terraform_state" {
  bucket = "myorg-terraform-state"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.terraform.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

## State segmentation

```
Single state (BAD):
  terraform.tfstate → 2000 resources, 10 min plan
  → One mistake affects all environments
  → One engineer blocks all others

Segmented state (GOOD):
  prod/networking/terraform.tfstate    → ~50 resources
  prod/compute/terraform.tfstate       → ~100 resources
  prod/database/terraform.tfstate      → ~30 resources
  staging/networking/terraform.tfstate → ~50 resources
  staging/compute/terraform.tfstate    → ~100 resources

Segmentation strategies:
  By environment:  prod/, staging/, dev/
  By service:      networking/, compute/, database/
  By team:         platform/, application/, data/
  Combined:        prod/platform/networking/

Cross-state references:
  # Read outputs from another state file
  data "terraform_remote_state" "networking" {
    backend = "s3"
    config = {
      bucket = "myorg-terraform-state"
      key    = "prod/networking/terraform.tfstate"
      region = "us-east-1"
    }
  }

  # Use outputs
  subnet_id = data.terraform_remote_state.networking.outputs.private_subnet_id
```

## State locking

```
How locking works:
  1. terraform plan/apply acquires lock
  2. Lock record created (S3 lockfile or DynamoDB item)
  3. Other terraform commands wait or fail
  4. On completion, lock is released

Lock stuck? (CI crashed mid-apply):
  # Check who holds the lock
  terraform plan  # Shows lock holder info

  # Force unlock (DANGER: verify no one is running)
  terraform force-unlock LOCK_ID

  # Always verify state is consistent after force-unlock
  terraform plan  # Should show no unexpected changes
```

## Anti-patterns

- **Local state for team projects** — storing `terraform.tfstate`
  on a developer's laptop. No locking, no backup, no collaboration.
  Always use a remote backend with locking for shared projects.
- **Single state for everything** — one state file containing all
  environments and services. Plan time is slow, blast radius is
  unlimited, and concurrent work is impossible. Segment state by
  environment and service.
- **State in version control** — committing `terraform.tfstate` to
  git. State files contain secrets (database passwords, API keys)
  and should never be in git. Use `.gitignore` for `*.tfstate*`.
- **No state versioning** — using an S3 bucket without versioning
  enabled. If state becomes corrupted, you have no way to recover.
  Always enable bucket versioning for state recovery.

## Gotchas

- **State contains secrets** — Terraform state stores resource
  attributes in plaintext, including database passwords, API keys,
  and certificates. Encrypt state at rest (S3 SSE-KMS) and
  restrict access with IAM policies.
- **State drift** — manual changes to infrastructure create drift
  between state and reality. Run `terraform plan` regularly (or in
  CI) to detect drift. Use `terraform refresh` to update state
  without applying changes.
- **Backend migration** — changing from local to remote backend or
  between remote backends requires `terraform init -migrate-state`.
  This is a one-time operation but must be coordinated across the
  team.
- **Circular remote state dependencies** — State A reads from
  State B, and State B reads from State A. This creates a
  dependency cycle that prevents either from being applied first.
  Design state boundaries to avoid circular references.

## Verification

- All team Terraform projects use remote backends with locking.
- State bucket has versioning, encryption, and public access blocked.
- State is segmented by environment and service domain.
- CI/CD pipeline acquires lock before apply and releases after.
- State files are excluded from version control (`.gitignore`).
- Drift detection runs on a schedule (daily or weekly).

## Related

- `documentation/docs/policies/infra/iac-testing-terratest-checkov.md`
- `documentation/docs/policies/deploy/infrastructure-drift-detection-remediation.md`
- `documentation/docs/policies/infra/secrets-management-vault-patterns.md`

## Source URLs (verified 2026-08-16)

- Terraform State Management Best Practices 2026 — https://hostingx.co.il/articles/terraform-state-management-guide
- Terraform State Lock: How It Works & Best Practices — https://spacelift.io/blog/terraform-state-lock
- Terraform State Management: Remote Backend Guide 2026 — https://blogs.pavanrangani.com/terraform-state-management-remote-backend-guide/
- Terraform State Best Practices for Teams 2026 — https://squareops.com/blog/terraform-state-management-best-practices-team-cicd/
