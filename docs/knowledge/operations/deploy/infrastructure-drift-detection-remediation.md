# Infrastructure Drift Detection — Terraform State and Remediation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Terraform-managed infrastructure no longer matches what is defined
in code. Someone made a manual change in the AWS console — added a
security group rule, resized an instance, modified an IAM policy — and
now `terraform plan` shows unexpected diffs. Worse, you do not know
drift has occurred until a deployment fails or a security audit reveals
undocumented resources. Emergency changes made during incidents are never
back-ported to IaC, creating a growing gap between declared and actual
state.

## Context

Infrastructure drift occurs when the actual state of cloud resources
diverges from the state declared in Infrastructure as Code (IaC).
Common causes include manual console changes, out-of-band API calls,
auto-scaling events, and changes by other automation tools. In 2026,
drift detection is a standard practice in mature IaC pipelines, with
Terraform Cloud/Enterprise offering built-in drift detection, and
third-party tools (Spacelift, env0, Scalr, Driftctl) providing
continuous monitoring. The goal is not to prevent all manual changes
(incident response requires them) but to detect and reconcile them
systematically.

## Types of drift

```
Configuration drift:
  → Resource attributes changed outside Terraform
  → Example: security group rule added via console
  → Detected by: terraform plan

State drift:
  → Resources exist that Terraform does not know about
  → Example: manually created S3 bucket
  → Detected by: cloud inventory scan (not terraform plan)

Code drift:
  → Terraform code was changed but never applied
  → Example: PR merged but terraform apply never ran
  → Detected by: CI pipeline comparing plan output

Dependency drift:
  → Provider or module versions changed upstream
  → Example: AWS provider update changes resource behavior
  → Detected by: lock file comparison, plan diff
```

## Detection methods

### 1. terraform plan (basic)

```bash
# Refresh state and show drift
terraform plan -refresh-only

# Output: shows what changed in real infrastructure
# versus what Terraform state records

# Limitations:
#   - Only detects drift in resources Terraform manages
#   - Does not find unmanaged resources
#   - Must be run per workspace/state file
```

### 2. Scheduled drift detection (CI)

```yaml
# GitHub Actions: scheduled drift check
name: Drift Detection
on:
  schedule:
    - cron: '0 */4 * * *'  # Every 4 hours

jobs:
  detect:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        workspace: [production, staging]
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init
        working-directory: infra/${{ matrix.workspace }}

      - name: Detect Drift
        id: plan
        run: |
          terraform plan -refresh-only -detailed-exitcode \
            -out=drift.plan 2>&1 | tee plan_output.txt
          echo "exitcode=$?" >> "$GITHUB_OUTPUT"
        working-directory: infra/${{ matrix.workspace }}
        continue-on-error: true

      - name: Alert on Drift
        if: steps.plan.outputs.exitcode == '2'
        run: |
          echo "::error::Drift detected in ${{ matrix.workspace }}"
          # Send Slack notification, create issue, etc.
```

### 3. Terraform Cloud drift detection

```hcl
# Terraform Cloud workspace configuration
resource "tfe_workspace" "production" {
  name         = "production"
  organization = "my-org"

  # Enable automatic drift detection
  assessments_enabled = true

  # Drift detection runs automatically on a schedule
  # Results appear in the workspace UI
  # Notifications sent via configured hooks
}
```

### 4. Cloud-native inventory scanning

```bash
# AWS Config: detect unmanaged resources
aws configservice get-discovered-resource-counts

# Compare against Terraform state
terraform state list | sort > tf_resources.txt
aws configservice list-discovered-resources \
  --resource-type AWS::EC2::Instance \
  --query 'resourceIdentifiers[].resourceId' | sort > aws_resources.txt

diff tf_resources.txt aws_resources.txt
```

## Remediation strategies

```
Drift detected → classify → remediate:

1. Intentional drift (emergency change):
   → Import into Terraform state
   → Update IaC code to match actual state
   → Commit, review, merge

2. Unintentional drift (accidental console change):
   → terraform apply to revert to declared state
   → Investigate root cause (who changed it, why)
   → Strengthen access controls

3. Acceptable drift (auto-scaling, dynamic resources):
   → Add lifecycle { ignore_changes } blocks
   → Exclude from drift detection
   → Document why drift is expected

4. Unknown resources (not in Terraform):
   → terraform import to bring under management
   → Or delete if truly orphaned
```

### Lifecycle ignore for expected drift

```hcl
resource "aws_autoscaling_group" "app" {
  name                = "app-asg"
  min_size            = 2
  max_size            = 20
  desired_capacity    = 2

  lifecycle {
    ignore_changes = [
      desired_capacity,  # Auto-scaling changes this
    ]
  }
}

resource "aws_ecs_service" "api" {
  name            = "api"
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 3

  lifecycle {
    ignore_changes = [
      desired_count,     # Auto-scaling adjusts this
      task_definition,   # Deployment pipeline updates this
    ]
  }
}
```

## Prevention

```
1. Restrict console access
   → Use read-only IAM policies for production
   → Break-glass procedure for emergency access
   → Audit trail for all console actions

2. Policy-as-code
   → OPA/Sentinel policies block non-compliant changes
   → SCPs prevent manual resource creation
   → Tag enforcement: all resources must have IaC tag

3. Immutable infrastructure
   → Replace instances instead of modifying them
   → Blue-green deployments avoid in-place changes
   → Container-based workloads reduce host drift

4. GitOps workflow
   → All changes go through PR → review → apply
   → No direct terraform apply from laptops
   → CI/CD is the only path to production
```

## Anti-patterns

- **Ignoring drift alerts** — treating drift detection as informational
  rather than actionable. Unresolved drift accumulates and creates
  a growing gap between code and reality. Every drift alert should
  result in either remediation or a documented exception.
- **terraform apply as drift fix** — blindly running `terraform apply`
  to "fix" drift without understanding what changed. The manual
  change may have been an emergency fix; reverting it could cause
  an outage. Always review the plan before applying.
- **No break-glass process** — forbidding all manual changes forces
  engineers to work around controls during incidents. Define a
  break-glass procedure: manual change → incident ticket →
  back-port to IaC within 24 hours.
- **Drift detection without notification** — running drift checks
  in CI but not alerting anyone. Drift detection is only useful if
  the right team is notified and responsible for remediation.

## Gotchas

- **State file conflicts** — running drift detection while another
  pipeline is applying changes can cause state lock conflicts. Use
  Terraform state locking and schedule drift checks outside
  deployment windows.
- **Provider-specific behaviors** — some AWS resources (e.g., Lambda
  environment variables, ECS task definitions) are expected to change
  outside Terraform. Blanket drift alerting on these creates noise.
  Use `ignore_changes` judiciously.
- **Multi-account drift** — in AWS Organizations with many accounts,
  drift detection must run per-account, per-workspace. At scale,
  this requires a dedicated pipeline and aggregated reporting.
- **Terraform refresh and API limits** — `terraform plan -refresh-only`
  makes API calls for every managed resource. Large state files
  (1,000+ resources) can hit API rate limits. Use targeted refresh
  or split state files.

## Verification

- Drift detection runs on a schedule (at least every 4 hours).
- Drift alerts are routed to the responsible team.
- Emergency manual changes are back-ported to IaC within 24 hours.
- `lifecycle { ignore_changes }` is used for expected drift.
- Console access to production is read-only by default.
- Break-glass procedure is documented and tested.

## Related

- `documentation/docs/policies/infra/iac-testing-terratest-checkov.md`
- `documentation/docs/policies/deploy/progressive-canary-deployment-rollback.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`

## Source URLs (verified 2026-08-16)

- Terraform Drift Detection: Prevent and Fix Out-of-Band Changes — https://scalr.com/learning-center/terraform-drift-detection-how-to-prevent-and-remediate
- How to Detect Drift in Terraform — https://oneuptime.com/blog/post/2026-01-27-terraform-drift-detection/view
- Terraform Drift Detection and Remediation Guide — https://spacelift.io/blog/terraform-drift-detection
- 8 Terraform Drift Detection Tools Enterprise Teams Use in 2026 — https://www.env0.com/blog/8-terraform-drift-detection-tools-enterprise-teams-actually-use-in-2026
