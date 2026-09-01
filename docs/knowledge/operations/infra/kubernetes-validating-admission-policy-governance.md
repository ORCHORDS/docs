---
title: "ValidatingAdmissionPolicy Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# ValidatingAdmissionPolicy Governance

## API semantics

`ValidatingAdmissionPolicy` and `ValidatingAdmissionPolicyBinding` are `admissionregistration.k8s.io/v1`, stable since Kubernetes v1.30. A policy supplies `spec.matchConstraints`, CEL `validations`, optional `variables`, `auditAnnotations`, `matchConditions`, `paramKind`, and `failurePolicy`. A binding supplies `policyName`, `matchResources`, optional `paramRef`, and `validationActions`. Actions are `Deny`, `Warn`, and `Audit`; `Deny` cannot be combined with `Warn` in the same binding. All validation expressions must evaluate true for admission.

## Minimal configuration

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata: {name: replicas-limit}
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: ["apps"]
      apiVersions: ["v1"]
      operations: ["CREATE", "UPDATE"]
      resources: ["deployments"]
  validations:
  - expression: "!has(object.spec.replicas) || object.spec.replicas <= 20"
    message: "replicas must not exceed 20"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: {name: replicas-limit-production}
spec:
  policyName: replicas-limit
  validationActions: [Deny, Audit]
  matchResources:
    namespaceSelector:
      matchLabels: {environment: production}
```

## Ordering, versions, and edge cases

CEL exposes `object`, `oldObject`, `request`, `namespaceObject`, `authorizer`, and, when configured, `params`. DELETE may have `object` null; CREATE has no `oldObject`. Guard optional fields with `has()`. Parameters are Kubernetes resources named or selected by `paramRef`; `parameterNotFoundAction` controls missing matches. Policy and binding matching intersect. Check policy `status.typeChecking.expressionWarnings` before enforcement. CEL runtime or cost errors follow `failurePolicy`.

## Deployment, evidence, and rollback

First bind with `Audit` and inspect audit annotations, then add `Deny`. Use server-side dry-run for positive and negative objects. Monitor API audit events, rejected request rates, policy status warnings, and changes/deletion of bindings. A policy without a binding does nothing. Roll back by removing `Deny` from the binding or narrowing `matchResources`; keep the policy for diagnostics rather than deleting the only record of intended logic.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## CEL review cases

CEL equality and Kubernetes quantity/string handling require explicit tests. Use `object.metadata.labels`, list `all`/`exists`, and `authorizer` checks only with bounded expressions. Variables are evaluated lazily and make repeated logic auditable. `matchConditions` can exclude requests before validations, while `matchConstraints` establishes the API resources eligible for policy evaluation.

For parameterized policy, test a named `paramRef`, selector matching zero objects, matching multiple objects, and caller authorization to read parameters. One request may be evaluated for each selected parameter object and must pass all applicable evaluations. Capture `status.observedGeneration` and type-check warnings after every policy update. Audit actions add policy/binding-derived annotations; Warn reaches interactive clients but may be hidden by automation. A rollback that removes a binding should be followed by a deliberate violating dry-run proving enforcement is actually absent only in the intended scope.

## Sources

- [VAP](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)
- [CEL](https://kubernetes.io/docs/reference/using-api/cel/)
