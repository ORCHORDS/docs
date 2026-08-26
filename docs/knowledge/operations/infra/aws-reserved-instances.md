# aws-reserved-instances

**Issue:** Choosing between Reserved Instances, Savings Plans, and On-Demand for cost optimization
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Running entirely On-Demand instances despite stable baseline workloads. Missing 40–60 % savings available through commitment pricing.

## Pattern / Solution
```
Commitment type comparison:
┌─────────────────────┬──────────┬─────────┬──────────────────┐
│ Type                │ Savings  │ Flex    │ Best for         │
├─────────────────────┼──────────┼─────────┼──────────────────┤
│ EC2 Reserved (1yr)  │ ~40%     │ Low     │ Stable EC2       │
│ EC2 Reserved (3yr)  │ ~60%     │ Low     │ Very stable EC2  │
│ Compute SP (1yr)    │ ~54%     │ High    │ EC2+Fargate+Lambda│
│ EC2 SP (1yr)        │ ~60%     │ Medium  │ Specific family  │
│ Spot                │ ~70-90%  │ Variable│ Fault-tolerant   │
└─────────────────────┴──────────┴─────────┴──────────────────┘
```

Strategy: cover baseline with Savings Plans, burst with Spot:
```bash
# Analyze past 30 days usage for SP recommendation
aws ce get-savings-plans-purchase-recommendation \
  --savings-plans-type COMPUTE_SP \
  --term-in-years ONE_YEAR \
  --payment-option NO_UPFRONT \
  --lookback-period-in-days THIRTY_DAYS
```

Track Savings Plans coverage:
```bash
aws ce get-savings-plans-coverage \
  --time-period Start=2026-08-01,End=2026-08-11 \
  --granularity MONTHLY \
  --group-by Type=DIMENSION,Key=SERVICE
```

Rule of thumb: buy Savings Plans to cover p50 usage, let Spot or On-Demand handle p50→p95, use Spot for ephemeral jobs.

## Gotchas
- Savings Plans apply automatically to matching usage — no instance reservation needed
- All Upfront provides the highest discount but ties up capital; No Upfront is more flexible
- Convertible Reserved Instances allow instance family/size changes — good for uncertain future needs
- RDS Reserved Instances are separate from EC2 — don't conflate them
- Unused Reserved Instances can be sold on AWS Marketplace

## Related
- `aws-ec2-instance-types.md`
- `spot-instance-strategies.md`
- `cloud-cost-optimization-rightsizing.md`
