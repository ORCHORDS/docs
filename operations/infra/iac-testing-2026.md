# iac-testing-2026

**Issue:** Terraform testing — 3 layers: unit + policy + integration
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your Terraform has no tests. Someone creates a public
S3 bucket. The auditor finds it. You wish you had
tests.

## Root cause
**IaC is code. Code needs tests.** Use 3 layers.

**Source:** Bits Lovers 2026:
https://www.bitslovers.com/terraform-testing-2026/

## The "3 testing layers" pattern

For Terraform testing:
1. **Unit:** `terraform test` (.tftest.hcl)
2. **Policy:** OPA / Conftest
3. **Integration:** Terratest (Go)

The 3 layers are a pyramid.

## The "test pyramid" pattern

For the layers:
- **Unit (most):** Fast, in-isolation
- **Policy (medium):** On plan JSON
- **Integration (least):** Real AWS

The pyramid is per resource.

## The "terraform test" pattern

For unit tests:
- **File:** `.tftest.hcl`
- **Location:** Module dir or `tests/`
- **Run:** `terraform test`
- **Mocks:** Mock providers
- **Run time:** Seconds

The unit test is the default.

## The "tftest.hcl" pattern

For a unit test:
```hcl
run "basic" {
  command = plan

  assert {
    condition     = aws_s3_bucket.this.bucket == "my-bucket"
    error_message = "Bucket name must be my-bucket"
  }

  assert {
    condition     = aws_s3_bucket.this.tags["Environment"] == "prod"
    error_message = "Must have prod environment tag"
  }
}
```

The test is declarative.

## The "OPA" pattern

For policy:
- **Rego:** OPA's language
- **Conftest:** Wraps OPA for tests
- **Input:** Terraform plan JSON
- **Output:** Pass / fail

The policy is the rules.

## The "Rego policy" pattern

For an S3 encryption policy:
```rego
package terraform.policies

deny[msg] {
  resource := input.resource.aws_s3_bucket[name]
  not resource.server_side_encryption_configuration
  msg := sprintf("S3 bucket %s must have encryption", [name])
}

deny[msg] {
  resource := input.resource.aws_db_instance[name]
  resource.engine == "postgres"
  not resource.final_snapshot_identifier
  msg := sprintf("RDS %s must have final snapshot", [name])
}
```

The policy is per resource.

## The "Conftest workflow" pattern

For pipeline:
```bash
# Generate plan JSON
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json

# Run policies
conftest test tfplan.json --policy policy/

# Output
# 9 tests, 7 passed, 0 warnings, 2 failures, 0 exceptions
```

The workflow is per PR.

## The "GitLab policy check" pattern

For CI:
```yaml
policy_check:
  extends: .terraform_base
  stage: policy-check
  image: alpine:3.19
  before_script:
    - apk add --no-cache curl terraform
    - curl -L https://github.com/open-policy-agent/conftest/releases/download/v0.50.0/conftest_0.50.0_Linux_x86_64.tar.gz | tar xz
    - mv conftest /usr/local/bin/
    - terraform init
  script:
    - terraform plan -out=tfplan.binary
    - terraform show -json tfplan.binary > tfplan.json
    - conftest test tfplan.json --policy policy/ --output github
```

The CI checks policy.

## The "Terratest" pattern

For integration:
- **Language:** Go
- **Deploys:** Real infra
- **Validates:** Via API calls
- **Tears down:** In defer
- **Cost:** Real AWS spend (transient)

The test is real.

## The "Terratest example" pattern

For an S3 test:
```go
func TestS3Bucket(t *testing.T) {
  terraformOptions := &terraform.Options{
    TerraformDir: "../modules/s3",
  }

  defer terraform.Destroy(t, terraformOptions)
  terraform.InitAndApply(t, terraformOptions)

  bucketID := terraform.Output(t, terraformOptions, "bucket_id")
  assert.NotEmpty(t, bucketID)

  // Verify encryption
  config := s3.GetEncryptionConfiguration(t, awsRegion, bucketID)
  assert.NotEmpty(t, config)
}
```

The test runs real infra.

## The "OPA via Terratest" pattern

For OPA + Terratest:
```go
func TestOPAEvalAllTerraformModules(t *testing.T) {
  cwd, _ := os.Getwd()
  opts := &test_structure.ValidationOptions{
    RootDir: cwd,
  }
  rulePath := filepath.Join(cwd, "../policies/enforce_tagging.rego")
  opaOpts := &opa.EvalOptions{
    FailMode: opa.FailUndefined,
    RulePath: rulePath,
  }
  test_structure.OPAEvalAllTerraformModules(
    t, opts, opaOpts, "data.enforce_tagging.allow")
}
```

The OPA runs on every module.

## The "OPA modes" pattern

For FailMode:
- **FailUndefined:** Fail if rule is undefined
- **FailDefined:** Fail if defined as false
- **Don't use:** Skip mode (no enforcement)

The mode is per policy.

## The "policy categories" pattern

For policies:
- **Security:** Encryption, no public S3, IAM
- **Cost:** Right size, no oversized
- **Naming:** Consistent tags, naming
- **Compliance:** Region, retention
- **Reliability:** Multi-AZ, backup

The categories are per org.

## The "GCP + Conftest" pattern

For GCP:
```rego
# gcp_security.rego
package main.gcp_security

deny[msg] {
  resource := input.resource.google_sql_database_instance[name]
  resource.settings.ip_configuration.ipv4_enabled == true
  msg := sprintf(
    "Cloud SQL %s has public IP enabled. Use private IP.",
    [name]
  )
}

deny[msg] {
  resource := input.resource.google_storage_bucket[name]
  resource.uniform_bucket_level_access.enabled == false
  msg := sprintf(
    "GCS bucket %s must have uniform bucket-level access.",
    [name]
  )
}
```

The policies are per cloud.

## The "what to scan" pattern

For Conftest:
- **Public S3:** Block
- **Public IP on DB:** Block
- **No encryption:** Block
- **No tags:** Block
- **Wrong region:** Block
- **MFA on root:** Require
- **MFA on IAM:** Require

The scans are per type.

## The "policy as code benefits" pattern

For benefits:
- **Automated:** No manual review
- **Consistent:** Always same rules
- **Documented:** Rego is the doc
- **Auditable:** Git history
- **Versioned:** Per environment

The benefits are real.

## The "my approach" pattern

For practical:
- **Modules:** Unit tests + mock providers + integration
- **Root configs:** Policy on every plan + quarterly integration
- **Modules in repo:** Full unit + integration
- **Cross-team:** Policy required

The approach is layered.

## The "policy CI failure" pattern

For failure:
- **PR comment:** With violation
- **Block merge:** Until fixed
- **Exception:** Documented with expiry
- **Override:** Only with approval

The failure is enforced.

## The "policy version" pattern

For versioning:
- **In git:** Per file
- **Versioned:** Per release
- **Documented:** Per policy
- **Reviewed:** Per change

The version is tracked.

## The "no tests" anti-pattern

For no tests:
- **Issue:** Bugs ship
- **Fix:** 3 layers

The tests are required.

## The "no policy" anti-pattern

For no policy:
- **Issue:** Inconsistent security
- **Fix:** OPA + Conftest

The policy is required.

## The "no mocks" anti-pattern

For no mocks:
- **Issue:** Tests need real AWS
- **Fix:** Mock providers for unit

The mocks are for unit.

## The "no integration" anti-pattern

For no integration:
- **Issue:** Bugs in plan ≠ bugs in API
- **Fix:** Terratest for critical modules

The integration is for confidence.

## The "no version" anti-pattern

For no version:
- **Issue:** Conftest version drift
- **Fix:** Pin in CI

The version is pinned.

## The "IaC testing checklist" pattern

For checklist:
- [ ] `terraform validate` in CI
- [ ] `terraform test` for modules
- [ ] OPA/Conftest for policies
- [ ] Terratest for critical
- [ ] Plan JSON artifact saved
- [ ] PR comment on violation
- [ ] Mock providers for unit
- [ ] Quarterly integration

The checklist is comprehensive.

## Verification
- **Test:** Unit tests pass
- **Test:** Policies enforce
- **Test:** Integration deploys
- **Test:** Drift detected
- **Audit:** Quarterly

## Gotchas
- **The "no tests" anti-pattern.** 3 layers.
- **The "no policy" anti-pattern.** OPA.
- **The "no mocks" anti-pattern.** Mock providers.

## Related
- `infra/iac-best-practices.md`
- `infra/terraform-modules.md`
- `deploy/gitops.md`
- `deploy/cab-change-management.md`
- Bits Lovers: https://www.bitslovers.com/terraform-testing-2026/
- Gruntwork: https://www.gruntwork.io/blog/automatically-enforce-policies-on-your-terraform-modules-using-opa-and-terratest
- OneUptime: https://oneuptime.com/blog/post/2026-02-17-how-to-implement-policy-as-code-for-gcp-terraform-deployments-using-opa-and-conftest/view
