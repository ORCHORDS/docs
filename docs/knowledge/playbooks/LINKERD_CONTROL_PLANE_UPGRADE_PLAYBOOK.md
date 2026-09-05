# Linkerd Control Plane Upgrade Playbook

## Purpose

Upgrade a Linkerd control plane while preserving service connectivity, identity, observability, and a clear rollback path.

## Audience

Platform engineers and SREs.

## Pre-conditions

- The current and target versions are reviewed under `LINKERD_VERSION_GOVERNANCE.md`.
- Kubernetes compatibility is confirmed.
- Cluster access and a recent configuration backup are available.
- Trust-anchor expiry and issuer health are known.

## Procedure

### Step 1 — Inventory

1. Record the current Linkerd project and artifact versions.
2. Record the proxy version used by meshed workloads.
3. Record installed extensions and multicluster dependencies.
4. Capture current health and service-level indicators.

### Step 2 — Pre-check

5. Run the Linkerd health checks.
6. Run the documented pre-upgrade checks for the target release.
7. Resolve warnings that indicate incompatibility or identity problems.
8. Review release notes for changed defaults or deprecated behavior.

### Step 3 — Upgrade the control plane

9. Generate the target control-plane manifests using the supported Linkerd upgrade flow.
10. Review the manifest diff before applying it.
11. Apply the control-plane change.
12. Wait for control-plane components to become Ready.

### Step 4 — Verify

13. Re-run Linkerd health checks.
14. Verify identity issuance and proxy-to-proxy mTLS.
15. Verify metrics and installed extensions.
16. Confirm representative meshed services can communicate.

### Step 5 — Roll the data plane

17. Restart or redeploy workloads in controlled slices when a proxy-image update is required.
18. Observe error rate, latency, and proxy health between slices.
19. Continue only while service indicators remain within the approved range.

## Rollback

If control-plane health regresses:

1. Stop further data-plane rollout.
2. Restore the previously reviewed control-plane configuration or follow the project rollback guidance for the affected release.
3. Re-run health and identity checks.
4. Confirm application traffic has recovered before closing the incident.

## Sources

- Linkerd releases: `https://linkerd.io/releases/`
- Linkerd reference: `https://linkerd.io/docs/reference/`
- Linkerd CLI upgrade reference: `https://linkerd.io/docs/reference/cli/upgrade/`
