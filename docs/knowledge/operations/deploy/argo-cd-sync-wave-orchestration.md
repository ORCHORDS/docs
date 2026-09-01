# Argo CD Sync Waves Orchestration

**Issue:** Argo CD reconciles resources in parallel by default, and complex applications whose resources have implicit dependencies on each other fail to deploy because the dependent resource reaches Ready before its dependency is reconciled. Sync waves and hooks give operators a way to express ordering declaratively, but the mechanism is misunderstood as a global scheduler rather than a per-resource annotation, which leads to brittle orchestration that breaks under reordering or partial failure.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How Sync Waves Actually Work

A sync wave is an annotation on a resource manifest of the form `argocd.argoproj.io/sync-wave: "5"`, where the value is a non-negative integer. During a sync, Argo CD collects all resources in the application, sorts them by wave value ascending, and applies resources in the same wave concurrently. The default wave is zero, so any annotated resource moves ahead of unannotated ones. Hooks (PreSync, Sync, PostSync, SyncFail) provide finer control within a wave.

Waves are local to the application, not global across the cluster. Two Applications with overlapping resource sets apply their own wave ordering independently. This is the source of confusion when teams expect cross-application ordering; Argo CD does not provide that, and the correct pattern is to declare a single parent Application that owns both sets so the wave annotation has access to all resources at sort time.

## Constructing A Wave Topology

A useful starting wave topology for a typical application is wave 0 for namespaces, wave 1 for secrets and configmaps, wave 2 for service accounts and RBAC, wave 3 for Deployments and StatefulSets, wave 4 for network resources such as Ingress and Service of type LoadBalancer, and wave 5 for PostSync hooks that perform health checks or smoke tests. Resource Kinds within a wave apply concurrently, so a Deployment and a Service in wave 3 will appear together; the Deployment's pod startup still depends on the Service existing for DNS.

PreSync and PostSync hooks are also assigned to waves and run synchronously within the hook phase. A PreSync hook in wave 1 runs before any other wave 1 resources apply; a PostSync hook in wave 5 runs after all wave 5 resources apply. The hook phase itself is a synchronization point: Argo CD pauses the entire sync until the hook's success policy is met. By default a hook succeeds when the underlying resource reports Successful or Healthy.

## Health And Resource Status

Argo CD's resource status is computed from a Kubernetes kind-specific health check. Deployments are Healthy when desired replicas are available; StatefulSets require an ordered update; Jobs succeed when completions are reached; PVCs are Healthy when bound. The sync waits for Healthy status to be reported before moving to the next wave, which gives orchestration its robustness: a Deployment in wave 3 will not race ahead if its pod fails to start, because the next wave's resources will not apply until the wave 3 Deployment reports Healthy.

This blocking behavior is also why wave ordering matters for resource kinds that do not report Healthy quickly. A Deployment with a misconfigured readiness probe that always fails will block the sync indefinitely. Set `metadata.annotations[argocd.argoproj.io/healthy]` to a literal value for resources that Argo CD cannot introspect, and use the `IgnoreExtraneous` and `DisableHealthCheck` options for resources that should not block wave advancement.

## Multi-Application Dependencies

When Application A must deploy before Application B, the standard pattern is to declare Application B with a `dependencies` block referencing Application A. Argo CD then refuses to sync B until A's status is Healthy and Synced. The dependency is enforced at the controller level, not by sync wave. This is the correct mechanism for cross-application ordering because it survives partial cluster states that a wave annotation alone cannot handle.

A common anti-pattern is to use sync waves to express cross-application dependencies, which works only because both Applications happen to apply to the same cluster and the timing happens to align. A subsequent change to either Application's source repository breaks the implicit timing. Always declare cross-application dependencies explicitly, and reserve sync waves for resources within a single Application.

## Failure Modes

The most common failure is excessive wave use, where teams assign distinct wave numbers to every logical layer of a five-tier application, producing a topology that no one understands. Resist the urge; waves should be coarse, three to six levels is sufficient for most applications. Fine-grained ordering should be expressed through Kubernetes resource references (Service -> Pod labels, Ingress -> Service) or through operators that handle their own reconciliation.

A second failure is hook resources not being cleaned up after a sync. Argo CD retains hook resources unless the manifest explicitly marks them with `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation` or `HookSucceeded`. Long-running clusters accumulate Job resources from PostSync hooks, cluttering the namespace and eventually triggering namespace quota issues. Audit hook cleanup policy as part of every release that introduces or modifies a hook.

A third failure is sync wave values that collide across teams because the convention is not documented. A platform team using wave 5 for PostSync health checks and a tenant team using wave 5 for ingress creation produces a silent ordering inversion. Document the wave conventions in the platform repository's CONTRIBUTING file, lint manifests for wave usage that violates the convention, and run a smoke test that ensures the expected ordering is observed.

## Canonical sources

1. https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/#sync-waves
2. https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/