# pulumi-vs-terraform

**Issue:** Choosing between Pulumi and Terraform for infrastructure as code
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams adopting IaC often choose between HCL-based Terraform and Pulumi's general-purpose language support. The choice affects testing, abstraction capability, and team skill requirements.

## Pattern / Solution
Decision matrix:

| Criterion | Terraform | Pulumi |
|-----------|-----------|--------|
| Language | HCL (declarative) | Python, TypeScript, Go, C# |
| Testing | Terratest (Go) | Built-in unit tests |
| Loops/conditionals | Limited (`count`, `for_each`) | Full language power |
| State backend | S3, Terraform Cloud | Pulumi Cloud, S3, Azure Blob |
| Provider coverage | Largest ecosystem | Imports Terraform providers |
| Learning curve | Low (HCL is simple) | Higher (need programming language) |
| Dynamic config | Hard (data sources) | Natural (functions, APIs) |
| Refactoring | Disruptive (address changes) | Easier with aliases |

Pulumi example (TypeScript):
```typescript
import * as aws from "@pulumi/aws";

const bucket = new aws.s3.Bucket("assets", {
    versioning: { enabled: true },
    tags: { Environment: pulumi.getStack() },
});

// Dynamic resource creation — hard in Terraform
const zones = ["us-east-1a", "us-east-1b", "us-east-1c"];
const subnets = zones.map((az, i) =>
    new aws.ec2.Subnet(`subnet-${i}`, {
        vpcId: vpc.id,
        cidrBlock: `10.0.${i}.0/24`,
        availabilityZone: az,
    })
);
```

Pulumi unit test:
```typescript
import * as testing from "@pulumi/pulumi/testing";

it("bucket has versioning", async () => {
    const resources = await testing.run(() => import("./index"));
    const bucket = resources.find(r => r instanceof aws.s3.Bucket);
    expect(bucket?.versioning?.enabled).toBe(true);
});
```

## Gotchas
- Pulumi state is encrypted at rest but the Pulumi Cloud free tier has limited history retention
- Importing Terraform providers into Pulumi uses `pulumi convert --from terraform` — the result needs cleanup
- Terraform provider ecosystem is larger; some niche providers only exist for Terraform
- Pulumi's `stack output` is equivalent to Terraform's `output` — needed for cross-stack references
- Both tools have the same fundamental limitation: they cannot manage resources that predate their state file without import

## Related
- `terraform-modules-structure.md`
- `terraform-remote-backend.md`
- `terraform-testing-terratest.md`
