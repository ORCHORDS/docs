# Kubernetes Operators and Custom Resource Definitions (CRDs)

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team manages a PostgreSQL cluster on Kubernetes using a
StatefulSet with manual runbooks for backup, failover, and schema
migration. A node failure at 3 AM requires an on-call engineer to
manually promote a replica, update the service endpoint, and verify
replication health. The recovery takes 45 minutes. Meanwhile, the
team maintaining an internal Redis deployment has written a shell
script that watches Redis pods and restarts them on failure — but
the script has no leader election, runs on a single node, and
silently stops working when OOMKilled.

## Context

A Kubernetes Operator encodes domain-specific operational knowledge
into a controller that automates day-2 operations (backup, failover,
scaling, upgrades) for a Custom Resource Definition (CRD). The
operator pattern extends Kubernetes by defining new API types (CRDs)
and implementing a reconciliation control loop that continuously
drives the observed state toward the desired state defined in the
custom resource's spec. Operator frameworks (Kubebuilder, Operator
SDK) scaffold the controller, CRD schema, RBAC, and testing
infrastructure. OLM (Operator Lifecycle Manager) manages operator
installation and upgrades on clusters. OperatorHub.io catalogs 300+
community operators.

## Custom Resource Definitions

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: databases.example.com
spec:
  group: example.com
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                engine:
                  type: string
                  enum: [postgres, mysql]
                replicas:
                  type: integer
                  minimum: 1
                  maximum: 10
                storage:
                  type: string
              required: [engine, replicas]
      subresources:
        status: {}
  scope: Namespaced
  names:
    plural: databases
    singular: database
    kind: Database
    shortNames: [db]
```

```
CRD features:
  → Extends Kubernetes API without custom API server
  → OpenAPI v3 schema validation on spec fields
  → Status subresource for controller-managed state
  → Versioning with conversion webhooks
  → Printer columns for kubectl output
  → Categories for grouping (kubectl get all)
```

## Reconciliation loop pattern

```
The reconciler is the core of an operator:

  1. Watch for changes to the custom resource
  2. Compare observed state vs desired state (spec)
  3. Take action to drive convergence
  4. Update status subresource with observed state
  5. Requeue if convergence not yet achieved

  Requirements:
    → IDEMPOTENT — same result regardless of how many
      times reconcile runs
    → LEVEL-TRIGGERED — react to current state, not just
      the event that triggered reconciliation
    → Self-healing from missed or duplicate events
```

```go
// controller-runtime Reconcile interface (Go)
func (r *DatabaseReconciler) Reconcile(
    ctx context.Context,
    req ctrl.Request,
) (ctrl.Result, error) {
    var db examplev1.Database
    if err := r.Get(ctx, req.NamespacedName, &db); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // Compare desired vs observed
    // Create/update/delete owned resources
    // Update status

    return ctrl.Result{}, nil
}
```

## Status subresource

```
Enabling /status as a separate subresource:

  Benefits:
    → Controllers update observed state without
      triggering spec-change reconciliation
    → Clients cannot mutate status directly
    → Enforces spec/status separation convention

  Kubebuilder marker:
    //+kubebuilder:subresource:status

  CRD YAML:
    subresources:
      status: {}

  Status typically contains:
    → Phase (Running, Failed, Pending)
    → Conditions (Ready, Available, Degraded)
    → ObservedGeneration (spec version last reconciled)
    → Instance-specific state (endpoints, replicas ready)
```

## Finalizers

```
Finalizers handle cleanup before deletion:

  1. Controller adds finalizer string to metadata.finalizers
  2. On delete: Kubernetes sets deletionTimestamp
  3. Object kept alive until ALL finalizers removed
  4. Controller detects deletionTimestamp
  5. Runs cleanup (deprovision cloud resource, delete PVCs)
  6. Removes its finalizer from the list
  7. Object deleted when finalizer list is empty

  Standard pattern for:
    → Deprovisioning external cloud resources
    → Cleaning up child resources not owned via OwnerReference
    → Revoking external credentials or DNS records
```

## Leader election

```
For HA operator deployments (multiple replicas):

  → Only one pod actively reconciles at a time
  → Uses Lease-based lock in the API server
  → Prevents conflicting concurrent writes

  controller-runtime config:
    mgr, err := ctrl.NewManager(cfg, ctrl.Options{
        LeaderElection:          true,
        LeaderElectionID:        "database-operator-lock",
        LeaderElectionNamespace: "operator-system",
    })

  On leader loss:
    → Standby pod takes over automatically
    → In-progress reconciliations are retried by new leader
```

## Operator frameworks

```
Framework       Language        Notes
──────────────────────────────────────────────────────────────
Kubebuilder     Go              Scaffolds on controller-runtime;
                                marker-based CRD/RBAC generation;
                                envtest for integration testing

Operator SDK    Go, Ansible,    CNCF project; Go operators are
                Helm            Kubebuilder-compatible; Ansible
                                for ops-team-friendly operators

Metacontroller  Any (webhook)   Meta-operator; reconciliation
                                logic as HTTP webhook in any
                                language; CompositeController
                                and DecoratorController patterns
```

## When to build vs alternatives

```
Build an operator when:
  → Non-trivial day-2 operations (backup, failover, migration)
  → Operational logic can't be expressed by Deployment/
    StatefulSet/HPA alone
  → Application-specific health checks and remediation
  → Complex multi-step provisioning workflows

Use alternatives when:
  → Stateless workload with simple lifecycle → Deployment
  → Stable ordered pods → StatefulSet
  → Template-based config → Helm chart
  → Simple scaling rules → HPA/KEDA
  → Operator adds more maintenance burden than value
```

## Testing operators

```
Test level       Tool/approach
──────────────────────────────────────────────────────────────
Unit tests       Fake client (controller-runtime/pkg/client/fake)
                 for logic-only coverage

Integration      envtest (Kubebuilder) — real API server + etcd
tests            without kubelet; fast, no full cluster needed

E2E tests        kind or k3d clusters for full cluster behavior

What to test:
  → Reconcile creates expected child resources
  → Status updated correctly after reconciliation
  → Finalizer cleanup works on deletion
  → Error handling and requeue behavior
  → Idempotency (reconcile twice = same result)
```

## Anti-patterns

- **Building an operator for simple deployments** — if a Helm
  chart or plain manifests suffice, an operator adds unnecessary
  maintenance burden (CRD versioning, conversion webhooks, RBAC,
  upgrade compatibility testing).
- **Non-idempotent reconcilers** — reconcile functions that
  create duplicate resources on re-run or fail on the second
  execution. Every reconcile call must produce the same result.
- **Mutating spec in the reconciler** — controllers should write
  to status only. Spec changes should come from users or other
  controllers, not the reconciler itself.
- **Missing finalizers for external resources** — without
  finalizers, deleting the custom resource orphans external
  cloud resources (databases, DNS records, certificates).

## Gotchas

- **CRD schema changes require conversion webhooks** — changing
  the stored version of a CRD requires a conversion webhook to
  translate between versions. Plan for version evolution from
  the start.
- **Status subresource prevents status-only updates from
  triggering reconciliation** — this is intentional but can
  confuse developers who expect every update to trigger the
  reconciler.
- **envtest does not run kubelet** — tests using envtest cannot
  test pod scheduling, node affinity, or resource limits. Use
  kind/k3d for those scenarios.
- **OLM v1 is the active successor** — classic OLM is being
  replaced by the `operator-controller` project (OLM v1).
  New operator packaging should target the newer format.

## Verification

- CRD schema includes OpenAPI v3 validation.
- Reconciler is idempotent and level-triggered.
- Status subresource enabled and used for observed state.
- Finalizers handle cleanup of external resources.
- Leader election configured for HA deployments.
- envtest integration tests cover reconcile, status, and delete.
- RBAC scoped to minimum required permissions.

## Related

- `documentation/docs/policies/infra/kubernetes-autoscaling-hpa-keda.md`
- `documentation/docs/policies/infra/kubernetes-network-policies-service-mesh.md`
- `documentation/docs/policies/deploy/kubernetes-rollout-strategies-argo-rollouts.md`

## Source URLs (verified 2026-08-16)

- Kubernetes — Custom Resource Definitions — https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/
- Kubebuilder Book — Using Finalizers — https://book.kubebuilder.io/reference/using-finalizers.html
- Kubebuilder Book — Getting Started — https://book.kubebuilder.io/
- Red Hat — Developer's Guide to Kubernetes Operators — https://developers.redhat.com/articles/2024/01/29/developers-guide-kubernetes-operators
