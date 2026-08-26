# kubernetes-namespace-isolation

**Issue:** Enforcing hard isolation boundaries between teams and environments within a shared cluster
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without namespace isolation, a misbehaving workload can starve resources across the cluster, and a compromised pod can reach other tenants' services. Proper isolation uses RBAC, NetworkPolicy, ResourceQuota, and LimitRange together.

## Pattern / Solution
Namespace creation with labels:
```bash
kubectl create namespace team-alpha
kubectl label namespace team-alpha \
  team=alpha \
  environment=production \
  pod-security.kubernetes.io/enforce=restricted
```

ResourceQuota per namespace:
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-alpha-quota
  namespace: team-alpha
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.cpu: "16"
    limits.memory: 32Gi
    count/pods: "50"
    count/services: "20"
    count/persistentvolumeclaims: "10"
```

LimitRange (prevents pods without resource specs):
```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: team-alpha
spec:
  limits:
  - type: Container
    default:
      cpu: 500m
      memory: 256Mi
    defaultRequest:
      cpu: 100m
      memory: 128Mi
    max:
      cpu: "4"
      memory: 8Gi
```

Default-deny NetworkPolicy:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: team-alpha
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

## Gotchas
- Pod Security Admission (PSA) replaced PodSecurityPolicy in K8s 1.25+; use `pod-security.kubernetes.io/enforce` labels
- ResourceQuota only enforces on *new* pod creation — existing pods over quota continue running
- Namespace deletion is irreversible and cascades to all child resources; protect namespaces with finalizers
- Cross-namespace DNS (`svc.namespace.svc.cluster.local`) bypasses NetworkPolicy unless explicitly allowed
- LimitRange defaults only apply to pods created *after* the LimitRange; existing pods are unaffected

## Related
- `kubernetes-rbac-patterns.md`
- `kubernetes-network-policies.md`
- `kubernetes-resource-limits.md`
