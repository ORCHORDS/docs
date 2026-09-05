# GitOps Sync Failure Recovery Playbook

## Purpose

Define the operational procedure for recovering from a GitOps controller (Argo CD / Flux CD) that has fallen out of sync, when the drift is between the desired state in Git and the actual cluster state. The procedure ensures that recovery is automated where possible and that manual overrides are auditable.

## Audience

Platform engineers, SREs, and on-call responders.

## Pre-conditions

- The cluster is managed by Argo CD 2.4+ or Flux CD 2.0+ (per `GITOPS_VERSION_GOVERNANCE.md`).
- The cluster is reconciled by at least one `Application` (Argo) or `Kustomization` / `HelmRelease` (Flux).
- The cluster has logging to a centralized system.

## Procedure

### Step 1 — Detect

1. Argo CD: `argocd app list -o yaml | jq '.[] | select(.status.health.status=="Degraded")'`.
2. Flux CD: `flux get kustomizations --all-namespaces | grep False`.
3. Confirm drift: `argocd app diff <app>` or `flux diff kustomization <name>`.

### Step 2 — Diagnose

4. Identify the sync status reason (`OutOfSync`, `Degraded`, `Unknown`).
5. Inspect controller logs.
6. Determine root cause:
   - Failed health check.
   - Failed pre-sync hook.
   - Invalid manifest (CRD mismatch).
   - Quota or rbac.
   - Network partition from Git server.

### Step 3 — Recover automatically

7. If the controller can auto-sync, force a sync:
   - Argo CD: `argocd app sync <app> --prune --force`.
   - Flux: `flux reconcile kustomization <name> --with-source`.
8. If the auto-sync succeeds, verify health.

### Step 4 — Recover manually

9. If auto-sync fails, manually reapply the desired state from Git:
   - `kubectl apply -k <path-to-kustomize-output>` (Flux).
   - `argocd app sync <app> --replace` (Argo).
10. Document every manual apply as a `SyncOverride` annotation on the Application / Kustomization.

### Step 5 — Address root cause

11. If the failure was caused by an invalid manifest, revert the Git commit (revert PR, do not force-push).
12. If the failure was caused by a CRD mismatch, update the CRD first, then the manifests.
13. If the failure was caused by a network partition, restore network access and retry sync.

### Step 6 — Verify

14. Confirm `OutOfSync` status is `Synced`.
15. Confirm `health.status` is `Healthy`.
16. Confirm all replicas are Ready.

### Step 7 — Postmortem

17. File a postmortem per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.
18. Identify the drift origin (manifest change, controller bug, network).
19. Add a regression test or guard rail.

## Rollback

If recovery introduces regressions:

1. Revert the Git commit.
2. Force a sync.
3. Verify health.

## References

- `GITOPS_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- Argo CD: `https://argo-cd.readthedocs.io/en/stable/operator-manual/sync-options/`
- Flux: `https://fluxcd.io/flux/cmd/flux_reconcile/`
