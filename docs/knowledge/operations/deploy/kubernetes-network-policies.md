# kubernetes-network-policies

**Issue:** Writing NetworkPolicy rules to enforce zero-trust pod-to-pod communication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
By default all pods can reach all other pods in a cluster. NetworkPolicy restricts this at L3/L4. Requires a CNI that enforces policies (Calico, Cilium, Weave; NOT Flannel alone).

## Pattern / Solution
Allow ingress only from specific pods:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes: [Ingress]
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
```

Allow egress to specific namespace (e.g., database namespace):
```yaml
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes: [Egress]
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          team: data
    ports:
    - protocol: TCP
      port: 5432
  - to:   # always allow DNS
    - namespaceSelector: {}
    ports:
    - protocol: UDP
      port: 53
```

Allow prometheus scraping across namespaces:
```yaml
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: monitoring
      podSelector:
        matchLabels:
          app: prometheus
    ports:
    - port: 9090
```

## Gotchas
- Missing DNS egress rule (UDP 53) is the #1 cause of mysterious network failures after adding policies
- `podSelector: {}` means *all pods in namespace*, not *no pods*
- `from` entries are OR'd together; `from[0].podSelector` + `from[0].namespaceSelector` within same entry are AND'd
- Policies are additive — a pod with multiple matching policies gets the union of all allowed traffic
- NetworkPolicy is not enforced on `hostNetwork: true` pods

## Related
- `kubernetes-namespace-isolation.md`
- `kubernetes-service-mesh-istio.md`
- `kubernetes-rbac-patterns.md`
