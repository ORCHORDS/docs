# kubernetes-rbac-patterns

**Issue:** Least-privilege RBAC design for Kubernetes workloads and human operators
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Overly permissive ClusterRoles and default service accounts allow privilege escalation. This entry covers practical RBAC patterns for CI/CD pipelines, operators, and human personas.

## Pattern / Solution
Minimal service account for a deployment:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: myapp
  namespace: myapp
automountServiceAccountToken: false  # opt-in only

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: myapp-role
  namespace: myapp
rules:
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get", "watch", "list"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: myapp-rolebinding
  namespace: myapp
subjects:
- kind: ServiceAccount
  name: myapp
  namespace: myapp
roleRef:
  kind: Role
  name: myapp-role
  apiGroup: rbac.authorization.k8s.io
```

CI/CD deploy role (namespace-scoped):
```yaml
rules:
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets"]
  verbs: ["get", "list", "patch", "update"]
- apiGroups: [""]
  resources: ["services", "configmaps"]
  verbs: ["get", "list", "create", "patch", "update"]
```

Audit who can do what:
```bash
kubectl auth can-i create deployments --as=system:serviceaccount:myapp:myapp -n myapp
kubectl get rolebindings,clusterrolebindings -A \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.subjects[*].name}{"\n"}{end}'
```

RBAC audit tool:
```bash
kubectl-who-can create pods -n production
# or
rakkess --sa myapp -n myapp
```

## Gotchas
- `ClusterRole` bound via `RoleBinding` (not `ClusterRoleBinding`) limits scope to one namespace — use this intentionally
- `*` wildcard on verbs or resources is almost never correct; enumerate explicitly
- `automountServiceAccountToken: false` on the ServiceAccount is overridden per-pod by `automountServiceAccountToken: true` on the Pod spec
- Aggregated ClusterRoles (`rbac.authorization.k8s.io/aggregate-to-view: "true"`) silently expand permissions when new CRDs are installed

## Related
- `kubernetes-namespace-isolation.md`
- `kubernetes-network-policies.md`
- `secrets-in-deploy-2026.md`
