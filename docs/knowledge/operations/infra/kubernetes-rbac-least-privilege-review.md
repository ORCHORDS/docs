---
title: "RBAC Least-Privilege Review"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# RBAC Least-Privilege Review

## API semantics

RBAC rules contain `apiGroups`, `resources`, `verbs`, and optionally `resourceNames`; non-resource rules use `nonResourceURLs`. A Role is namespaced. A ClusterRole can contain cluster-scoped or namespaced rules and may be bound cluster-wide with ClusterRoleBinding or into one namespace with RoleBinding. Rules are additive: there is no deny. `resourceNames` cannot restrict `create` or `deletecollection` because the object name is not reliably available for authorization. Subresources are separate strings such as `pods/log`, `pods/exec`, and `serviceaccounts/token`.

## Minimal configuration

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: deployment-reader, namespace: shop}
rules:
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: support-read, namespace: shop}
subjects:
- {kind: Group, name: support@example.com, apiGroup: rbac.authorization.k8s.io}
roleRef: {kind: Role, name: deployment-reader, apiGroup: rbac.authorization.k8s.io}
```

## Ordering, versions, and edge cases

Treat `bind`, `escalate`, `impersonate`, Secret reads, workload creation, CSR approval, and service-account token requests as escalation-sensitive. A user who can create Pods can often run as any ServiceAccount in that namespace and mount Secrets available to it. ClusterRole aggregation labels (`aggregate-to-admin`, `aggregate-to-edit`, `aggregate-to-view`) can expand default roles when new labeled ClusterRoles appear. `roleRef` is immutable; replace a binding to change it. Avoid wildcard resources and verbs because newly installed APIs become authorized automatically.

## Deployment, evidence, and rollback

Test effective access with `kubectl auth can-i --as=system:serviceaccount:shop:api --list -n shop` and targeted negative checks such as `create pods/exec`, `get secrets`, and `create serviceaccounts/token`. Use audit events with response code 403 to find missing access, but do not grant directly from observed calls without threat review. Roll back by restoring the prior binding or Role rules; deleting an overbroad ClusterRole does not remove permissions supplied by another binding.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Review queries and escalation cases

Export Roles, ClusterRoles, RoleBindings, and ClusterRoleBindings with UIDs so replacement is distinguishable from mutation. Resolve group membership at the identity provider and expand ClusterRole aggregation before calculating effective access. Review non-resource URLs such as `/metrics`, `/healthz`, and wildcard paths separately from API resources.

Exercise SubjectAccessReview-compatible checks for each persona. `kubectl auth can-i` is convenient but its `--list` output can be incomplete for external authorizers; targeted checks are stronger evidence. Test `impersonate` on users, groups, and serviceaccounts; `create` on Pods, Jobs, DaemonSets, and webhook configurations; `patch` on namespace labels; and reads of Secrets. Watch audit records for `authorization.k8s.io/decision` where available and API 403 rates. Rollback must account for cached credentials and projected service-account tokens that remain valid until expiry even after a binding is removed.

## Sources

- [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/)
