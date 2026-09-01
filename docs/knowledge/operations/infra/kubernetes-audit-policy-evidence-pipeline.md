---
title: "Audit Policy and Evidence Pipeline"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Audit Policy and Evidence Pipeline

## API semantics

An `audit.k8s.io/v1` Policy is an ordered list: the first matching rule selects `None`, `Metadata`, `Request`, or `RequestResponse`. Rules can match `users`, `userGroups`, `verbs`, `resources`, `namespaces`, and `nonResourceURLs`. `omitStages` suppresses stages such as `RequestReceived`. Audit stages are `RequestReceived`, `ResponseStarted`, `ResponseComplete`, and `Panic`; long-running requests such as watches may emit `ResponseStarted` and much later `ResponseComplete`. Request bodies at Request/RequestResponse can contain credentials or Secret data.

## Minimal configuration

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
omitStages: ["RequestReceived"]
rules:
- level: Metadata
  resources:
  - group: ""
    resources: ["secrets"]
- level: Request
  verbs: ["create", "update", "patch", "delete"]
  resources:
  - group: "rbac.authorization.k8s.io"
    resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]
- level: Metadata
```

## Ordering, versions, and edge cases

API-server flags configure log or webhook backend, including path/config, batch mode, buffer, maximum age/backups/size, and truncation. An event includes `auditID`, stage, request URI, verb, user, source IPs, object reference, response status, timestamps, annotations, and possibly request/response objects. Policy changes require API-server configuration rollout; validate the same policy hash on every replica. Use Metadata for Secret access to avoid recording values.

## Deployment, evidence, and rollback

Generate allowed, 403, 404, impersonated, exec, token-request, and watch traffic, then correlate by `auditID`. Monitor `apiserver_audit_event_total` and `apiserver_audit_error_total` plus backend ingest lag and parse failures. Test disk full or webhook outage under the selected blocking/batch mode. Roll back to the previous policy and flags through control-plane configuration management; verify events continue across the rollout and preserve the failed policy for forensic comparison.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Event selection and confidentiality

Put narrow exclusions and sensitive-resource rules before broad catch-alls. Resource rules may include subresources; explicitly test `pods/exec`, `pods/attach`, `pods/portforward`, `serviceaccounts/token`, and eviction. Non-resource URL matching supports a trailing wildcard. `RequestResponse` can produce very large records and should be limited to investigation-critical resources after data classification.

Audit webhooks use a kubeconfig and can batch events, creating a loss window during process failure. Log backend rotation limits local retention; shipping must complete before rotation removes files. Compare event counts at API server and collector and alarm on gaps. Verify Unicode, truncation, large object, and watch events parse correctly. For incident evidence preserve raw event bytes, audit policy hash, API-server identity, and collector receipt time. Rolling back a policy cannot reconstruct events that were assigned `None`; document that irreversibility in change approval.

## Sources

- [Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/)
- [Audit API](https://kubernetes.io/docs/reference/config-api/apiserver-audit.v1/)
