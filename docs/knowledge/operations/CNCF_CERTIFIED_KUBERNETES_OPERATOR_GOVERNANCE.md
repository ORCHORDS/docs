# CNCF Certified Kubernetes Operator Governance

## Purpose

The CNCF Certified Kubernetes Application Developer (CKAD) and Certified Kubernetes Administrator (CKA) programs validate operational competence with Kubernetes, while the operator pattern is the standard approach to packaging and managing Kubernetes-native applications. This article governs the application of the operator model and Kubernetes operator certification practices so engineering teams can adopt operators for the applications they manage on Kubernetes.

## Scope

The article applies to engineering teams that operate Kubernetes clusters and run Kubernetes-native workloads. Within this knowledge base, the article covers the operator pattern (custom resources, controllers, reconciliation loops), the design considerations (scope, lifecycle, observability, upgrade strategy), the operator lifecycle, and the documentation of operator behavior. It does not cover a specific operator framework (Operator SDK, Kubebuilder, KOPF); readers should select the framework that fits their context.

## Workflow

1. Identify the application or service for which an operator is appropriate. Operators are most useful for stateful or complex lifecycle applications where the operational steps benefit from automation.
2. Define the Custom Resource Definitions (CRDs) the operator manages. Each CRD should have a stable schema, version, and validation.
3. Implement the controller:
   - Watch the CRD resources.
   - Reconcile the desired state against the actual state.
   - Update the status to reflect progress.
   - Handle errors with backoff and retry.
4. Implement the operator's lifecycle: install, upgrade, and uninstall. Each transition should be testable and reversible.
5. Implement observability — metrics, logs, traces, and conditions — so the operator's behavior is reviewable in production.
6. Document the operator's CRDs, behavior, configuration, and operational procedures.
7. Test the operator in a non-production environment covering failure scenarios and upgrade paths before production deployment.

## Controls and evidence

Operator controls include the CRD definitions, the controller implementation, the operational procedures, the upgrade plan, and the observability. Evidence includes the CRD manifests, the test results (unit, integration, end-to-end, chaos), the production metrics, and the documented runbooks.

## Validation

Validation should confirm the CRDs are stable and validated, the controller reconciles to the desired state, the lifecycle operations work, observability produces useful information, and the documented procedures are followed. Production incident reviews confirm the operator's behavior under failure.

## Failure correction

Common failure modes: CRDs are changed without versioning (corrective: version CRDs and follow Kubernetes' conversion webhook pattern); reconciliation loop has bugs that cause flapping (corrective: add requeue logic, status conditions, and chaos testing); operator upgrades are not tested (corrective: test upgrades in a non-production environment covering multiple versions); observability is missing (corrective: add metrics, logs, traces, and CR conditions for inspection); uninstall is not tested (corrective: test uninstall in a non-production environment).

## Limitations

The operator pattern is one approach to managing Kubernetes-native applications; for simple stateless workloads, raw Deployments may be sufficient. Operators require careful design and testing; a poorly designed operator can be worse than manual management. The article does not certify any operator or any operator framework.

## Scope note

This article summarizes project-neutral operational use of Kubernetes operators and CNCF-certified Kubernetes practices. It does not assert any specific deployment's conformance or claim any certification outcome.

## Canonical sources

- CNCF — Kubernetes: https://www.cncf.io/projects/kubernetes/
- CNCF — Certification Programs: https://www.cncf.io/certification/
- Kubernetes Documentation — Operators: https://kubernetes.io/docs/concepts/extend-kubernetes/operator/
- Kubernetes Operator Pattern — CoreOS 2016 white paper (historical reference): https://coreos.com/blog/introducing-operators.html