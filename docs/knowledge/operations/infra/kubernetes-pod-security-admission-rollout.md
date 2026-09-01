---
title: "Pod Security Admission Rollout"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Pod Security Admission Rollout

## API semantics

Pod Security Admission (PSA) is the built-in admission controller for PSS. Namespace labels are `pod-security.kubernetes.io/{enforce,audit,warn}` and optional `pod-security.kubernetes.io/{enforce,audit,warn}-version`. Values are `privileged`, `baseline`, or `restricted`; versions are `latest` or `v1.N`. `enforce` rejects a violating pod, `warn` returns an HTTP warning to the requesting client, and `audit` adds audit annotations. PSA evaluates pod creation and security-relevant pod updates, including ephemeral-container updates; it does not scan, mutate, or evict pods already running.

## Minimal configuration

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: payments
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/enforce-version: v1.35
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.35
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.35
```

## Ordering, versions, and edge cases

The admission configuration can exempt exact usernames, RuntimeClass names, or namespaces. Exempting a controller username exempts every pod it creates; exempting a namespace bypasses all profiles there. Store exemptions in API-server configuration and compare every control-plane replica. Protect namespace-label mutation with RBAC because anyone able to lower `enforce` can bypass PSA. Deployments require special testing: Deployment admission may succeed while the ReplicaSet receives pod denials and emits `FailedCreate` events.

## Deployment, evidence, and rollback

Run `kubectl label --dry-run=server --overwrite ns payments pod-security.kubernetes.io/enforce=restricted` to preview label admission, then create violating direct Pods and Deployments. Inspect `kubectl get events -n payments`, ReplicaSet conditions, client Warning headers, and audit annotations with prefix `pod-security.kubernetes.io/`. Roll back to the prior profile/version labels and verify a fresh controller pod is admitted; do not expect rejected or existing pods to be repaired automatically.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Admission configuration and coverage

Cluster-wide exemptions live in `PodSecurityConfiguration`, whose defaults and exemptions specify enforce/audit/warn levels and usernames, RuntimeClasses, or namespaces. Managed services may expose only namespace labels; record that limitation. Namespace labels are evaluated using the namespace object visible to admission, so GitOps drift and manual relabeling are security events.

Build a matrix covering CREATE Pod, controller-created Pod, UPDATE of mutable pod fields, `pods/ephemeralcontainers`, and exempt/non-exempt RuntimeClasses. A dry-run request still exercises admission but creates no object. Capture HTTP 403 Status objects for enforce denials, Warning headers for warn, and audit annotations for audit. Track namespaces lacking explicit labels because they inherit cluster defaults. During rollback, restore all six labels atomically from version control and verify the API-server admission configuration itself did not change.

## Sources

- [PSA](https://kubernetes.io/docs/concepts/security/pod-security-admission/)
- [Enforce PSS](https://kubernetes.io/docs/tasks/configure-pod-container/enforce-standards-namespace-labels/)
