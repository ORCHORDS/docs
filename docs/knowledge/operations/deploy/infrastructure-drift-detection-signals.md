# infrastructure-drift-detection-signals

**Issue:** example project declares its infrastructure in Terraform and its workloads in Git, but production has quietly diverged from both: a console-made security-group change from six months ago, a `kubectl scale` that survived an incident and never got codified, and a load balancer modified by a support engineer during a vendor call. Nobody noticed because the only drift check is a `terraform plan` that runs when someone remembers to run it. This article covers building drift detection as a continuous signal across layers — complementing, not replacing, the Terraform-specific CI workflow already documented in `terraform-drift-detection.md`.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Drift Is and Where It Hides

1. **Drift is the gap between declared state and live state.** Declared state lives in Terraform, Helm values, manifests, and pipeline configs; live state is what the cloud and cluster actually are. Any unrecorded divergence is drift, whether caused by humans, consoles, APIs, or vendor tooling.
2. **Layer 1: cloud resources.** Security groups, IAM policies, DNS records, database flags — modified via console, CLI, or support tickets; detected by comparing live resources against Terraform state.
3. **Layer 2: Kubernetes workloads.** Replica counts, image tags, env vars — modified by `kubectl edit/scale/patch` during incidents or debugging; detected by diffing live objects against the manifests a GitOps controller would apply.
4. **Layer 3: config sprinkled between.** CDN rules, queue subscriptions, feature-flag targeting rules, and cron schedules changed in admin UIs — the layer no IaC covers at all, where drift lives longest because nothing is even theoretically comparing it.
5. **Unmanaged drift compounds.** A drifted resource blocks the next clean apply, engineers start working around Terraform errors with more manual changes, and within a quarter the IaC is fiction — drift is self-accelerating neglect.

## Drift Signals by Detection Mechanism

1. **Scheduled `terraform plan` with `--detailed-exitcode`.** Exit code 0 = clean, 2 = drift present; run on a cron in CI against every workspace. This is the baseline mechanism (full workflow in `terraform-drift-detection.md`).
2. **GitOps controller diff as a live signal.** Argo CD continuously compares live cluster state to the Git target — its "OutOfSync" status is a real-time drift report that needs no cron; Flux exposes the same via its Kustomization readiness conditions. Where Terraform detects drift only when a plan runs, the in-cluster reconciler sees it within one poll interval.
3. **Cloud audit logs as the earliest trigger.** Every console/CLI mutation lands in CloudTrail / GCP Audit Logs / Azure Activity Log within minutes. Alerting on write events against resource types you manage in IaC catches the drift the moment it is created — with the actor's identity attached — rather than at the next plan.
4. **Reconciliation metrics from controllers.** Argo CD and Flux export Prometheus metrics for sync health and applied-out-of-band changes; a `argocd_app_info{sync_status="OutOfSync"}` alert is drift detection as monitoring, chartable next to deploy markers.
5. **Diff-based review for the uncovered layer.** For admin-UI config with no IaC, export the config on a schedule (many SaaS tools support config export/API) and commit the diff — a poor man's state file that at least makes invisible drift reviewable.

## Continuous vs Periodic Detection

1. **Periodic (cron plan) catches drift eventually.** A daily plan finds yesterday's console change today — acceptable for slow-changing layers like network config, too slow for anything incident-adjacent.
2. **Continuous (reconciler/audit-log) catches drift as it happens.** Audit-log alerts and controller sync status notice the change within minutes, including who made it; this is the difference between "fix a state mismatch" and "have a conversation with a teammate."
3. **Match frequency to change rate.** Cloud audit-log alerts (minutes) for managed resource types; hourly-to-daily terraform plans per workspace; controller-native continuous reconciliation for cluster workloads. Daily-or-less for anything is a smell unless the layer genuinely never changes.
4. **Detection without ownership routing decays.** Every drift alert must route to the owning team (tag workspaces/resources with an owner label), or it becomes notification spam that everyone swipes away within two weeks.

## Triage: Revert, Import, or Codify

1. **Revert when the change is harmful or accidental.** Terraform apply the declared state (or let the reconciler resync) to restore desired config; the console change dies and the audit entry explains why.
2. **Import when the change is good but unmanaged.** The manual change was correct — bring it into state (`terraform import`) and then write the matching HCL so the next plan is clean; the import without the code just hides the drift from view.
3. **Codify when the change reveals missing capability.** If on-call keeps hand-scaling because IaC has no knob for it, the drift is a feature request: add the variable, module support, or a proper autoscaling policy so the legitimate need stops producing illegitimate drift.
4. **Always pick one of the three, never "leave it."** Every open drift item older than a sprint is a decision to let declared state rot; track unresolved drift as a count with a target of zero-stale, not zero-total.

## Alerting, Metrics, and Anti-Patterns

1. **Alert on drift age, not drift existence.** Some drift is legitimate (an incident patch awaiting merge-back); the alert-worthy signal is drift that persists past your merge-back SLA — alert on `age > 48h`, page nobody at minute one.
2. **Chart drift count next to deploy frequency.** Rising drift on a flat deploy cadence means out-of-band changes are winning; this belongs on the same dashboard as change-failure-rate (see `change-failure-rate.md`) because drift-heavy estates have worse deploy outcomes.
3. **Anti-pattern: auto-revert with humans in the loop absent.** Self-heal on workload manifests is standard; auto-applying terraform against changes an operator made deliberately during an active incident will escalate the incident. Pair automation with the incident-process rule that hotfixes merge back within 24h (see `hotfix-branching-deployment-discipline.md`).
4. **Anti-pattern: drift detection as blame detection.** If the audit-log alert reads like an accusation, operators pre-emptively disable it and drift goes dark; frame alerts as "state mismatch, needs triage" with the actor as context, not as the subject.
5. **Anti-pattern: monitoring the wrong truth.** If Terraform state itself is stale (forgotten refresh, dangling resources), the plan says "clean" while reality differs — schedule refresh/prune and periodically verify a sample of live resources directly against declared values rather than trusting state as ground truth.
