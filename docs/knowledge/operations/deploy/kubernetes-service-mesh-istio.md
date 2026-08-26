# kubernetes-service-mesh-istio

**Issue:** Deploying and operating Istio for mTLS, traffic management, and observability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service meshes provide mTLS between pods, fine-grained traffic splitting, retries, circuit breaking, and distributed tracing without application code changes. Istio is the most feature-complete option but has significant operational overhead.

## Pattern / Solution
Install Istio with minimal profile:
```bash
istioctl install --set profile=minimal -y
kubectl label namespace production istio-injection=enabled
```

Enforce strict mTLS cluster-wide:
```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system   # cluster-wide
spec:
  mtls:
    mode: STRICT
```

Traffic splitting for canary (Istio VirtualService):
```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: myapp
spec:
  hosts: [myapp]
  http:
  - route:
    - destination:
        host: myapp
        subset: stable
      weight: 90
    - destination:
        host: myapp
        subset: canary
      weight: 10
---
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: myapp
spec:
  host: myapp
  subsets:
  - name: stable
    labels:
      version: stable
  - name: canary
    labels:
      version: canary
```

Circuit breaker:
```yaml
spec:
  trafficPolicy:
    outlierDetection:
      consecutiveGatewayErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
```

## Gotchas
- Sidecar injection is per-namespace; existing pods need restart after labeling the namespace
- Istio adds ~10ms of latency per hop and ~50MB RSS per sidecar — budget accordingly
- `PeerAuthentication` STRICT mode breaks non-mesh services (e.g., health-check pods without sidecars)
- Envoy sidecar startup delay can cause connection refused errors; use `holdApplicationUntilProxyStarts: true`
- Ambient mode (sidecars replaced by ztunnel) is production-ready as of Istio 1.22 and cuts overhead significantly

## Related
- `kubernetes-network-policies.md`
- `kubernetes-ingress-controller.md`
- `kubernetes-observability-stack.md`
- `canary-deployments.md`
