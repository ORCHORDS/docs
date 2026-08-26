# gitops-pull-vs-push-deployment-models

**Issue:** example project's CI pipeline deployed straight to the cluster with `kubectl apply` from a GitHub Actions runner. When a runner's kubeconfig leaked into a fork-PR context, and again when an on-call engineer hand-patched a Deployment at 2am that the next CI run silently overwrote, it became clear the team had never made an explicit choice between push-based and pull-based deployment. The repo now has both Argo CD and `kubectl apply` steps mutating the same namespace, and nobody can say which system is the source of truth for what is running in production.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Two Models Defined

1. **Push-based deployment.** An external system (CI runner, laptop, Jenkins job) holds cluster credentials and actively applies changes — `kubectl apply`, Helm upgrade, `wrangler deploy`, `terraform apply`. Deployment happens as an event at pipeline time; between runs, nothing watches the cluster.
2. **Pull-based deployment (GitOps).** An in-cluster controller (Argo CD, Flux) continuously fetches the declared state from Git and reconciles the live cluster toward it. Deployment is not an event but a standing convergence loop.
3. **The litmus test.** If you delete a production Deployment and nothing puts it back within minutes, you are push-based no matter what your README claims. Pull-based systems restore it automatically on the next reconciliation pass.
4. **Both are legitimate — for different layers.** Push fits ephemeral, external resources (DNS records, CDN config, serverless platforms without an in-platform reconciler). Pull fits long-lived in-cluster workloads where drift correction is wanted.

## Security and Credential Posture

1. **Push exports secrets to every pipeline.** Every CI job that can deploy needs a kubeconfig or cloud credentials, multiplying the places credentials can leak — runner caches, fork PRs, third-party actions. The 2023 tj-actions/changed-files compromise demonstrated how a single action can exfiltrate injected credentials across thousands of repos.
2. **Pull keeps credentials inside the boundary.** Argo CD and Flux authenticate outward to Git (read-only) from inside the cluster; no cluster credentials ever leave it. CI only needs write access to Git, which is already scoped and auditable.
3. **Prefer deploy tokens over PATs either way.** If CI must push (to a registry or to Git), use short-lived OIDC-federated tokens rather than long-lived personal tokens — see `oidc-federated-deploy-credentials.md` in this directory.
4. **Pull does not eliminate trust decisions.** Whoever can merge to the deploy branch can change production; branch protection and required reviews become your real change-control layer, not the pipeline.

## Reconciliation and Drift Behavior

1. **Push has no drift correction.** Manual edits, `kubectl scale` during an incident, and web-console changes persist until the next pipeline run happens to touch the same resource — which may be never.
2. **Pull converges continuously.** The controller diffs live state against Git on a poll/webhook interval (Argo CD defaults to ~3 min polling; webhooks make it near-instant) and reverts out-of-band changes on the next sync.
3. **Self-heal must be an explicit, reviewed choice.** Argo CD's `selfHeal: true` reverts manual patches automatically — exactly what you want for workload manifests, and exactly what you do not want in the middle of an incident where an operator scaled replicas to survive traffic. Decide per-application and document it.
4. **Reconciliation cadence is a tunable, not a constant.** Flux exposes per-resource reconciliation intervals; treat overly aggressive intervals on large clusters as a control-plane load problem.

## Failure Modes of Each Model

1. **Push: the "worked last run" fallacy.** Green CI says the apply succeeded once, not that the cluster still matches it. State between runs is unverified by construction.
2. **Pull: silent resurfacing of old manifests.** A controller faithfully re-applying a stale branch can roll production back if someone force-pushes or points the app at the wrong ref. Pin applications to immutable commit SHAs or protected branches, not floating tags.
3. **Pull: reconciliation lag is real.** A Git merge is "deployed" only after the controller syncs it. Gate downstream steps (smoke tests, purge hooks) on observed sync health, not on the merge itself — see `merged-is-not-deployed-bundle-verification.md`.
4. **Hybrid collisions.** Running `kubectl apply` against resources an Argo CD Application owns produces fighting writes: the manual change wins briefly, then reconciliation reverts it, and the diff flaps. Pick one writer per resource, enforced by RBAC.

## Choosing and Migrating

1. **Default rule.** Long-lived Kubernetes workloads: pull. Serverless edge platforms (Workers, Lambda) and external SaaS state: push from CI, because there is no in-cluster reconciler to pull.
2. **Hybrid pattern that works.** CI builds and pushes immutable image tags, then commits a manifest update (or opens a PR via the app-of-apps repo). The pull controller does the actual deploy. CI never talks to the cluster.
3. **Migration path.** Start with one non-critical namespace under Argo CD or Flux, run it read-only (diff-only, no auto-sync) for two weeks to see what would change, then enable sync once the drift report is clean.
4. **Keep the audit story unified.** Whichever model runs production, the answer to "what is running and who changed it" must come from Git history plus controller logs — not from anyone's memory of the last `kubectl` command they ran.
