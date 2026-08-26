# helm-chart-design-patterns

**Issue:** Every team's first Helm chart grows by copy-paste until `templates/` contains forty files held together by `{{- if }}` chains, `values.yaml` has 300 keys nobody remembers, upgrades fail half-applied because hooks were used as a workflow engine, and nobody can reproduce last month's deployment because the chart repo tag was overwritten. This article covers chart design that survives production: small charts with strict values schemas, helpers instead of duplication, hooks for one-shot jobs only, and distribution as immutable OCI artifacts — which stopped being optional in 2025 when registries began deleting classic chart repos.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Chart Structure and Template Hygiene

1. **One chart per deployable unit, small by design.** A chart should model one application or one infrastructure component; a "platform chart" that deploys app + database + ingress + monitoring together couples their upgrade cycles and makes rollbacks of one piece impossible without rolling back everything.
2. **Put shared logic in `_helpers.tpl` named templates.** Labels, selector names, and the service account name belong in `define` blocks used via `include` — the classic bug is a Deployment selector and Service selector drifting apart because the label list was pasted in three places and edited in two.
3. **Extract cross-chart patterns into library charts.** A chart with `type: library` in `Chart.yaml` contributes templates but deploys nothing; consuming charts `include` its helpers, so "how we do probes/labels/podAnnotations" is defined once for the whole org instead of forked into 40 charts.
4. **Keep CRDs in the `crds/` directory.** Files there install before templates render and are never upgraded or deleted by Helm — the correct behavior for CRDs that would orphan running custom resources if mutated during `helm upgrade`.
5. **Render and lint in CI on every change.** `helm lint`, `helm template`, and (ideally) `helm unittest` cases in the chart's pipeline catch malformed YAML and bad conditionals before a release does; a chart that only fails at install time in prod is a chart without tests.

## Values Design

1. **Defaults must be safe and boring.** `values.yaml` should deploy a working, resource-requested, non-privileged workload with no real secrets; anything environment-specific (domains, replicas, instance classes) arrives via `-f values-prod.yaml` overrides, never by editing the defaults.
2. **Enforce a `values.schema.json`.** A JSON Schema on the values file turns "typo'd `replicaCount` silently ignored" into a hard validation error at `helm install` time — cheap insurance that pays for itself the first time a key is renamed and half the overrides files are missed.
3. **Stay shallow and predictable.** Two or three levels of nesting maximum; deeply nested trees (`metrics.sidecar.extraEnv[0].valueFrom`) make override files unreadable and diff reviews useless.
4. **No secrets in values, ever.** Values files live in git and ship inside the chart package; use External Secrets, Sealed Secrets, or SOPS so the chart only references a secret name, keeping `helm get values` safe to paste into a ticket.
5. **Treat non-default values as code.** Per-environment override files are reviewed in PRs with the same rigor as application code, because a one-character change to a prod override file is a full production change.

## Distribution: OCI Is the Only Answer Now

1. **Publish charts as OCI artifacts.** `helm push ./mychart-1.4.2.tgz oci://registry.example.com/charts` stores the chart in any OCI registry (GHCR, ACR, ECR, Harbor, Docker Hub) with registry-native auth, RBAC, and replication — this is Helm's documented recommended path, not an exotic alternative.
2. **The classic repo format is being actively retired.** Azure Container Registry deleted chart-repo (non-OCI) charts on 2025-03-30 and retired its legacy Helm repository support on 2025-09-15; any 2026 design that still points `repo:` at an HTTP index.yaml is building on a deprecating substrate.
3. **OCI artifacts are immutable — exploit that.** Pushing version 1.4.2 twice to an OCI registry fails instead of silently overwriting, which kills the "someone re-pushed the tag" class of unreproducible deployment.
4. **Pin by digest in the supply chain.** Argo CD / Flux / CI pipelines should reference charts by version at minimum, and by `@sha256:` digest for the highest bar; combine with cosign signing and `--verify` so the deploy pipeline cryptographically checks chart provenance.
5. **One registry namespace per trust boundary.** `charts/team-a/` vs `charts/team-b/` with separate write permissions keeps a compromised CI credential in one team from poisoning charts fleet-wide.

## Hooks, Tests, and Upgrade Safety

1. **Hooks are for one-shot jobs only.** `pre-install`/`pre-upgrade` Jobs for schema migrations or secret generation is the legitimate use; anything long-running in a hook is invisible to `helm upgrade` lifecycle and blocks releases when it wedges.
2. **Set hook deletion policies deliberately.** `helm.sh/hook-delete-policy: hook-succeeded` keeps succeeded Jobs from accumulating, but before-hook-of-same-name deletion is what stops five stale migration Jobs from racing a rollback.
3. **Never use `helm.sh/hook-weight` as a workflow engine.** Weights order hooks within a release, not build a pipeline; if you need app-depends-on-db semantics, that is an application readiness concern (initContainers, readiness probes), not a chart concern.
4. **Template the `helm test` Pod.** A `helm.sh/hook: test` Pod hitting the service's health endpoint gives every consumer a one-command smoke check after install — the cheapest possible guard against "chart installs green but the app is broken."
5. **Design upgrades to be idempotent and reversible.** Avoid `kubectl`-in-`post-install` side scripts; anything the chart does through side effects will not be undone by `helm rollback`, so state created outside of Kubernetes resources must be handled by an operator or explicitly documented break-glass runbook.

## Pitfalls

1. **Namespace-by-namespace values sprawl.** Ten near-identical `values-*.yaml` files diverging by one key each means the difference is invisible in review; factor shared config into a base file and keep per-env files to the actual deltas.
2. **Chart version discipline collapses under pressure.** Bump `version` on every template change even when `appVersion` is unchanged — CD systems diff chart versions, and a re-pushed same-version chart with different content is exactly the drift OCI immutability exists to prevent.
3. **`latest` app images in defaults.** A default image tag of `latest` makes the same chart+values deploy different code tomorrow; pin the default `appVersion` image digest and let CD control upgrades explicitly.
4. **Labels without the standard keys.** Charts should emit `app.kubernetes.io/name`, `app.kubernetes.io/instance`, `app.kubernetes.io/version`, and `helm.sh/chart` so dashboards, network policies, and cost tools can aggregate without per-chart custom label knowledge.
5. **Treating `helm upgrade --install` as atomic.** A failed upgrade leaves partial state; always run with `--wait --timeout` and a tested `helm rollback` path, and prefer GitOps-driven upgrades (Argo CD/Flux) so the git commit — not a laptop — is the source of truth for what should be deployed.
