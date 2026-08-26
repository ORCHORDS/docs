# terraform-drift-detection

**Issue:** Detecting and remediating when production infrastructure drifts from its Terraform definition
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers make manual changes in the AWS console or via CLI to fix urgent issues and forget to reflect them in Terraform. Over time the codebase diverges from reality, causing unexpected plan diffs and failed applies.

## Pattern / Solution
**Scheduled drift detection in CI (runs nightly)**
```yaml
# .github/workflows/drift-detect.yml
name: Terraform Drift Detection
on:
  schedule:
    - cron: '0 6 * * *'  # 06:00 UTC daily

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456:role/terraform-ro
          aws-region: us-east-1

      - name: Terraform init
        run: terraform init
        working-directory: infra/

      - name: Detect drift
        id: plan
        run: |
          terraform plan -detailed-exitcode -out=drift.tfplan 2>&1 | tee plan.txt
          echo "exit_code=$?" >> $GITHUB_OUTPUT
        working-directory: infra/
        continue-on-error: true

      - name: Alert on drift
        if: steps.plan.outputs.exit_code == '2'
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {"text": "⚠️ Terraform drift detected in `infra/`. Review the plan output."}
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_INFRA_WEBHOOK }}
```

**Exit codes**
- `0` — no changes (no drift)
- `1` — error
- `2` — changes present (drift detected)

**Drift remediation options**
```bash
# Option A: apply Terraform to restore desired state
terraform apply drift.tfplan

# Option B: import the manual change into state (if intentional)
terraform import aws_security_group_rule.new sg-xxxxx_ingress_tcp_443_443_0.0.0.0/0

# Option C: update the Terraform code to match reality
# Then re-plan to confirm zero diff
```

**Preventing drift**
- Require all infrastructure changes to go through Terraform via policy (AWS SCP deny direct console changes in prod)
- Use `terraform-docs` to document resources and discourage manual overrides
- Enable AWS Config rules that flag manually modified resources

## Gotchas
- `terraform plan` with a read-only IAM role will show false drift for resources requiring write access to read full state (e.g. some RDS parameters)
- Sensitive attribute changes (passwords, keys) are shown as `(sensitive value)` in the plan — do not assume no drift just because the diff looks small
- A nightly plan can itself fail if the backend credentials expire — monitor the workflow, not just the plan result

## Related
- `terraform-state-management.md`
- `infrastructure-cost-tagging.md`
- `gitops.md`
