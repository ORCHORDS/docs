# kubernetes-operator-pattern

**Issue:** A stateful system (a database, a certificate authority, a message queue) needs real operational knowledge to run: version-specific upgrade orders, backups before schema changes, failover when a node dies. Doing this by hand does not scale past a handful of instances, and stuffing it into Helm hooks or CI scripts makes the logic invisible to the cluster. The Kubernetes operator pattern packages that operational knowledge as a custom controller — a loop that watches the desired state in a Custom Resource and continuously drives the cluster toward it. This article covers when the pattern pays off, the reconciliation model that makes it work, and the failure modes that bite first-time operator authors.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When an Operator Is the Right Answer

1. **There is a stateful resource with operational procedures.** Operators earn their keep when day-2 operations exist at all — scaling a Cassandra ring, rotating certs, orchestrating a primary failover; for stateless apps a Deployment plus an HPA already is the automation and a custom controller is over-engineering.
2. **The knowledge is repeatable and expressible as desired state.** If the runbook can be phrased as "given a spec saying 5 replicas with version 4.1, make reality match," an operator fits; if it is genuinely ad-hoc judgment, encode it elsewhere and leave the operator out.
3. **You are managing a resource type, not one instance.** The pattern shines when platform teams expose a `Database` or `Certificate` CRD and dozens of teams create instances — the operator is the API implementation, and self-service replaces ticket-driven provisioning.
4. **Check for an existing operator first.** Postgres (CloudNativePG, Zalando), Redis, Kafka (Strimzi), cert-manager, External Secrets — writing a bespoke operator for a commodity database in 2026 is usually reinventing a maintained one; the decision is configuring and trusting an existing operator vs. authoring your own.
5. **Gauge the maintenance commitment honestly.** An operator is a long-lived distributed system with its own release cycle, RBAC surface, and bug queue; a team that cannot maintain a Go/Python service for years should keep their logic in an Ansible playbook or CI job instead.

## The Reconciliation Model

1. **Level-triggered, not edge-triggered.** The controller does not react to "the spec changed" events — it is handed the current full state and asks "does actual match desired?" on every pass; this makes behavior self-healing after crashes, restarts, and missed events, because the next reconcile simply re-derives what to do.
2. **The reconcile function must be idempotent.** It can be called every few seconds, concurrently for different objects, and re-run after a controller crash mid-action; each step must be safe to repeat and must tolerate the world already matching the spec (create-if-absent, patch-not-replace).
3. **One object key per worker, work queue everywhere.** controller-runtime (Go) and Kopf (Python) both deliver change notifications through a work queue that deduplicates and serializes per-object — never spawn background goroutines that mutate watched state outside the queue, or you break the model's ordering guarantees.
4. **Requeue explicitly.** Return `ctrl.Result{RequeueAfter: 30s}` for time-based polling (cert renewal checks, backup schedules) and return errors with backoff for transient failures; a reconcile that neither requeues nor errors will never run again for that object until something changes.
5. **Status is observed state, written last.** Report conditions, observed generation, and counts in `.status` after acting, and enable the status subresource so status writes never trip spec-change watches — a controller that feeds its own spec back into its inputs is the classic infinite-reconcile-loop generator.

## CRD Design

1. **Structural schemas with tight types.** Use OpenAPI v3 structural schemas (kubebuilder markers in Go), enums and ranges where the domain allows, and CEL validation rules for cross-field checks — invalid objects should be rejected by the API server at admission, not discovered inside the operator at runtime.
2. **Design the spec like an API you cannot easily change.** Fields gain deprecation cycles once anyone depends on them; version early (`v1alpha1`), keep a conversion webhook path in mind for `v1` transitions, and prefer fewer, declarative fields over imperative verbs (`replicas: 5`, never `action: scale-up`).
3. **Use finalizers for external cleanup.** When the operator manages things outside the cluster (DNS records, cloud load balancers, licenses), add a finalizer, clean up while `deletionTimestamp` is set, then remove it — without this, deleting the CR orphans external resources forever.
4. **Set sane limits and defaults in the CRD.** `x-kubernetes-validations` can cap replicas or require TLS fields, giving users guardrails that hold even when they edit YAML by hand and skip your UI/webhook entirely.
5. **Document the status contract.** Consumers (humans, GitOps, other controllers) will branch on your Conditions; publish which condition types exist, what `True/False/Unknown` mean, and keep `observedGeneration` accurate so staleness is detectable.

## Building and Shipping

1. **Kubebuilder / Operator SDK for Go is the default path.** It scaffolds API types, controllers, CRDs, RBAC manifests, webhooks, and e2e tests around controller-runtime; the generated layout is what every reviewer, tool, and AI assistant already understands.
2. **Kopf for Python teams.** Kopf exposes `@kopf.on.create/-update/-resume` handlers with built-in diff tracking and finalizer management — a pragmatic choice when the operational logic is glue around Python SDKs, at the cost of a per-object handler model rather than an explicit reconcile function.
3. **Run the operator as a normal workload with its own limits.** Set CPU/memory requests on the operator pod so heavy reconcile bursts do not starve neighbors, and enable leader election when running multiple replicas — without election, two operator copies will fight over the same objects.
4. **Scope RBAC to the exact resources.** The operator needs watch/list on its CRD plus the specific managed resources (Deployments, Secrets) — not `cluster-admin`; audit the generated `role.yaml` the same way you audit any other privileged deployment.
5. **Test against envtest and real clusters.** controller-runtime's envtest runs a real API server with your CRDs for fast unit-ish tests, but behaviors like eviction, upgrade ordering, and webhook timing only surface on actual nodes — a kind cluster or e2e suite in CI is the minimum bar before anyone's production depends on the operator.

## Pitfalls

1. **Infinite reconcile loops.** Writing a field on every pass (a timestamp, a default the user then removes), or comparing spec to status with a value that never converges, produces reconcile-every-second forever; watch event counts and add "no-op detection" — return early when observed generation is current.
2. **Long-running work inside Reconcile.** A reconcile that takes minutes (large restores, downloads) blocks the work queue; kick off a Job and return, then poll the Job's status in later reconciles — the pattern is "start step, observe step," never "do everything inline."
3. **Trusting in-cluster state as the whole world.** The API server's view can lag reality (a Deployment says ready, the pod just crashed); operators that act on stale cache snapshots need requeues and readiness re-checks before destructive actions like failover.
4. **Silent operator death.** If the operator pod is down, CRs silently stop converging and drift accumulates unnoticed; alert on controller runtime errors, queue depth, and `observedGeneration` staleness across CRs — the operator is itself a service you monitor.
5. **Scope creep into a platform.** Operators are seductive and accrete features until the team maintains an undocumented PaaS; keep each operator's CRD surface minimal, version its contract publicly, and push anything generic back into standard Kubernetes primitives.
