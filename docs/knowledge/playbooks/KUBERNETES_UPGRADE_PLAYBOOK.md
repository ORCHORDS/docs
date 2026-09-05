# Kubernetes Cluster Minor Upgrade Playbook

## Purpose

Upgrade a Kubernetes cluster from one minor version to the next (e.g., 1.33 → 1.34) with zero unplanned downtime. The playbook covers control-plane upgrade, node-by-node upgrade, deprecated API audit, and rollback.

## Audience

Platform engineers, SRE on-call, application owners, cluster operators.

## Pre-conditions

1. The reference cards are current: `KUBERNETES_VERSION_GOVERNANCE.md`, `CNCF_CKS_KUBERNETES_GOVERNANCE.md`.
2. The target version is within the supported matrix (≤ N+1 from current).
3. A staging cluster mirrors production topology.
4. Cluster backup is current (etcd snapshot, Velero).
5. Application owners have signed off on the upgrade.
6. The change ticket is open with the upgrade window.

## Procedure

### 1. Pre-flight

1. Read release notes for the target minor.
2. Audit deprecated APIs:
   ```bash
   kubectl api-resources --verbs=list -o name | \
     xargs -I{} kubectl get {} -A -o yaml 2>/dev/null | \
     grep -E "kind:|apiVersion:" | sort -u
   ```
3. Use `pluto` (FairwindsOps) or `kubectl deprecations` to identify deprecated APIs.
4. Confirm CNI, CSI, Ingress versions support the target minor.
5. Confirm kubelet skew: kubelet ≤ control plane minor + 2.
6. Validate the staging upgrade passes.

### 2. Control plane upgrade

1. Upgrade the first control plane node:
   ```bash
   kubeadm upgrade plan
   kubeadm upgrade apply v1.34.x
   ```
2. Restart kubelet.
3. Drain the node: `kubectl drain <node> --ignore-daemonsets --delete-emptydir-data`.
4. Repeat for each control plane node.
5. Validate the cluster: `kubectl get nodes`, `kubectl get pods -A`.

### 3. Node upgrade (one at a time)

1. Drain the node: `kubectl drain <node> --ignore-daemonsets --delete-emptydir-data`.
2. Upgrade the kubelet: install the new kubelet + kubectl binaries.
3. Restart kubelet.
4. Upgrade the container runtime if needed.
5. Uncordon the node: `kubectl uncordon <node>`.
6. Validate: `kubectl get pods -A -o wide | grep <node>`.
7. Repeat for each worker node.

### 4. Validation

- API server: `kubectl get nodes` returns all nodes Ready.
- Workloads: `kubectl get pods -A` returns all pods Running.
- Networking: `kubectl exec ... curl <service>` validates ingress.
- Storage: `kubectl get pvc` validates PVCs bound.
- Cluster DNS: `kubectl run ... nslookup kubernetes.default`.

### 5. Rollback

Rollback decisions:

- Cluster upgrade fails on first control plane node → revert binary; restore from etcd snapshot.
- Workloads fail to schedule → investigate the API change; revert the cluster.

Rollback procedure:

1. Revert the kubeadm upgrade on each control plane node.
2. Restore etcd from snapshot (per `ETCD_DR_PLAYBOOK.md`).
3. Restart kubelet on each node.
4. Validate the cluster.

## Mandatory pre-flight

1. Reference card is current.
2. Target version is supported.
3. Deprecated APIs are migrated.
4. Backup is current.
5. Application owners sign off.
6. Staging upgrade passes.

## Mandatory post-flight

1. New kubelet binaries are deployed cluster-wide.
2. New kubectl binaries are deployed.
3. CSI / CNI are updated.
4. Documentation is updated.
5. Backup continues on the new version.

## References

- `KUBERNETES_VERSION_GOVERNANCE.md`
- `CNCF_CKS_KUBERNETES_GOVERNANCE.md`
- `ETCD_DR_PLAYBOOK.md`
- Kubernetes upgrade: `https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/`
- API deprecation: `https://kubernetes.io/docs/reference/using-api/deprecation-guide/`
- Pluto (deprecated API finder): `https://github.com/FairwindsOps/pluto`
