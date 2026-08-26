# service-mesh

A service mesh is an infrastructure layer that handles service-to-service communication, providing traffic management, security, and observability without requiring changes to application code.

## Core Components

**Sidecar Proxy**: The foundation of service meshes. Each service instance runs a sidecar proxy (like Envoy) that intercepts all network traffic. For example, with Istio:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: productpage
spec:
  template:
    spec:
      containers:
      - name: productpage
        image: istio/examples-bookinfo-productpage-v1:1.16.2
      - name: istio-proxy
        image: docker.io/istio/proxyv2:1.16.2
```

**mTLS**: Mutual Transport Layer Security ensures secure communication between services. Istio automatically provisions certificates:

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
spec:
  mtls:
    mode: STRICT
```

## Traffic Management

Service meshes provide sophisticated traffic routing. Istio's VirtualService example:

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: reviews
spec:
  hosts:
  - reviews
  http:
  - route:
    - destination:
        host: reviews
        subset: v2
      weight: 80
    - destination:
        host: reviews
        subset: v3
      weight: 20
```

Linkerd's traffic splitting:

```yaml
apiVersion: linkerd.io/v1alpha2
kind: ServiceProfile
metadata:
  name: reviews.default.svc.cluster.local
spec:
  routes:
  - name: GET /reviews
    condition:
      path_regex: /reviews
    response_classes:
    - name: success
      is_failure: false
```

## Observability

Metrics, logs, and tracing are automatically collected. Istio's Prometheus integration:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: istio-component-monitor
spec:
  selector:
    matchLabels:
      istio: pilot
  endpoints:
  - port: http-monitoring
```

## Tradeoffs and Gotchas

**Performance overhead**: Sidecars add ~50-100ms latency per request. Each proxy consumes CPU and memory.

**Complexity**: Debugging issues becomes harder when traffic flows through multiple proxies. Network policies can conflict with mesh rules.

**Version compatibility**: Istio's control plane version must match sidecar versions. Mixing versions causes routing failures.

**Resource consumption**: A 100-service mesh might require 200+ proxy instances, each consuming 50-100MB RAM.

## When to use

Use a service mesh when you have:
- Multiple microservices with complex traffic patterns
- Need for mTLS without application code changes
- Existing Kubernetes infrastructure with Istio or Linkerd
- Requirements for advanced traffic management (canary deployments, circuit breaking)
- Need for comprehensive observability across services

## When NOT to use

Avoid service meshes when:
- Simple monolithic applications or small service sets (<5 services)
- Performance is critical and you can't tolerate proxy overhead
- You're not using Kubernetes or container orchestration
- Budget constraints prevent managing additional infrastructure complexity
- Your team lacks experience with service mesh concepts
- Services communicate over HTTP/HTTPS only (no gRPC, TCP needs)
