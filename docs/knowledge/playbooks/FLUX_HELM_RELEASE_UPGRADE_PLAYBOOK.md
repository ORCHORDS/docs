# Flux Helm Release Upgrade Playbook

## Purpose

Define the operational procedure for upgrading a HelmRelease managed by Flux CD. The procedure covers chart version bumps and values updates, with safe rollback if analysis fails.

## Audience

Platform engineers, SREs, and GitOps operators.

## Pre-conditions

- Flux CD 2.3+ (per `FLUX_VERSION_GOVERNANCE.md`).
- The cluster has Helm Controller installed.
- The HelmRelease is reconciled by Flux.

## Procedure

### Step 1 — Detect

1. Confirm the current chart version: `flux get hr <name> -n <namespace>`.
2. Confirm a new chart version is available.

### Step 2 — Author the change

3. Edit the `HelmRelease` manifest in Git:
   - `spec.chart.spec.version`.
   - `spec.values`.
4. Commit the change.
5. Open a PR for review.

### Step 3 — Reconcile

6. Merge the PR.
7. Trigger reconciliation:
   - `flux reconcile helmrelease <name> -n <namespace>`.
   - Or wait for the reconcile interval (default 1m).

### Step 4 — Validate

8. `flux get hr <name> -n <namespace>` to confirm the new revision.
9. `flux logs` to inspect controller logs.
10. Confirm Helm test passes if defined.

### Step 5 — Verify

11. Confirm pods are Ready.
12. Confirm services are reachable.
13. Confirm metrics are at baseline.

### Step 6 — Rollback

14. If the new chart breaks behavior, revert the PR.
15. Reconcile again: `flux reconcile helmrelease <name>`.
16. Confirm the previous revision is rolled back.

### Step 7 — Cleanup

17. Remove the failed chart version from the Helm repository cache (optional).

## Rollback

If Helm upgrade fails midway:

1. `flux suspend helmrelease <name>` to pause reconciliation.
2. Manually roll back via `helm rollback`.
3. `flux resume helmrelease <name>` to resume.
4. Reconcile.

## References

- `FLUX_VERSION_GOVERNANCE.md`
- Flux Helm Controller: `https://fluxcd.io/flux/components/helm/`
- HelmRelease spec: `https://fluxcd.io/flux/components/helm/helmreleases/`
