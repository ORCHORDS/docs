# Kubernetes HPA and VPA Autoscaling

## Overview

Kubernetes Horizontal Pod Autoscaler (HPA) and Vertical Pod Autoscaler (VPA) are essential tools for automatically scaling applications based on resource utilization. HPA scales pods horizontally by adding or removing replicas, while VPA adjusts resource requests and limits vertically to optimize resource allocation.

## HPA Configuration

### CPU and Memory Metrics
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app-deployment
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Custom Metrics
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: custom-metric-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app-deployment
  metrics:
  - type: Pods
    pods:
      metricName: requests-per-second
      targetAverageValue: 100
  - type: External
    external:
      metricName: queue-length
      targetValue: 50
```

## VPA Configuration

### VPA in Off Mode
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: vpa-off-mode-pod
  annotations:
    vpa.autoscaling.k8s.io/off-mode: "true"
spec:
  containers:
  - name: app-container
    image: nginx:latest
    resources:
      requests:
        memory: "64Mi"
        cpu: "250m"
      limits:
        memory: "128Mi"
        cpu: "500m"
```

### VPA with Recommendation Mode
```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: app-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app-deployment
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
    - containerName: app-container
      minAllowed:
        memory: "64Mi"
        cpu: "250m"
      maxAllowed:
        memory: "1Gi"
        cpu: "1"
```

## External Metrics

### Prometheus Integration
