# CNCF Kyverno Policy-as-Code Governance

## Purpose

Kyverno is a Kubernetes-native policy engine (CNCF Incubating project) that validates, mutates, and generates Kubernetes resources using YAML or JSON policies without a separate policy language. As an admission controller, Kyverno intercepts API server requests and applies rules expressed in familiar Kubernetes syntax. The governance pattern captures the policy lifecycle (authoring, testing, distribution, exemption), the validation pipeline, and the documented mutation and generation rules so that policy drift across clusters is prevented.

## Current context and source status

Kyverno 1.10 (released 2024) and Kyverno 1.11 (released 2025) are the current supported versions. Kyverno 1.12 entered beta in 2026. The Kyverno CLI (`kyverno`) supports `apply`, `test`, `validate`, and `jp` (JMESPath) subcommands. The project follows the CNCF Incubating governance model.

## Governance pattern

1. Author policies in YAML using the `kyverno.io` API group, organized by namespace and severity (`low`, `medium`, `high`).
2. Use `validationFailureAction: Enforce` for production-critical rules; `Audit` for observability-only rules.
3. Define `match` and `exclude` blocks precisely to avoid over- or under-applying policies.
4. Use `validationFailureActionOverrides` for temporary exceptions during migrations.
5. Write a `kyverno test` suite alongside each policy that pairs valid and invalid fixtures with expected pass/fail outcomes.
6. Pin Kyverno version, chart version, and CRD version in the cluster bootstrap.
7. Distribute policies as ConfigMaps or Helm charts through GitOps; never apply ad-hoc.
8. Maintain a PolicyException list with owner, justification, and expiry date.
9. Monitor Kyverno metrics (Prometheus) for the rate of policy failures per rule.
10. Route high-severity failures to admission denial logs and SIEM.

## Validation and evidence

- `kyverno validate` returns 0 exit for each policy file.
- `kyverno test ./...` returns 0 with all fixtures matching expected outcomes.
- Cluster install records the version, chart, and CRD versions.
- GitOps reconciliation log records the applied policy set.
- PolicyException list is reconciled against the active exceptions.
- Prometheus metrics show policy failure rate per rule.

## Failure correction

Common defects include policies that match too broadly (blocking legitimate workloads), `validationFailureAction: Enforce` set before testing, and PolicyExceptions without expiry. Corrective actions include narrowing the `match` block, flipping to `Audit` during test rollout, and adding expiry date enforcement in CI.

## Limitations

- Kyverno policies do not extend to non-Kubernetes resources (use OPA for non-K8s policies).
- Mutation and generation rules must be idempotent; non-idempotent mutations cause reconcile loops.
- Background scans are best-effort and may miss fast-changing resources.
- Kyverno does not support post-admission remediation for already-deployed resources.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (Kyverno deployment topology), **security** (admission control and supply-chain security), **engineering** (policy testing in CI), and **templates** (reusable Kyverno policy skeletons). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- Kyverno documentation (CNCF Incubating): https://kyverno.io/docs/
- Kyverno GitHub repository (CNCF Incubating): https://github.com/kyverno/kyverno
- Kyverno policy reference (CNCF Incubating): https://kyverno.io/policies/

Sources were verified on September 1, 2026.