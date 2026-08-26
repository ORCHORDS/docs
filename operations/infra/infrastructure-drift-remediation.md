# infrastructure-drift-remediation

**Issue:** Detecting and remediating drift between IaC state and actual cloud resource configuration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual changes made in the AWS/GCP console, emergency hotfixes applied directly to servers, or out-of-band automation leave actual infrastructure in a state that differs from Terraform or Pulumi state files. The next `terraform apply` either fails, overwrites valid changes, or silently drifts further.

## Pattern / Solution
Detect drift regularly and remediate through IaC, not through additional manual changes.

**Terraform drift detection:**
```bash
# Show planned changes without applying (drift report)
terraform plan -out=drift.tfplan
terraform show -json drift.tfplan | jq '.resource_changes[] | select(.change.actions != ["no-op"])'

# Refresh state from actual cloud resources
terraform refresh   # deprecated in TF 1.x; use plan -refresh-only
terraform plan -refresh-only -out=refresh.tfplan
terraform apply refresh.tfplan   # updates state to match reality

# Import a resource created out-of-band
terraform import aws_s3_bucket.logs my-logs-bucket-name
```

**Automated drift detection in CI (run nightly):**
```yaml
# .github/workflows/drift-check.yml
name: Drift Check
on:
  schedule:
    - cron: '0 6 * * *'   # 06:00 UTC daily

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform init
      - id: plan
        run: terraform plan -refresh-only -detailed-exitcode
        continue-on-error: true
      - name: Alert on drift
        if: steps.plan.outputs.exitcode == '2'
        uses: slackapi/slack-github-action@v1
        with:
          payload: '{"text":"Terraform drift detected in production"}'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

Terraform exit codes:
- `0` = no changes
- `1` = error
- `2` = changes detected (drift exists)

**Remediation workflow:**
1. Run `terraform plan -refresh-only` to see what changed in reality
2. For valid manual changes: update the `.tf` files to match, then `terraform apply`
3. For invalid manual changes: run `terraform apply` to revert to desired state
4. For resources that should not be managed by Terraform: use `terraform state rm` to remove from state

**Pulumi drift detection:**
```bash
pulumi refresh    # sync state with actual cloud resources
pulumi preview    # show what Pulumi would change
```

## Gotchas
- `terraform refresh` updates local state only — it does not revert changes in the cloud. Reverting requires `terraform apply`.
- Importing resources into state without the corresponding `.tf` definition causes the next plan to propose deletion.
- State locking must be enabled (remote backend) before running automated drift checks; concurrent plan runs corrupt state.
- Some resource properties are not readable by the provider (e.g., secrets) and will always show as drift unless marked `ignore_changes`.

```hcl
# Ignore specific attributes that change externally
resource "aws_instance" "app" {
  # ...
  lifecycle {
    ignore_changes = [user_data, tags["LastModified"]]
  }
}
```

## Related
- `iac-best-practices.md`
- `terraform-modules.md`
- `grafana-dashboard-as-code.md`
