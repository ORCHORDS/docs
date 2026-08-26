# Zero-Downtime Deploy Strategies

Zero-downtime deployments ensure your applications remain available during updates. Here are the most effective strategies with practical implementations.

## Blue-Green Deployment

Blue-green deployment uses two identical production environments. While one runs the current version (blue), the other (green) receives the new deployment. Once verified, traffic switches to green.

```bash
# Deploy to green environment
aws elbv2 modify-target-groups \
    --target-groups-arns arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/green-group/1234567890123456 \
    --target-group-name green-group

# Switch traffic to green
aws elbv2 modify-target-groups \
    --target-groups-arns arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/blue-group/1234567890123456 \
    --target-group-name blue-group
```

## Rolling Deployment

Rolling deployments update instances gradually, replacing old versions with new ones in batches. This approach minimizes risk while maintaining availability.

```yaml
# Kubernetes rolling deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deployment
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
      - name: app-container
        image: myapp:v2
```

## Canary Deployment

Canary deployments roll out new versions to a small subset of users first, gradually increasing traffic based on success metrics.

```javascript
// Nginx canary configuration
upstream backend {
    server 10.0.0.1:8080 weight=90;  # 90% traffic
    server 10.0.0.2:8080 weight=10;  # 10% traffic (new version)
}

server {
    location / {
        proxy_pass http://backend;
    }
}
```

## Serverless Version Aliases

Serverless platforms use version aliases to manage deployments without downtime.

```bash
