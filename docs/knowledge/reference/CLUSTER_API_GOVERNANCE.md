---
title: Kubernetes Cluster API (CAPI) Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://cluster-api.sigs.k8s.io ; https://github.com/kubernetes-sigs/cluster-api
---

# Kubernetes Cluster API (CAPI) Version Governance

## 1. Purpose

This reference card governs the lifecycle of Kubernetes Cluster API (CAPI) when used to declaratively provision, upgrade, and tear down Kubernetes clusters across cloud, on-prem, and edge providers. It applies to platform engineering teams that manage fleet-level cluster lifecycle operations.

## 2. Scope

In scope:

- CAPI core controller ≥ v1.7.x (`cluster.x-k8s.io/v1beta1`).
- Providers: AWS, Azure, GCP, vSphere, OpenStack, Tinkerbell, Metal³, Kamaji, Docker (dev only).
- Bootstrap providers: kubeadm, Tink.
- Add-on providers (CAPZ/CAPX/CAPI/CAPA) and ClusterResourceSet.
- ClusterClass for templated cluster topology.

Out of scope:

- Legacy CAPI v1alpha3 / v1alpha4 deployments — must be migrated to v1beta1.
- Custom infrastructure providers outside the upstream list.

## 3. Versioning policy

- Pin the CAPI controller and every provider to the same minor version (e.g. `v1.7.4`).
- The cluster's Kubernetes version must be supported by the CAPI version: see the upstream provider compatibility matrix.
- Keep **management** cluster on a Kubernetes version ≥ 1.28 when running CAPI v1.7.x.
- Use ClusterClass for any cluster that will be templated multiple times; do not duplicate raw `Cluster` resources.

## 4. Compatibility matrix

| CAPI | Kubernetes (management) | AWS provider | Notes |
| --- | --- | --- | --- |
| v1.6.x | 1.27+ | v2.4.x | ClusterClass GA in AWS |
| v1.7.x | 1.28+ | v2.5.x | MachinePools GA in CAPA |
| v1.8.x | 1.30+ | v2.6.x | Managed topologies GA |

## 5. Cluster lifecycle

- `Cluster.spec.topology` references a `ClusterClass`; per-cluster overrides only for allowed paths.
- `MachineDeployment` enables rolling upgrades via `strategy.rollingUpdate.maxSurge` and `maxUnavailable`.
- Use `MachineHealthCheck` with `nodeStartupTimeout` and `unhealthyConditions` to trigger auto-remediation.

## 6. Upgrade procedure

1. Bump `spec.topology.version` in the ClusterClass template (control plane and worker).
2. Apply with `clusterctl upgrade plan` and `clusterctl upgrade apply` (or in CI).
3. Watch `capi_cluster_info{type="control_plane",ready}` for parity with the previous version.
4. Validate workloads via the platform SLO dashboard before promoting the next step.

## 7. Rollback procedure

- CAPI rollbacks are version-aware: revert the `spec.topology.version` in the ClusterClass and reapply; control plane nodes roll forward, not backward, so a true rollback requires a separate version bump.
- For MachineDeployment changes, `kubectl apply` the previous MachineDeployment manifest; CAPI reconciles back to the previous state.

## 8. Observability

- Required metrics: `capi_cluster_info{name,namespace}`, `capi_machine_info{owner,phase}`, `capi_machine_deployment_replicas_updated`, `capi_cluster_resource_set_applied_resources_total`.
- Alert on `capi_cluster_info{ready="false"} == 1` (cluster not ready) and on `capi_machine_deployment_replicas_unavailable` > 1 for sustained periods.

## 9. References

- CAPI documentation — https://cluster-api.sigs.k8s.io
- `clusterctl` CLI reference — https://cluster-api.sigs.k8s.io/clusterctl/overview.html
- Provider compatibility matrix — https://cluster-api.sigs.k8s.io/provider-compatibility
