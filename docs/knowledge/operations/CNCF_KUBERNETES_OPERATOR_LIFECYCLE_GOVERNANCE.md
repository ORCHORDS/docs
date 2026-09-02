# CNCF Kubernetes Operator Lifecycle Governance

## Purpose

Kubernetes Operators extend the Kubernetes control plane through custom resources and controllers that encode operational domain knowledge. The operator lifecycle governance pattern captures the install method (OLM, Helm, plain manifests), the upgrade strategy (in-place, blue-green, canary), the CRD version compatibility matrix, the backup and restore procedure, and the documented decommissioning process. Without explicit governance, operators drift across clusters and create irreconcilable version skew.

## Current context and source status

The Operator Framework (CNCF Sandbox, formerly CoreOS/Red Hat) includes the Operator Lifecycle Manager (OLM), Operator Registry, and OperatorHub. Operator SDK (CNCF Sandbox) provides scaffolding for Go, Ansible, and Helm-based operators. Kubebuilder is the canonical Go scaffolding tool. The OperatorHub and community-operators catalogs distribute OLM bundles.

## Governance pattern

1. Inventory every Operator in use with version, install method, and CRD API versions.
2. Pin Operator and CRD versions in cluster bootstrap (use Renovate or Dependabot for chart versions).
3. Use OLM for Operators that distribute as OLM bundles; use Helm for non-OLM Operators.
4. Document CRD version compatibility: v1beta1 deprecated in Kubernetes 1.22, removed in 1.25+; migrate to v1.
5. Plan operator upgrades with the documented compatibility matrix; test in staging.
6. Define the upgrade strategy per operator: in-place, blue-green (for data plane operators), canary (using Argo Rollouts).
7. Back up CRDs and CR instances before operator upgrade; verify restore procedure.
8. Monitor operator metrics: `controller_runtime_reconcile_total`, `controller_runtime_reconcile_errors_total`, leader-election status.
9. Document the decommissioning process: remove CR instances, delete CRD, uninstall Operator, verify cluster stability.
10. Route operator upgrade failures to the on-call runbook.

## Validation and evidence

- Operator inventory in version control.
- Operator and CRD versions recorded in cluster inventory.
- Operator upgrade tested in staging before production.
- Backup and restore procedure documented and tested.
- Operator metrics dashboard deployed.
- Decommissioning runbook published.

## Failure correction

Common defects include upgrading without testing in staging, missing backup before upgrade, and orphaned CR instances after uninstall. Corrective actions include enforcing staging-test gate in CI, requiring pre-upgrade backup, and adding orphan-CR check to the decommissioning runbook.

## Limitations

- Operators do not provide a generic data-plane (use platform-specific operators like Postgres Operator).
- OLM does not support all CRD features (for example, conversion webhooks across multiple versions).
- Operator upgrade may not migrate CR instance schema; manual migration may be required.
- Operator uninstall does not always cascade-delete CR instances.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (operator deployment topology), **engineering** (operator SDK and controller patterns), **security** (operator RBAC and least privilege), and **templates** (operator deployment manifest template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- Operator Framework documentation (CNCF Sandbox): https://operatorframework.io/
- Operator SDK GitHub repository (CNCF Sandbox): https://github.com/operator-framework/operator-sdk
- Kubernetes documentation, Operator pattern: https://kubernetes.io/docs/concepts/extend-kubernetes/operator/

Sources were verified on September 1, 2026.