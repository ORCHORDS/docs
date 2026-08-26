# spot-instance-strategies

**Issue:** Using Spot/Preemptible instances for fault-tolerant workloads to cut compute costs 70–90%
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Batch jobs, ML training, and CI runners running on expensive On-Demand instances when they could use Spot with proper interruption handling.

## Pattern / Solution
AWS Spot best practices:
```hcl
resource "aws_launch_template" "worker" {
  instance_market_options {
    market_type = "spot"
    spot_options {
      spot_instance_type = "one-time"
      # No max_price = bid current on-demand price (avoids interruption when price spikes)
    }
  }
}

resource "aws_autoscaling_group" "workers" {
  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 1   # keep 1 on-demand for stability
      on_demand_percentage_above_base_capacity = 0   # rest are spot
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
    launch_template {
      launch_template_specification { launch_template_id = aws_launch_template.worker.id }
      # Diversify across families and sizes — reduces interruption probability
      override { instance_type = "m7g.xlarge" }
      override { instance_type = "m6g.xlarge" }
      override { instance_type = "r7g.large" }
      override { instance_type = "c7g.xlarge" }
    }
  }
}
```

Handling interruption (2-minute warning via instance metadata):
```bash
#!/bin/bash
# Poll for interruption notice every 5 seconds
while true; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    http://169.254.169.254/latest/meta-data/spot/termination-time)
  if [ "$STATUS" = "200" ]; then
    # Checkpoint work, drain, notify orchestrator
    /opt/app/graceful-shutdown.sh
    break
  fi
  sleep 5
done
```

Karpenter for Kubernetes spot diversification:
```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
spec:
  instanceRequirements:
  - key: karpenter.sh/capacity-type
    operator: In
    values: ["spot", "on-demand"]
  - key: node.kubernetes.io/instance-type
    operator: In
    values: ["m7g.xlarge", "m6g.xlarge", "m6i.xlarge", "c7g.xlarge"]
```

## Gotchas
- `capacity-optimized` strategy (old) replaced by `price-capacity-optimized` — use the new one
- Spot pools can be exhausted — diversify across at least 5 instance types and 3 AZs
- Spot interruptions are 2-minute notice, not immediate — implement checkpoint logic
- GPU spots (p-family) have very low availability; use on-demand for time-sensitive GPU jobs

## Related
- `aws-ec2-instance-types.md`
- `auto-scaling-policies.md`
- `aws-reserved-instances.md`
