# terratest-patterns

**Issue:** Structuring Terratest suites for maintainability and reliable infrastructure validation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Terratest tests are slow, fragile, and leave orphaned cloud resources when they fail mid-test.

## Pattern / Solution
**Always defer Destroy first** so cleanup runs even on panic:

```go
func TestVPCModule(t *testing.T) {
  t.Parallel()
  opts := &terraform.Options{
    TerraformDir: "../../modules/vpc",
    Vars: map[string]interface{}{ "env": "test" },
  }
  defer terraform.Destroy(t, opts)
  terraform.InitAndApply(t, opts)

  vpcID := terraform.Output(t, opts, "vpc_id")
  vpc := aws.GetVpcById(t, vpcID, "us-east-1")
  assert.True(t, aws.IsVpcWithCidr(vpc, "10.0.0.0/16"))
}
```

**Stage tests** using build tags so you can run cheap unit tests separately from expensive integration tests:

```go
//go:build integration
```

```bash
go test -v -tags=integration ./test/...
```

**Use unique naming** with `random.UniqueId()` to avoid collisions when parallel runs overlap.

**Retry transient AWS errors** with `retry.DoWithRetry`.

## Gotchas
- Never run `t.Parallel()` without ensuring resources have unique names — parallel runs sharing a name cause conflicts.
- Set a test timeout (`-timeout 30m`) to prevent indefinitely stuck tests from consuming quota.
- Store Terraform state in S3/GCS for team consistency, not local files.

## Related
- test-driven-infrastructure
- test-environment-management
- test-containers-docker
