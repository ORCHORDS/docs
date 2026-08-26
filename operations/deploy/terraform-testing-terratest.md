# terraform-testing-terratest

**Issue:** Writing automated infrastructure tests with Terratest
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Terraform modules fail silently in unexpected ways — wrong security group rules, missing tags, incorrect AMI lookups. Terratest runs real infrastructure, validates it, then tears it down.

## Pattern / Solution
Basic Terratest structure:
```go
// test/vpc_test.go
package test

import (
    "testing"
    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/gruntwork-io/terratest/modules/aws"
    "github.com/stretchr/testify/assert"
)

func TestVpcModule(t *testing.T) {
    t.Parallel()

    terraformOptions := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
        TerraformDir: "../modules/vpc",
        Vars: map[string]interface{}{
            "cidr_block":   "10.99.0.0/16",
            "environment":  "test",
        },
        EnvVars: map[string]string{
            "AWS_DEFAULT_REGION": "us-east-1",
        },
    })

    defer terraform.Destroy(t, terraformOptions)
    terraform.InitAndApply(t, terraformOptions)

    vpcID := terraform.Output(t, terraformOptions, "vpc_id")
    assert.NotEmpty(t, vpcID)

    vpc := aws.GetVpcById(t, vpcID, "us-east-1")
    assert.Equal(t, "10.99.0.0/16", aws.GetCidrBlockOfVpc(t, vpc))
}
```

Test for HTTP endpoint reachability:
```go
func TestWebServerReturns200(t *testing.T) {
    url := terraform.Output(t, opts, "alb_dns_name")
    maxRetries := 10
    timeBetweenRetries := 10 * time.Second

    http_helper.HttpGetWithRetry(t,
        fmt.Sprintf("http://%s", url),
        nil, 200, "Hello World",
        maxRetries, timeBetweenRetries)
}
```

Run tests:
```bash
cd test
go test -v -run TestVpcModule -timeout 30m
```

## Gotchas
- Always use `defer terraform.Destroy()` as the first statement after `WithDefaultRetryableErrors` to ensure cleanup even on test failure
- Tests create real resources and cost real money; run in a dedicated test AWS account with billing alerts
- Parallel tests can hit AWS service limits; tune parallelism with `-parallel N` or rate limit providers
- Test timeouts must be generous (15-30min); infrastructure provisioning is slow
- Use `t.Helper()` in shared helpers so failure line numbers point to the caller, not the helper

## Related
- `terraform-modules-structure.md`
- `terraform-remote-backend.md`
- `pulumi-vs-terraform.md`
