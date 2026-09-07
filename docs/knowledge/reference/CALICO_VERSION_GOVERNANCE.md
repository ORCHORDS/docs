---
title: Calico Networking and Network Policy Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Tigera Calico (projectcalico/calico); CNCF Calico; Calico documentation at docs.tigera.io
---

# Calico Networking and Network Policy Version Governance

## 1. Purpose

This card governs how `orchords-docs` evaluates Calico across versions, dataplane modes (eBPF / Linux / Windows), BGP and BGP-IPAM patterns, and policy semantics. It is the reference input for any KB card that cites Kubernetes networking, network policy, or pod-to-pod encryption.

## 2. Scope

In scope:

- Calico v3.28+ (apiVersion `projectcalico.org/v3`, `crd.projectcalico.org/v1`).
- Dataplane: eBPF (recommended on kernels ≥ 5.10 with BTF), Linux (iptables/nftables), Windows HNS.
- Encapsulation: IPIP, VXLAN, none (BGP routed fabric).
- BGP: full-mesh, route reflectors, add-path.
- Policy tiers: `default`, `kube-system`, namespace, GlobalNetworkPolicy, NetworkPolicy (k8s).

Out of scope:

- Cilium (see `CILIUM_VERSION_GOVERNANCE.md`).
- Service-mesh authorization (see `ISTIO_VERSION_GOVERNANCE.md`, `LINKERD_VERSION_GOVERNANCE.md`).
- Subnet IPAM for bare-metal IPv6 fabric (call out to BGP-only deployments).

## 3. Versioning policy

- Pin to a specific minor (e.g. `v3.28.0`) and verify digest against the published Tigera operator images.
- Support the current minor and the previous minor (N-1); security backports only on N-1.
- The `tigera-operator` chart owns lifecycle; do not mix manifests from the legacy `calico.yaml` install after v3.22.
- Upgrade window: ≤ 60 days after a new minor; 14 days for security releases.
- Dataplane migration (Linux → eBPF or vice versa) requires a documented change ticket and an audit window.

## 4. Compatibility matrix

| Calico | Released | Status | K8s tested | Notes |
|---|---|---|---|---|
| 3.30.x | August 2026 | current | 1.31 – 1.34 | eBPF-only Windows HNS preview; nftables default |
| 3.29.x | May 2026 | N-1 | 1.30 – 1.33 | stable; nftables opt-in |
| 3.28.x | February 2026 | N-2 | 1.29 – 1.32 | legacy; no backports |
| 3.27.x | November 2025 | EoL | 1.28 – 1.31 | EoL |

References: `https://github.com/projectcalico/calico/releases`, `https://docs.tigera.io/calico/latest/getting-started/`.

## 5. Dataplane selection

- Default to the eBPF dataplane on kernels ≥ 5.10 with BTF; expect reduced CPU on CNI-heavy workloads and faster policy enforcement.
- Fall back to the Linux dataplane (nftables on new installs, iptables legacy only when explicitly required by a downstream CNI chain) when eBPF is unsupported (older kernels, restricted eBPF).
- Use the Windows HNS dataplane only on Windows nodes; never run eBPF on Windows.

## 6. BGP and IPAM

- For clusters > 50 nodes, use route reflectors (BGP) or BGP-IPAM, not full-mesh iBGP.
- Pin ASNs and cluster IDs explicitly; do not rely on the operator's defaults.
- For dual-stack, enable `IPv4IPIP` or `VXLANMode: Always` only when cross-pod routing requires encapsulation; otherwise `none` (BGP routed) is preferred.
- Honor `BGPExporters`/`BGPPeer` semantics when integrating with external L3 fabrics.

## 7. Policy tiers

- Place platform policies in the `kube-system` tier; tenant policies in the `default` tier; security overlays in a higher-priority tier.
- Use `GlobalNetworkPolicy` for cluster-wide enforcement and `NetworkPolicy` (k8s) for namespace-scoped rules.
- Apply `doNotTrack` and `preDNAT` only when DNAT rewriting is documented (e.g., for ingress gateway chains).
- Test policies with `calicoctl get` and `calicoctl apply --dry-run` before `apply`.

## 8. Upgrade procedure

1. Read release notes; identify FelixConf, KubeControllersConf, BGP changes.
2. Apply the operator upgrade to staging with `--dry-run --debug`.
3. Run `calicoctl node status` and `calicoctl ipam check` against staging.
4. Validate BGP session state with `calicoctl node bgp peer show`.
5. Roll production one cluster at a time; keep prior `BGPConfiguration` for one cycle.

## 9. Rollback procedure

1. `helm rollback tigera-operator` to the prior chart revision.
2. Confirm `kubectl get felixconfiguration -o yaml | grep dataplane` matches the prior dataplane.
3. Validate BGP sessions return to `Established`; watch for `Idle`/`Active` flaps.
4. If a CRD upgrade was applied, run `calicoctl upgrade` to restore the prior `ClusterInformation`.
5. Document the rollback cause in the change ticket.

## 10. Observability

Required metrics:

- `felix_active_local_endpoints` (gauge per node).
- `felix_int_dataplane_failures_total{type}` (counter).
- `calico_bgp_session_state{peer}` (gauge: 1 = Established).
- `calico_policysync_latency_seconds` (histogram).

One alert:

- `CalicoBGPFlapping` — page when `changes(calico_bgp_session_state[5m]) > 4` sustained 10 minutes; also page on `rate(felix_int_dataplane_failures_total[5m]) > 0.1` for 5 minutes.

References: `https://docs.tigera.io/calico/latest/operations/metrics/`, `https://github.com/projectcalico/calico/blob/master/README.md`.

## 11. References

- Calico docs: `https://docs.tigera.io/calico/latest/`
- Calico repo: `https://github.com/projectcalico/calico`
- Releases: `https://github.com/projectcalico/calico/releases`
- Calicoctl: `https://docs.tigera.io/calico/latest/reference/calicoctl/`
- BGP design: `https://docs.tigera.io/calico/latest/networking/configuring/bgp/`
- Policy tiers: `https://docs.tigera.io/calico/latest/network-policy/`
- CNCF Calico: `https://www.cncf.io/projects/calico/`
