# cost-per-deployment

**Issue:** Measuring and optimising the infrastructure cost of each deployment pipeline run
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CI/CD infrastructure costs grow silently as teams scale. Compute-heavy build jobs, redundant test environments, and over-provisioned runners inflate costs without improving delivery. Measuring cost per deployment enables ROI decisions.

## Pattern / Solution
GitHub Actions cost estimation:
```bash
# GitHub billing API — minutes per workflow
gh api /orgs/$ORG/settings/billing/actions \
  --jq '{used_minutes: .total_minutes_used, paid_minutes: .total_paid_minutes_used}'

# Per-workflow breakdown (use workflow run list)
gh api /repos/$OWNER/$REPO/actions/runs \
  --paginate \
  --jq '.workflow_runs[] | {name: .name, created_at, run_started_at}'
```

EC2 spot instance runner cost tracking:
```python
# Lambda function triggered by runner lifecycle events
import boto3, json
from datetime import datetime

def handler(event, context):
    instance_id = event['detail']['instance-id']

    ec2 = boto3.client('ec2')
    spot_price = boto3.client('ec2').describe_spot_price_history(
        InstanceTypes=['c6i.2xlarge'],
        MaxResults=1,
        ProductDescriptions=['Linux/UNIX']
    )['SpotPriceHistory'][0]['SpotPrice']

    # Store in CloudWatch custom metric
    cw = boto3.client('cloudwatch')
    cw.put_metric_data(
        Namespace='CI/Cost',
        MetricData=[{
            'MetricName': 'SpotCostPerRun',
            'Value': float(spot_price) * (event['duration_minutes'] / 60),
            'Unit': 'None',
        }]
    )
```

Cost reduction levers:
```bash
# 1. Identify slow jobs consuming most minutes
gh api /repos/$OWNER/$REPO/actions/runs --paginate \
  --jq '.workflow_runs[] | {id: .id, name: .name}' | \
  while read run; do
    RUN_ID=$(echo $run | jq -r .id)
    gh api /repos/$OWNER/$REPO/actions/runs/$RUN_ID/jobs \
      --jq '.jobs[] | {name: .name, duration: (.completed_at | fromdateiso8601) - (.started_at | fromdateiso8601)}'
  done

# 2. Switch to spot/preemptible runners (60-90% savings)
# 3. Cache aggressively (Docker layer cache, npm cache)
# 4. Cancel stale builds on new push
# 5. Run expensive tests only on main branch
```

## Gotchas
- GitHub Actions minutes are billed at multipliers: Linux 1x, Windows 2x, macOS 10x — default to Linux
- Spot instance interruptions mid-build waste all accrued compute; implement retry or checkpoint
- Staging environments left running 24/7 cost more than all CI builds combined; implement auto-shutdown
- Caching reduces costs but introduces stale dependency risks; set aggressive TTLs on caches

## Related
- `finops-cost-optimization.md`
- `infrastructure-cost-tagging.md`
- `github-actions-self-hosted.md`
- `docker-layer-caching-ci.md`
