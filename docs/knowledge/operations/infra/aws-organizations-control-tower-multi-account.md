# AWS Organizations + Control Tower: Multi-Account Strategy

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
All workloads share a single AWS account, so a developer with S3 write access can inadvertently
touch production data; compliance audits fail because there is no blast-radius boundary between
environments or between business units.

## Context
AWS Organizations groups accounts into Organizational Units (OUs) and applies Service Control
Policies (SCPs) as guardrails at the OU level. AWS Control Tower automates landing zone
provisioning — it creates a management account, a log archive account, and an audit account,
then enrolls new accounts via Account Factory.
Together they provide policy enforcement, consolidated billing, and centralized CloudTrail
without requiring per-account configuration. Terraform's `aws` provider and the `aws_organizations_*`
resources can drive this declaratively after Control Tower's baseline is deployed.

## OU Hierarchy Design

```
Root
├── Security (management, log-archive, audit — created by Control Tower)
├── Infrastructure
│   ├── Shared Services (DNS, artifact registries, internal PKI)
│   └── Networking (Transit Gateway, Direct Connect)
├── Workloads
│   ├── Production
│   │   ├── orchords-prod
│   │   └── payments-prod
│   └── NonProduction
│       ├── orchords-staging
│       ├── orchords-dev
│       └── sandbox-*
└── Suspended          # Accounts pending closure
```

This hierarchy maps SCPs and tag policies to OUs, not individual accounts, so adding a new
account in `NonProduction` automatically inherits developer-friendly (but safe) guardrails.

## Terraform: Account Vending via Account Factory

Control Tower's Account Factory can be triggered from Terraform using the
`aws_servicecatalog_provisioned_product` resource, which calls the Account Factory Service
Catalog product.

```hcl
# terraform/accounts/staging.tf
resource "aws_servicecatalog_provisioned_product" "staging" {
  name                     = "orchords-staging"
  product_id               = data.aws_servicecatalog_product.account_factory.id
  provisioning_artifact_id = data.aws_servicecatalog_product.account_factory.provisioning_artifact_id

  provisioning_parameters {
    key   = "AccountName"
    value = "orchords-staging"
  }
  provisioning_parameters {
    key   = "AccountEmail"
    value = "aws+orchords-staging@example.com"
  }
  provisioning_parameters {
    key   = "ManagedOrganizationalUnit"
    value = "NonProduction"
  }
  provisioning_parameters {
    key   = "SSOUserFirstName"
    value = "Platform"
  }
  provisioning_parameters {
    key   = "SSOUserLastName"
    value = "Team"
  }
  provisioning_parameters {
    key   = "SSOUserEmail"
    value = "platform@example.com"
  }

  timeouts {
    create = "60m"
    update = "60m"
    delete = "60m"
  }

  tags = {
    Environment = "staging"
    Owner       = "platform"
    CostCenter  = "eng-platform"
  }
}
```

## Service Control Policies

SCPs use IAM policy JSON syntax but apply at the OU/account level before IAM policies are
evaluated. A `Deny` in an SCP cannot be overridden by any account-level `Allow`.

```hcl
# terraform/scps/production-guardrails.tf
resource "aws_organizations_policy" "deny_root_usage" {
  name        = "DenyRootUsage"
  description = "Prevent root account activity except in break-glass scenarios"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DenyRootActions"
        Effect   = "Deny"
        Action   = ["*"]
        Resource = ["*"]
        Condition = {
          StringLike = {
            "aws:PrincipalArn" = ["arn:aws:iam::*:root"]
          }
        }
      }
    ]
  })
}

resource "aws_organizations_policy" "deny_region_outside_approved" {
  name        = "DenyRegionsOutsideApproved"
  description = "Restrict workloads to approved regions only"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DenyUnapprovedRegions"
        Effect   = "Deny"
        NotAction = [
          "iam:*", "sts:*", "route53:*",
          "support:*", "organizations:*",
          "cloudfront:*", "waf:*"
        ]
        Resource = ["*"]
        Condition = {
          StringNotEquals = {
            "aws:RequestedRegion" = ["us-east-1", "us-west-2", "eu-west-1"]
          }
        }
      }
    ]
  })
}

resource "aws_organizations_policy_attachment" "production_guardrails" {
  policy_id = aws_organizations_policy.deny_region_outside_approved.id
  target_id = aws_organizations_organizational_unit.production.id
}
```

## Cross-Account IAM Role Assumption Pattern

Workloads in member accounts assume a role in the shared-services account to access shared
resources (ECR, Route 53, internal artifact stores) without peering VPCs or duplicating access.

```typescript
// scripts/assume-cross-account-role.ts
import { STSClient, AssumeRoleCommand } from "@aws-sdk/client-sts";
import { fromTemporaryCredentials } from "@aws-sdk/credential-providers";

const SHARED_SERVICES_ACCOUNT = "111122223333";

export function sharedServicesCredentials(roleSession: string) {
  return fromTemporaryCredentials({
    params: {
      RoleArn: `arn:aws:iam::${SHARED_SERVICES_ACCOUNT}:role/OrchardsSharedServicesAccess`,
      RoleSessionName: roleSession,
      DurationSeconds: 3600,
    },
    clientConfig: { region: "us-east-1" },
  });
}

// Usage: push an image to shared ECR from the staging account
import { ECRClient, GetAuthorizationTokenCommand } from "@aws-sdk/client-ecr";

const ecr = new ECRClient({
  region: "us-east-1",
  credentials: sharedServicesCredentials("staging-ci-push"),
});

const { authorizationData } = await ecr.send(new GetAuthorizationTokenCommand({}));
```

## Consolidated Billing and Cost Allocation Tags

Tag policies enforce consistent tagging so Cost Explorer can slice spending by team, service, and environment.

```hcl
# terraform/scps/tag-policy.tf
resource "aws_organizations_policy" "tag_policy" {
  name = "RequiredTagPolicy"
  type = "TAG_POLICY"

  content = jsonencode({
    tags = {
      Environment = {
        tag_key = {
          "@@assign" = "Environment"
        }
        tag_value = {
          "@@assign" = ["production", "staging", "dev", "sandbox"]
        }
        enforced_for = {
          "@@assign" = [
            "ec2:instance", "rds:db", "s3:bucket",
            "lambda:function", "ecs:service"
          ]
        }
      }
      CostCenter = {
        tag_key = {
          "@@assign" = "CostCenter"
        }
        enforced_for = {
          "@@assign" = ["ec2:instance", "rds:db", "lambda:function"]
        }
      }
    }
  })
}

resource "aws_organizations_policy_attachment" "tag_policy_root" {
  policy_id = aws_organizations_policy.tag_policy.id
  target_id = data.aws_organizations_organization.current.roots[0].id
}
```

## Anti-patterns
- Putting all environments in one account and relying on IAM alone for blast-radius isolation
- Using a single IAM user (human) to manage the management account — use AWS SSO with MFA
- Attaching SCPs directly to individual accounts instead of OUs — makes policy auditing fragile
- Skipping the Suspended OU — decommissioned accounts left in active OUs still incur SCP evaluation overhead and show in billing
- Not enabling CloudTrail in all regions in all accounts — Control Tower's CloudTrail is org-level but only covers regions you enable

## Gotchas
- Account Factory provisioning takes 15-30 minutes; Terraform apply will block until the Service Catalog product reaches `AVAILABLE`
- The management account is exempt from SCPs by design — never deploy workloads there
- `aws_organizations_policy_attachment` requires the management account credentials, not the member account
- Control Tower uses its own internal Terraform state; manually changing resources Control Tower manages will cause reconciliation conflicts on the next Landing Zone update
- Billing consolidation lag: new accounts may take up to 24 hours to roll up into the management account's Cost Explorer view

## Verification
```bash
# List all accounts and their OUs
aws organizations list-accounts --output table

# Verify SCP is attached to Production OU
aws organizations list-policies-for-target \
  --target-id $(aws organizations list-organizational-units-for-parent \
    --parent-id r-xxxx --query "OrganizationalUnits[?Name=='Production'].Id" --output text) \
  --filter SERVICE_CONTROL_POLICY

# Confirm tag policy enforcement (dry-run)
aws organizations describe-effective-policy \
  --policy-type TAG_POLICY \
  --target-id <account-id>
```

## Related
- `/documentation/docs/policies/infra/aws-iam-least-privilege.md`
- `/documentation/docs/policies/infra/aws-cloudtrail-audit.md`
- `/documentation/docs/policies/infra/aws-cost-explorer-tagging.md`
- `/documentation/docs/policies/infra/multi-cloud-strategy.md`
- `/documentation/docs/policies/infra/iac-best-practices.md`

## Sources
- https://docs.aws.amazon.com/controltower/latest/userguide/what-is-control-tower.html
- https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/organizations_policy
- https://docs.aws.amazon.com/controltower/latest/userguide/account-factory.html
