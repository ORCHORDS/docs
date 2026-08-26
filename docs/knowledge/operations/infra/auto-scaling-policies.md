# auto-scaling-policies

**Issue:** Configuring auto-scaling policies that respond correctly to load without thrashing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Scale-out too slow causing user-facing latency spikes; scale-in too aggressive causing repeated scaling cycles. Scaling on CPU alone misses memory-bound or I/O-bound workloads.

## Pattern / Solution
Target tracking (preferred for most workloads):
```hcl
resource "aws_autoscaling_policy" "cpu" {
  name                   = "target-cpu-60"
  policy_type            = "TargetTrackingScaling"
  autoscaling_group_name = aws_autoscaling_group.app.name

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 60.0   # keep CPU at 60% — leaves headroom for spikes
  }
}

# Scale on custom metric (SQS queue depth)
resource "aws_autoscaling_policy" "queue" {
  name        = "target-sqs-depth"
  policy_type = "TargetTrackingScaling"
  autoscaling_group_name = aws_autoscaling_group.workers.name

  target_tracking_configuration {
    customized_metric_specification {
      metric_name = "ApproximateNumberOfMessagesVisible"
      namespace   = "AWS/SQS"
      statistic   = "Average"
      dimensions {
        name  = "QueueName"
        value = "my-queue"
      }
    }
    target_value = 10   # 10 messages per instance
  }
}
```

Kubernetes HPA with custom metrics:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  minReplicas: 3
  maxReplicas: 50
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "500"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300   # 5 min cooldown prevents thrashing
      policies:
      - type: Pods
        value: 2
        periodSeconds: 60
```

## Gotchas
- Scale-out should be aggressive (fast); scale-in should be conservative (slow stabilization window)
- Warm-up period: new instances take time to pass health checks — factor this into target utilization
- Multi-metric policies: ASG satisfies the most conservative policy — test that they don't conflict
- KEDA (Kubernetes Event-Driven Autoscaler) scales to zero for batch workloads — HPA cannot

## Related
- `spot-instance-strategies.md`
- `capacity-planning-forecasting.md`
- `aws-ec2-instance-types.md`
