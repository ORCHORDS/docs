# Infrastructure as Code Testing — Terratest and Checkov

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Terraform changes are reviewed by reading HCL diffs in pull
requests — no automated validation beyond `terraform plan`. Security
misconfigurations (public S3 buckets, open security groups, unencrypted
databases) are discovered in production, not in CI. Infrastructure
changes break applications because the provisioned resources do not
match what the application expects. You cannot confidently refactor
Terraform modules because there are no tests to verify behavior.

## Context

Infrastructure as Code (IaC) testing validates infrastructure
definitions before they are deployed, catching misconfigurations,
security violations, and functional bugs early. The testing pyramid
for IaC has three layers: static analysis (Checkov, tfsec) for policy
and security scanning without deploying anything, unit testing
(terraform test, tftest) for validating module logic in isolation, and
integration testing (Terratest) for deploying real infrastructure and
verifying it works. In 2026, the standard practice is to run static
analysis in CI on every PR and integration tests on a schedule (nightly)
or before production deployments.

## IaC testing pyramid

```
              ┌─────────────────┐
              │  Integration    │  Terratest (Go)
              │  (deploy & test)│  Deploy real infra, verify, destroy
              ├─────────────────┤
              │  Unit / Plan    │  terraform test, tftest
              │  (plan only)    │  Validate plan output without deploy
              ├─────────────────┤
              │  Static Analysis│  Checkov, tfsec, Trivy
              │  (no deploy)    │  Policy, security, compliance checks
              └─────────────────┘
    Speed:     Slow (minutes)        Fast (seconds)
    Cost:      Real cloud resources  Free (no resources)
    Coverage:  Functional behavior   Configuration correctness
```

## Static analysis — Checkov

Checkov scans IaC templates (Terraform, CloudFormation, Kubernetes,
Helm, Docker) for security misconfigurations and compliance violations
without deploying anything.

```bash
# Scan Terraform directory
checkov -d ./terraform/ --framework terraform

# Scan with specific compliance framework
checkov -d ./terraform/ --check CIS_AWS

# Output as SARIF for GitHub Code Scanning
checkov -d ./terraform/ -o sarif > results.sarif
```

### CI integration

```yaml
# GitHub Actions
- name: Run Checkov
  uses: bridgecrewio/checkov-action@v12
  with:
    directory: ./terraform
    framework: terraform
    soft_fail: false
    output_format: sarif
```

### Custom policies

```python
# custom_checks/s3_versioning.py
from checkov.terraform.checks.resource.base_resource_check import (
    BaseResourceCheck,
)
from checkov.common.models.enums import CheckResult

class S3VersioningEnabled(BaseResourceCheck):
    def __init__(self):
        name = "Ensure S3 bucket has versioning enabled"
        id = "CUSTOM_S3_001"
        supported_resources = ["aws_s3_bucket"]
        super().__init__(name=name, id=id,
                         supported_resource_type=supported_resources)

    def scan_resource_conf(self, conf):
        versioning = conf.get("versioning", [{}])
        if isinstance(versioning, list) and versioning:
            enabled = versioning[0].get("enabled", [False])
            if enabled == [True] or enabled is True:
                return CheckResult.PASSED
        return CheckResult.FAILED

check = S3VersioningEnabled()
```

### Common Checkov checks

| Check ID | Description |
|---|---|
| CKV_AWS_18 | Ensure S3 bucket has access logging enabled |
| CKV_AWS_19 | Ensure S3 bucket has server-side encryption |
| CKV_AWS_21 | Ensure S3 bucket has versioning enabled |
| CKV_AWS_23 | Ensure every security group rule has a description |
| CKV_AWS_145 | Ensure RDS database is encrypted at rest |
| CKV_AWS_337 | Ensure EKS cluster uses a supported Kubernetes version |

## Integration testing — Terratest

Terratest (Go) deploys real infrastructure, runs assertions against it,
and destroys it afterward:

```go
package test

import (
    "testing"
    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/gruntwork-io/terratest/modules/http-helper"
    "github.com/stretchr/testify/assert"
)

func TestWebServer(t *testing.T) {
    t.Parallel()

    opts := &terraform.Options{
        TerraformDir: "../modules/web-server",
        Vars: map[string]interface{}{
            "instance_type": "t3.micro",
            "environment":   "test",
        },
    }

    // Deploy infrastructure
    defer terraform.Destroy(t, opts)
    terraform.InitAndApply(t, opts)

    // Get outputs
    url := terraform.Output(t, opts, "server_url")
    instanceId := terraform.Output(t, opts, "instance_id")

    // Verify the server responds
    http_helper.HttpGetWithRetry(t, url, nil, 200,
        "Hello, World", 10, 5*time.Second)

    // Verify instance properties
    assert.NotEmpty(t, instanceId)
}
```

### Terratest patterns

```go
// Test database module
func TestDatabase(t *testing.T) {
    t.Parallel()

    opts := &terraform.Options{
        TerraformDir: "../modules/database",
        Vars: map[string]interface{}{
            "engine":         "postgres",
            "engine_version": "17",
            "instance_class": "db.t3.micro",
        },
    }

    defer terraform.Destroy(t, opts)
    terraform.InitAndApply(t, opts)

    endpoint := terraform.Output(t, opts, "endpoint")
    port := terraform.Output(t, opts, "port")

    // Verify database is reachable
    assert.NotEmpty(t, endpoint)
    assert.Equal(t, "5432", port)
}
```

## Tool comparison

| Feature | Checkov | tfsec/Trivy | Terratest | terraform test |
|---|---|---|---|---|
| Type | Static analysis | Static analysis | Integration test | Unit test |
| Language | Python | Go | Go | HCL |
| Deploys infra | No | No | Yes | No (plan only) |
| Custom rules | Python checks | Rego/YAML | Go code | HCL assertions |
| IaC support | TF, CFN, K8s, Docker | TF, CFN, K8s | TF, Docker, K8s | Terraform only |
| Compliance | CIS, PCI, SOC 2 | CIS, AWS best practices | N/A | N/A |
| CI speed | Seconds | Seconds | Minutes | Seconds |

## Anti-patterns

- **No static analysis** — relying on `terraform plan` review for
  security. Humans miss misconfigured security groups, unencrypted
  databases, and overly permissive IAM policies. Automate with Checkov.
- **Integration tests without cleanup** — Terratest creates real cloud
  resources. Without `defer terraform.Destroy()`, failed tests leave
  orphaned resources that accumulate cost.
- **Testing only the happy path** — testing that infrastructure deploys
  successfully without verifying it works correctly. Assert on endpoints,
  connectivity, permissions, and encryption — not just deployment status.
- **Skipping tests for "simple" changes** — a "simple" security group
  rule change can open a port to the internet. Static analysis catches
  these automatically.

## Gotchas

- **Terratest parallel isolation** — parallel tests must use unique
  resource names to avoid conflicts. Use random suffixes or unique
  test IDs in resource naming.
- **Cloud cost of integration tests** — Terratest deploys real
  infrastructure. Use the smallest instance types, shortest test
  windows, and always clean up. Set budget alerts for test accounts.
- **Checkov false positives** — some Checkov rules may not apply to
  your architecture. Use inline skip comments
  (`# checkov:skip=CKV_AWS_18:Reason`) for documented exceptions.
- **State file isolation** — integration tests must use isolated state
  files (local backend or unique S3 keys) to avoid corrupting
  production state.

## Verification

- Checkov runs on every PR and blocks merge on critical findings.
- All Terraform modules have at least static analysis coverage.
- Critical infrastructure modules have Terratest integration tests.
- Integration tests run nightly or before production deployments.
- Test accounts have budget alerts to catch resource leaks.
- Custom Checkov policies enforce organization-specific standards.

## Related

- `documentation/categories/infra/terraform-patterns.md`
- `documentation/categories/infra/ci-cd-pipeline-design.md`
- `documentation/categories/security/container-security.md`

## Source URLs (verified 2026-08-16)

- Terratest and Checkov guide — https://www.devopsroles.com/infrastructure-testing-terratest-checkov/
- Terraform scanning tools 2026 — https://spacelift.io/blog/terraform-scanning-tools
- IaC testing best practices — https://gigatester.com/infrastructure-as-code-testing/
- Terraform testing guide — https://oneuptime.com/blog/post/2026-02-02-terraform-testing/view
