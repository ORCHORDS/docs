# cloud-cost-optimization-rightsizing

**Issue:** Identifying and eliminating waste through rightsizing, scheduling, and architecture changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloud spend growing faster than usage. Over-provisioned instances, idle resources, and unattached storage accumulate silently.

## Pattern / Solution
Common waste categories and quick wins:
```bash
# AWS: Find unattached EBS volumes
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query 'Volumes[*].[VolumeId,Size,CreateTime]' \
  --output table

# AWS: Find idle load balancers (no healthy targets for 7d)
aws elbv2 describe-load-balancers --query 'LoadBalancers[*].LoadBalancerArn' | \
  xargs -I{} aws elbv2 describe-target-health --target-group-arn {}

# AWS: Find snapshots older than 90 days not attached to AMI
aws ec2 describe-snapshots --owner-ids self \
  --query 'Snapshots[?StartTime<`2026-05-01`].[SnapshotId,VolumeSize,StartTime]'
```

Rightsizing workflow:
```
1. Collect 2-4 weeks of CPU/memory metrics
2. Identify p95 CPU < 20% or p95 memory < 40% → candidate for downsizing
3. Check for burstable (t-family) suitability: if CPU rarely exceeds 20%, t4g is cheaper
4. Apply change in staging, validate, roll to prod
5. Re-evaluate after 30 days
```

Dev environment scheduling (save ~65%):
```hcl
# Stop dev RDS instances on weeknights and weekends
resource "aws_cloudwatch_event_rule" "stop_dev_db" {
  name                = "stop-dev-db-evening"
  schedule_expression = "cron(0 19 ? * MON-FRI *)"   # 7 PM UTC weekdays
}
```

Orphan resource scanner (open source):
- `cloud-nuke` (Gruntwork) — delete all resources in an account by age
- `aws-nuke` — dry-run mode to preview before deletion
- Infracost — PR comments with cost delta for Terraform changes

## Gotchas
- Rightsizing during peak traffic periods can cause incidents — schedule during low-traffic windows
- Memory metrics not available by default in CloudWatch — requires CloudWatch Agent
- Spot interruptions break rightsizing analysis — exclude spot instances from baseline
- RDS "available" status instances still bill compute — stop them or delete if unused

## Related
- `aws-reserved-instances.md`
- `spot-instance-strategies.md`
- `aws-cost-explorer-tagging.md`
