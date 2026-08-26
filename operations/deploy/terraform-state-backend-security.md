# Terraform State Backend Security

## Overview

Terraform state backend security is critical for protecting infrastructure-as-code configurations and sensitive data. The state file contains all your infrastructure information, including secrets, which makes proper backend security essential for any production environment.

## Symptom

Common security issues include unauthorized access to state files, concurrent modifications causing conflicts, and exposure of sensitive credentials in unencrypted storage. Teams often experience state corruption, accidental deletions, or compromised infrastructure due to inadequate backend protection measures.

## Gotchas

- S3 bucket policies must explicitly allow Terraform operations
- DynamoDB lock table requires proper IAM permissions
- State encryption keys must be rotated regularly
- Workspaces provide isolation but aren't a security boundary
- Remote state sharing creates additional attack vectors

## Secure S3 + DynamoDB Backend Configuration

```hcl
terraform {
  backend "s3" {
    bucket         = "my-terraform-state-bucket"
    key            = "prod/terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true
    dynamodb_table = "terraform-lock-table"

    # Required for remote state sharing
    profile = "terraform-prod"
  }
}
```

## IAM Least Privilege Implementation

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-terraform-state-bucket",
        "arn:aws:s3:::my-terraform-state-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:us-west-2:123456789012:table/terraform-lock-table"
    }
  ]
}
```

## Encryption Configuration

```hcl
# S3 bucket with encryption
resource "aws_s3_bucket" "terraform_state" {
  bucket = "my-terraform-state-bucket"

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }

  # Enable versioning
  versioning {
    enabled = true
  }

  # Block public access
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for locking
resource "aws_dynamodb_table"
