---
title: "Admission Controller Chain Design"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Admission Controller Chain Design

## API semantics

Authentication and authorization precede admission. Mutating admission runs before validating admission; built-in plugins and dynamic webhooks participate in those phases. A mutating webhook can be reinvoked when later mutations affect its input, so patches must be idempotent. `MutatingWebhookConfiguration` and `ValidatingWebhookConfiguration` use `webhooks[].rules`, `namespaceSelector`, `objectSelector`, `matchPolicy`, `matchConditions`, `failurePolicy`, `sideEffects`, `timeoutSeconds`, and `admissionReviewVersions`. `matchPolicy: Equivalent` lets the API server convert equivalent versions before calling the webhook.

## Minimal configuration

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata: {name: image-policy}
webhooks:
- name: images.policy.example
  admissionReviewVersions: ["v1"]
  sideEffects: None
  failurePolicy: Fail
  timeoutSeconds: 3
  matchPolicy: Equivalent
  clientConfig:
    service: {namespace: policy-system, name: image-policy, path: /validate}
    caBundle: BASE64_CA
  rules:
  - operations: ["CREATE", "UPDATE"]
    apiGroups: ["apps"]
    apiVersions: ["v1"]
    resources: ["deployments"]
    scope: Namespaced
```

## Ordering, versions, and edge cases

The webhook response must repeat the request UID and set `allowed`; mutators return a base64 JSONPatch with `patchType: JSONPatch`. Do not rely on webhook ordering: configuration order is not a stable policy contract. Keep timeout at 1–30 seconds and avoid recursive calls that match the same webhook. `failurePolicy: Fail` rejects on timeout/error; `Ignore` admits and should emit a separately monitored fail-open signal. Exclude the webhook's own recovery namespace only when that bypass is explicitly governed.

## Deployment, evidence, and rollback

Inspect `apiserver_admission_webhook_admission_duration_seconds`, `apiserver_admission_webhook_rejection_count`, API-server audit records, webhook HTTP status, and certificate expiry. Test malformed AdmissionReview, timeout, TLS failure, version conversion, dry-run (`sideEffects` must permit it), and reinvocation. Roll back by narrowing selectors or deleting only the failing webhook entry; retain a separately authenticated API-server recovery procedure if Fail blocks all matching writes.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Request and response contract

An AdmissionReview request identifies UID, kind, resource, subresource, operation, userInfo, object, oldObject, options, dryRun, and requestKind/requestResource after equivalent matching. Validators return status details for useful client errors. Mutators must encode RFC 6902 operations and avoid overwriting fields owned by another injector. Audit the final stored object to prove mutation outcome.

Set `reinvocationPolicy: IfNeeded` only for mutating webhooks designed for it. Use `matchConditions` CEL to exclude narrow request classes without another network call. Service references require working cluster DNS/network and a CA bundle that validates the serving name; URL references add external routing dependencies. During rollout, graph p50/p99 latency and timeout count per webhook. Before rollback, determine whether previously mutated objects need cleanup—removing a mutator does not reverse patches already persisted.

## Sources

- [Dynamic admission](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/)
