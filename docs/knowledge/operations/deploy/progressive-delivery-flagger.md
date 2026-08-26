# Progressive Delivery with Flagger

Progressive delivery is a deployment strategy that gradually introduces new software versions to users, reducing risk and enabling faster feedback loops. Flagger is an open-source tool that implements progressive delivery patterns for Kubernetes applications, providing automated canary deployments, metric-based promotion decisions, and rollback capabilities.

## Symptom

When deploying new application versions, teams often face several challenges:
- High-risk deployments causing production outages
- Manual intervention required for promotion decisions
- Lack of visibility into deployment progress and health metrics
- No automated rollback mechanisms when issues are detected
- Difficulty integrating with existing monitoring and alerting systems

## Gotchas

Several common pitfalls exist when implementing progressive delivery with Flagger:
- **Insufficient health checks**: Basic readiness probes may not detect performance degradation or memory leaks
- **Poor metric selection**: Choosing metrics that don't accurately represent user experience
- **Inadequate rollback triggers**: Setting thresholds that are too lenient or overly aggressive
- **Network configuration issues**: Misconfigured service mesh settings preventing proper traffic routing
- **Notification delays**: Webhook configurations that fail to send timely alerts during deployments

## Configuration Examples

### Basic Canary Deployment

```yaml
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: app-canary
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app-deployment
  progressDeadlineSeconds: 60
  service:
    port: 80
    targetPort: 8080
  analysis:
    interval: 10s
    threshold: 1
    maxWeight: 100
    stepWeight: 20
    metrics:
    - name: request-success-rate
      threshold: 99
      interval: 60s
    - name: request-duration
      threshold: 500
      interval: 60s
```

### Advanced Configuration with Webhooks

```yaml
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: app-canary
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app-deployment
  service:
    port: 80
    targetPort: 8080
  analysis:
    interval: 30s
    threshold: 5
    maxWeight: 100
    stepWeight: 25
    metrics:
    - name: http_requests_total
      threshold: 1000
      interval: 60s
      query: sum(rate(http_requests_total{job="app"}[5m]))
    - name: error_rate
      threshold: 0.1
      interval: 60s
      query
