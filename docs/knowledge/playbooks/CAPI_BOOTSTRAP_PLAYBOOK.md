# Cluster API Bootstrap Playbook

## Purpose

Provision a new management cluster and prepare it to host CAPI controllers plus the desired set of infrastructure providers, so that downstream cluster lifecycle work can be expressed declaratively.

## Audience

Platform engineers, SRE on-call, security engineers reviewing IAM grants.

## Pre-conditions

- A target Kubernetes cluster (v1.28+ for CAPI v1.7.x) with at least 4 vCPU, 16 GB RAM, and 100 GB storage.
- IAM credentials for the chosen infrastructure provider (AWS / Azure / GCP / vSphere) with permissions sufficient for the provider's `iam.json` policy.
- `clusterctl` CLI installed locally and on the CI runners.
- Out-of-band communication channel between the management cluster and the workload cluster's network.

## Procedure

1. **Initialize the management cluster**: `clusterctl init --infrastructure aws --control-plane aws --bootstrap kubeadm --bootstrap-token-ttl 60m`. Confirm `clusterctl init` returns `✓ Initialized` and verify pods in `capi-system`, `capi-kubeadm-control-plane-system`, `capa-system`.
2. **Apply IAM credentials**: `clusterctl init` prints the IAM JSON URL; create the IAM role per provider docs and secret:
   `kubectl create secret generic capa-manager-bootstrap-credentials --from-file=credentials=~/.aws/credentials -n capa-system`.
3. **Validate with a smoke cluster**: produce a tiny `Cluster` resource (1 control plane, 1 worker, no add-ons) and `kubectl apply -f cluster.yaml`. Watch `capi_cluster_info{phase="Provisioned"} == 1`.
4. **Test kubeadm bootstrap**: confirm the control plane comes up healthy and that the cluster API endpoint is reachable from the management cluster.
5. **Add ClusterClass**: convert the smoke `Cluster` into a `ClusterClass` for templated use, with `controlPlane.ref.apiVersion: controlplane.cluster.x-k8s.io/v1beta1`.
6. **Day-2 tooling**: install ClusterResourceSet and add at minimum the platform `metrics-server` and `argocd-agent`.
7. **Document**: register the new management cluster in `platform/inventory/clusters.md` with cluster name, region, and provider.

## Rollback

- `clusterctl delete --all` removes all child clusters created via CAPI; the management cluster remains.
- `clusterctl reset --force` removes the CAPI controllers from the management cluster (use only when decommissioning).
- For a stuck child cluster, `kubectl delete cluster` triggers controller cleanup; the provider's console may still hold orphaned resources — purge via `cluster-api-aws-controller-list` for AWS.

## References

- CAPI getting started — https://cluster-api.sigs.k8s.io/user/quick-start.html
- `clusterctl init` reference — https://cluster-api.sigs.k8s.io/clusterctl/commands/init.html
- Internal: Batch 101 reference card `CLUSTER_API_GOVERNANCE.md`.
