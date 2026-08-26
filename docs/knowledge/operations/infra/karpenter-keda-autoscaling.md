# Karpenter + KEDA Autoscaling Stack

## Overview

The Karpenter + KEDA autoscaling stack combines AWS EC2's provisioner-based node management with Kubernetes Event-Driven Autoscaling (KEDA) for comprehensive application scaling. This integration provides automatic node provisioning, intelligent consolidation, and event-driven scaling capabilities that work seamlessly together to optimize costs and performance.

## Node Provisioning

Karpenter automatically provisions nodes based on workload requirements using provisioners. The stack leverages Karpenter's ability to create nodes with specific instance types, zones, and labels matching your application needs.

```yaml
# Karpenter Provisioner Configuration
apiVersion: karpenter.sh/v1beta1
kind: Provisioner
metadata:
  name: default
spec:
  providerRef:
    name: default
  requirements:
    - key: kubernetes.io/arch
      operator: In
      values: [amd64]
    - key: kubernetes.io/os
      operator: In
      values: [linux]
    - key: node.kubernetes.io/instance-type
      operator: In
      values: [m5.large, m5.xlarge]
  ttlSecondsAfterEmpty: 30
  consolidation:
    enabled: true
```

## Consolidation

Karpenter's consolidation feature automatically terminates underutilized nodes and consolidates workloads onto fewer, more efficient nodes. This reduces costs while maintaining application availability through proper disruption budgets.

```yaml
# Consolidation Configuration
spec:
  consolidation:
    enabled: true
  ttlSecondsUntilExpired: 2592000 # 30 days
```

## Disruption Budgets

Proper disruption budget configuration ensures that scaling operations don't disrupt critical workloads. Karpenter integrates with PodDisruptionBudgets to maintain availability during node consolidation and provisioning.

```yaml
# PodDisruptionBudget Configuration
apiVersion: policy/v1beta1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: my-app
```

## KEDA Scaled Objects

KEDA scaled objects define the scaling triggers and targets for your applications. These objects work with Karpenter to provision additional nodes when workload demands increase.

```yaml
# KEDA ScaledObject Configuration
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: my-app-scaledobject
spec:
  scaleTargetRef:
    name: my-app-deployment
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus:9090
        metricName: http_requests_total
        threshold: "100"
        query: sum(rate(http_requests_total[2m]))
```

## Event-Driven Scaling

The stack enables event
