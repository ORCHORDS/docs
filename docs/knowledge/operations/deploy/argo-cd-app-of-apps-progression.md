# Argo CD App-of-Apps Progression

**Issue:** Multi-tenant Kubernetes platforms must express cluster-wide application composition in Git, and operators who jump straight from a single Application to a complex layered topology encounter combinatorial sync failures. The App-of-Apps pattern is the canonical Argo CD response, and progressing through it in deliberate stages avoids the failure mode where a broken parent manifest propagates to every dependent application.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Topology

App-of-Apps is an Application whose manifest declares other Applications. The parent Application, pointing at the bootstrap Git repository, reconciles children that each point at their own application repository or path. Children can themselves be parents, producing a tree. Sync waves, sync phases, and ApplicationSet generators extend the pattern into policy-managed fleets, but the core mechanism remains: an Application is a CRD whose `spec.source` and `spec.destination` define a reconciliation unit.

The progression model organizes the topology into layers. The root application is a thin bootstrap that points to a curated list of platform applications. Platform applications define shared services (ingress, cert-manager, monitoring) and may themselves declare tenant overlays. Tenant applications are leaf nodes that the platform team does not touch directly; they are owned by the application team but reconciled by the same Argo CD instance.

## Progression Stages

Stage 1 is a single Application per environment, with no App-of-Apps. This is the right starting point because every debugging step is local and sync failure messages are unambiguous. Stage 2 introduces a bootstrap Application that points to a directory of child Application manifests; each child uses `path:` and `chart:` to declare its own source. Stage 3 introduces ApplicationSet with cluster generators so a single Git path can deploy across multiple clusters without per-cluster child manifests.

Stage 4 adds sync waves and hooks at the leaf level, because by now the platform has policy on resource ordering that the children cannot satisfy on their own. Stage 5 introduces a hub-and-spoke topology where a separate cluster runs the controller and remote spokes pull from the same Git source. The progression is enforced by review: any PR that introduces Stage N+1 features must justify why Stage N is insufficient, and the justification is recorded in the repository's CONTRIBUTING file.

## Sync Policy Choices

Each Application has a sync policy that can be manual, automated, or automated with self-heal. The default for platform applications should be `automated: true` with self-heal enabled, because drift detection and remediation is the entire point of running a controller. Tenant applications should default to manual sync, because their release cadence is owned by the application team and an automated sync could conflict with in-cluster operators that the controller does not know about.

Prune propagation deserves careful thought. When `prune: true` is set on the parent, deletion of a child from the parent manifest cascades to the cluster. This is the desired behavior for ephemeral environments but is dangerous for production. Use the `prune: false` policy for production roots, and rely on a separate workflow for explicit teardown. Argo CD supports `pruneLast: true` on sync options to delay pruning until after successful sync, reducing blast radius.

## Sync Failure Cascades

The most severe App-of-Apps incident is a parent manifest that fails to sync because of an indentation error in YAML. The parent goes OutOfSync and Healthy=False, but the children remain at their last-known-good state. The remediation path is to fix the parent, commit, and let Argo CD reconcile; no children are touched. This works as long as children do not depend on parent-level annotations or labels that the parent applies to its own namespace.

A worse cascade occurs when the parent is healthy and pruning is enabled, and a team member deletes a child declaration thinking it is an orphan. Argo CD prunes the corresponding Application and the Application controller deletes its resources. The mitigation is to require that any child removal in the parent manifest be made via two-step process: first add the `argo-cd.argoproj.io/compare-options: IgnoreExtraneous` annotation to the parent so the deletion is ignored, then physically remove the declaration only after cluster confirmation.

## Failure Modes

The most common pattern failure is a parent manifest that embeds secrets inline so that Argo CD can render its own Application resources without external secret lookups. This works in development but creates a credential sprawl problem. The parent should reference External Secrets, sealed-secrets resources, or a secret manager; the parent manifest stays clean, and the Application CRD itself never contains secret material.

A second failure is the root Application declaring children from many Git repositories with different rate limits. When one child repository's API rate limit is exceeded, Argo CD marks the child as suspended but the parent still reconciles. Operators can chase phantom outages for hours before realizing the issue is rate limiting, not cluster state. Configure Git providers to emit rate-limit signals into Prometheus and alert when child reconciliation is throttled.

A third failure is when children have inter-resource dependencies that Argo CD cannot detect. For example, Application A declares a namespace that Application B then populates. If A fails, B's sync proceeds and the resources end up in an unintended namespace. Use sync waves and Application-level dependencies (`dependencies:` field) to make Argo CD aware of the ordering, and never rely on application-level namespacing for cross-application dependency enforcement.

## Canonical sources

1. https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/
2. https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#applications