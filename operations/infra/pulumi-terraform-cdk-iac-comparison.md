# Infrastructure as Code — Pulumi vs Terraform vs AWS CDK Comparison

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team writes Terraform HCL for all infrastructure. A senior
engineer needs to dynamically generate 40 IAM policies from a JSON
config file but HCL's `for_each` and `dynamic` blocks produce
unreadable nested expressions. Testing requires deploying real
infrastructure because HCL has no mocking layer. Meanwhile, another
team uses AWS CDK but cannot provision their GCP resources through
it because CDK only targets CloudFormation.

## Context

Three IaC tools dominate in 2026: Terraform (declarative HCL,
multi-cloud), Pulumi (general-purpose languages, multi-cloud), and
AWS CDK (TypeScript/Python compiling to CloudFormation, AWS-only).
Terraform has the largest provider ecosystem but HCL limits
abstraction and testing. Pulumi uses TypeScript, Python, Go, or C#
with unit-testable infrastructure code and encrypts secrets in
state by default. AWS CDK provides high-level constructs for AWS
services but inherits CloudFormation's stack size limits and slower
rollback. The choice depends on multi-cloud requirements, team
language preferences, and testing needs.

## Tool comparison

```
                    Terraform           Pulumi              AWS CDK
──────────────────────────────────────────────────────────────────────
Language:           HCL (DSL)           TS/Python/Go/C#     TS/Python/Java/C#
Cloud support:      Multi-cloud         Multi-cloud         AWS only
State storage:      S3/TF Cloud/local   Pulumi Cloud/S3     CloudFormation
Secrets in state:   Plaintext default   Encrypted default   CF-managed
Unit testing:       Terratest (Go)      Native test runners CDK assertions
Drift detection:    terraform refresh   pulumi refresh      CF drift detection
Plan/preview:       terraform plan      pulumi preview      cdk diff
Provider count:     3000+               150+                AWS services only
Learning curve:     Low (new DSL)       Medium (SDK)        Medium (constructs)
```

## Terraform (HCL)

```hcl
# Declarative resource definition
resource "aws_s3_bucket" "data" {
  bucket = "my-data-bucket"

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}
```

```
Terraform strengths:
  → Largest provider ecosystem (3000+ providers)
  → HCL is purpose-built — less footgun surface
  → Mature module registry for reusable components
  → terraform plan gives clear execution preview

Terraform limitations:
  → HCL limits abstraction and composition at scale
  → No mocking layer — Terratest deploys real infra
  → Secrets stored in plaintext in state by default
  → Scheduled drift detection requires TF Cloud (paid)
```

## Pulumi (general-purpose languages)

```typescript
import * as aws from "@pulumi/aws";

const bucket = new aws.s3.Bucket("data", {
  tags: {
    Environment: "production",
    ManagedBy: "pulumi",
  },
});

const versioning = new aws.s3.BucketVersioningV2("data", {
  bucket: bucket.id,
  versioningConfiguration: { status: "Enabled" },
});

export const bucketName = bucket.id;
```

```typescript
// Unit test with mocking — no cloud calls needed
import * as pulumi from "@pulumi/pulumi";
import { describe, it, expect } from "vitest";

pulumi.runtime.setMocks({
  newResource: (args) => ({ id: `${args.name}-id`, state: args.inputs }),
  call: (args) => args.inputs,
});

describe("S3 Bucket", () => {
  it("has versioning enabled", async () => {
    const { bucket } = await import("./index");
    const tags = await new Promise((resolve) =>
      bucket.tags.apply(resolve)
    );
    expect(tags?.ManagedBy).toBe("pulumi");
  });
});
```

```
Pulumi strengths:
  → Full language power (loops, conditionals, classes)
  → Unit tests with mocking layer — no real infra needed
  → Secrets encrypted in state by default
  → Policy-as-code (CrossGuard) in same language

Pulumi limitations:
  → Smaller provider ecosystem than Terraform
  → Language power can over-engineer simple infra
  → Pulumi Cloud SaaS default for state (self-hosted option exists)
```

## AWS CDK

```typescript
import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";

export class DataStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string) {
    super(scope, id);

    new s3.Bucket(this, "DataBucket", {
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
  }
}
```

```
CDK strengths:
  → High-level constructs abstract AWS complexity
  → Fine-grained and snapshot assertions against synth output
  → No state file to manage (CloudFormation owns state)
  → Tight integration with AWS services

CDK limitations:
  → AWS only — no multi-cloud
  → Inherits CloudFormation stack size limits (500 resources)
  → Slower rollback on failures (CF stack rollback)
  → Coarser drift detection than Terraform/Pulumi
```

## When to pick each tool

```
Pick Terraform when:
  → Multi-cloud with large provider needs
  → Ops-oriented teams preferring config over code
  → Need mature module ecosystem and community
  → Simple infrastructure definitions

Pick Pulumi when:
  → Complex conditional/loop logic in infra
  → Teams wanting tests, infra, and policy in one language
  → Multi-cloud with software-engineering workflow
  → Need encrypted secrets in state by default

Pick AWS CDK when:
  → AWS-only infrastructure
  → Want high-level construct abstractions
  → Teams already invested in CloudFormation
  → Need CDK Pipelines for CI/CD
```

## Anti-patterns

- **Storing Terraform state locally** — local state files are not
  shared, not locked, and not backed up. Use remote backends
  (S3 + DynamoDB, Terraform Cloud) for all team work.
- **Over-engineering with Pulumi** — general-purpose language power
  can lead to class hierarchies and abstractions that are harder
  to understand than equivalent declarative config. Simple infra
  should remain simple.
- **CDK stacks exceeding CloudFormation limits** — stacks with
  500+ resources hit template size caps. Split into nested stacks
  or separate stacks before reaching the limit.
- **No drift detection schedule** — all three tools support drift
  detection but none run it automatically by default. Schedule
  periodic `refresh`/`diff` runs in CI.

## Gotchas

- **Terraform state contains secrets in plaintext** — database
  passwords, API keys, and other sensitive values are stored
  unencrypted in state. Use remote backends with encryption at
  rest and restrict state file access.
- **Pulumi Cloud default** — Pulumi uses its SaaS for state by
  default. Self-hosted backends (S3, Azure Blob, GCS) are
  available but require explicit configuration.
- **CDK CloudFormation rollback** — failed deployments trigger
  full stack rollback, which can take minutes for large stacks.
  Terraform and Pulumi handle partial failures more granularly.
- **Mixing IaC tools** — some teams use Terraform for networking
  and Pulumi for application infra. This works but requires
  careful state boundary management and cross-tool output sharing.

## Verification

- Remote state backend configured with encryption and locking.
- Drift detection scheduled in CI (weekly minimum).
- Unit tests cover critical infrastructure logic.
- Secrets management uses tool-native encryption or external vaults.
- Stack/project sizes monitored against platform limits.
- IaC code reviewed with same rigor as application code.

## Related

- `documentation/categories/infra/terraform-state-management-backends.md`
- `documentation/categories/infra/iac-testing-terratest-checkov.md`
- `documentation/categories/deploy/argocd-flux-gitops-deployment.md`

## Source URLs (verified 2026-08-16)

- Pulumi vs Terraform Comparison — https://www.pulumi.com/docs/iac/comparisons/terraform/
- Pulumi vs AWS CDK Comparison — https://www.pulumi.com/docs/iac/comparisons/aws-cdk/
- Terraform vs Pulumi vs AWS CDK: 2025 Benchmark — https://sanj.dev/post/terraform-pulumi-aws-cdk-iac-comparison
- Unit Testing Pulumi Programs — https://www.pulumi.com/docs/iac/guides/testing/unit/
