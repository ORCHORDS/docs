# test-driven-infrastructure

**Issue:** Applying TDD principles to infrastructure-as-code to catch configuration errors before deployment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Terraform or Pulumi changes are applied to staging without verification, breaking the environment and causing incidents.

## Pattern / Solution
Write tests that validate infrastructure configuration before and after `apply`:

**Before apply (static analysis):**
- `terraform validate` — syntax and schema check.
- `tflint` — linting for provider-specific issues.
- `checkov` — security and compliance scanning of Terraform plans.

```bash
checkov -d . --framework terraform --check CKV_AWS_20,CKV_AWS_57
```

**After apply (integration):**
Use Terratest (Go) to spin up real resources, assert on their properties, then destroy them:

```go
func TestS3BucketIsPrivate(t *testing.T) {
  opts := &terraform.Options{ TerraformDir: "../modules/storage" }
  defer terraform.Destroy(t, opts)
  terraform.InitAndApply(t, opts)
  bucketID := terraform.Output(t, opts, "bucket_id")
  assert.Equal(t, "private", aws.GetS3BucketACL(t, "us-east-1", bucketID))
}
```

## Gotchas
- Terratest tests create real cloud resources and incur costs — always `defer Destroy`.
- Slow feedback loop (minutes to apply/destroy) means infrastructure tests belong in a nightly pipeline, not per-PR.
- Use a dedicated test AWS account/GCP project to isolate test resources from production.

## Related
- terratest-patterns
- test-environment-management
- chaos-testing-approaches
