# aws-cost-explorer-tagging

**Issue:** Implementing cost allocation tags to attribute AWS spend by team, service, and environment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
AWS bill is a single lump sum. No visibility into which service, team, or environment is responsible for cost spikes.

## Pattern / Solution
Mandatory tags enforced via AWS Config:
```json
// config-rule: required-tags
{
  "requiredTagKeys": ["Environment", "Team", "Service", "CostCenter"],
  "tag:Environment": "prod|staging|dev",
  "tag:Team": "platform|backend|frontend|data"
}
```

SCP to deny resource creation without required tags:
```json
{
  "Effect": "Deny",
  "Action": ["ec2:RunInstances", "rds:CreateDBInstance"],
  "Resource": "*",
  "Condition": {
    "Null": {
      "aws:RequestTag/Team": "true",
      "aws:RequestTag/Environment": "true"
    }
  }
}
```

Activate tags for cost allocation (must be done in Billing Console):
```bash
aws ce tag-resources --resource-type COST_ALLOCATION_TAG \
  --resource-ids "Environment" "Team" "Service"
```

Cost Explorer CLI query:
```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-08-11 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=Team
```

## Gotchas
- Tags take 24 h to appear in Cost Explorer after activation
- Resources created before tagging policy are untagged — remediate with Config auto-remediation SSM document
- AWS Budgets can alert per tag dimension — set per-team monthly budgets
- Some services (data transfer, support) cannot be tagged — attribute by allocation key

## Related
- `aws-reserved-instances.md`
- `cloud-cost-optimization-rightsizing.md`
- `aws-iam-least-privilege.md`
