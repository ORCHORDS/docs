# kubernetes-cni-selection

**Issue:** The CNI (Container Network Interface) plugin is decided once at cluster creation and is nearly impossible to change later without rebuilding the cluster — yet it silently determines pod-to-pod throughput, whether NetworkPolicy is enforced at all, wire-level encryption options, IP address management across thousands of pods, and how debuggable the network is. Teams pick whatever the getting-started tutorial used, then discover at scale that policy enforcement is absent or the dataplane collapses under iptables rule counts. This article covers how the choice actually maps to requirements, the 2025-2026 state of the main contenders, and the migration realities.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What the CNI Actually Decides

1. **Pod connectivity and overlay choice.** The CNI implements the Kubernetes network model (every pod can reach every pod); whether that happens via VXLAN overlay, native routing, or BGP peering with the physical network is a CNI decision with direct latency, MTU, and troubleshooting consequences.
2. **NetworkPolicy enforcement.** The NetworkPolicy API is mandatory in Kubernetes, but enforcement is the CNI's job — clusters running a CNI without policy support (stock flannel) silently accept `NetworkPolicy` objects and enforce nothing, which is a standing security audit finding.
3. **IP address management (IPAM).** How pod CIDRs are allocated across nodes (per-node blocks, host-local, cluster-wide pools) interacts with VPC subnet sizing, node autoscaling limits, and dual-stack — running out of pod IPs presents as mysterious pending pods, not a clear error.
4. **The dataplane technology.** Traditional Linux CNIs lean on iptables rules that grow linearly with pods-times-policies and get slow past tens of thousands of rules; eBPF-based dataplanes (Cilium, Calico's eBPF mode) replace per-packet rule chains with kernel programs and hold up dramatically better in policy-heavy clusters — benchmarks through 2025-2026 consistently show eBPF CNIs outperforming iptables-based ones by 20-40% under heavy policy loads.
5. **Observability and debugging surface.** Some CNIs ship tooling (Cilium's Hubble flows, Calico's flow logs) that answers "why is pod A blocked from pod B" in one command; with others the answer is tcpdump and prayer — the cost of that difference shows up in every network incident.

## The Main Contenders in 2025-2026

1. **Cilium — eBPF-native, feature-maximal.** eBPF dataplane with L7-aware network policies (HTTP/gRPC-aware rules), Hubble flow observability, built-in WireGuard or IPsec encryption, and Gateway API ingress integration; it has become the pragmatic default for new serious clusters and is the backing for several managed offerings. Cost: more moving parts, an eBPF learning curve, and a kernel-version floor.
2. **Calico — the enterprise policy engine.** Multiple dataplane options (iptables, VXLAN, native BGP routing to the physical fabric, optional eBPF mode), mature large-scale deployments, and strong policy tooling; its BGP peering makes it the natural fit where the network team wants pods routed, not overlaid. Cost: the flexibility means a real design decision about which mode you are running and documenting it.
3. **flannel — simple overlay, nothing more.** One of the simplest CNIs, default in k3s and many tutorials: basic VXLAN pod connectivity, but zero native NetworkPolicy support — usable when paired with Calico policy ("Canal"-style combinations), but as a sole choice it is only defensible for lab/edge clusters with no isolation requirements.
4. **Cloud-managed CNIs.** AWS VPC CNI (pods consume VPC IPs), Azure CNI, GKE Dataplane V2 (Cilium-based) — these trade dataplane generality for VPC-native networking and managed lifecycle; they remove an operational burden but impose cloud-specific IPAM constraints (ENI limits, subnet sizing) that bite at scale.
5. **Multus for multi-interface edge cases.** Not a competitor but an attachment layer allowing pods multiple network interfaces (SR-IOV, DPDK, separate data/management networks) in telco/industrial clusters; it composes with an underlying primary CNI and adds real complexity — adopt only when the workload genuinely needs a second interface.

## Selection Criteria

1. **Start from policy requirements, not benchmarks.** If your security model depends on default-deny namespaces and L7 rules, the field narrows to Cilium or Calico immediately; throughput differences between those two matter far less than whether enforcement exists at all.
2. **Check kernel support for eBPF modes.** eBPF dataplanes want reasonably modern kernels (and BTF/CO-RE support for portability across kernel versions); on old distro kernels or unusual virtualization you may be pushed to iptables modes — verify on the actual node images before committing.
3. **Plan IPAM against real address space.** Count nodes x pods-per-node against the CIDR you can give the cluster, including dual-stack and autoscaler ceilings; per-node /24 blocks waste addresses but route cleanly, while cluster-wide pools conserve them — pick deliberately with the network team.
4. **Match the overlay decision to the physical network.** Native routing or BGP (Calico, some Cilium configs) integrates pods into the datacenter fabric with the lowest latency but requires fabric cooperation; VXLAN works everywhere at an MTU and slight performance cost — the right answer is whichever the network owners will actually support.
5. **Weight operational tooling honestly.** A CNI with built-in flow visibility turns "pod can't reach database" from a two-hour cross-team incident into a one-command answer; for teams without dedicated network engineers, Cilium+Hubble or Calico's tooling often beats a technically faster but opaque dataplane.

## Migration and Day-2

1. **Treat CNI choice as one-way.** There is no supported in-place path between major CNIs; the practical "migration" is a new cluster built with the target CNI and workloads drained over — so this decision deserves more upfront rigor than almost any other cluster setting.
2. **Canary the dataplane under real policy load.** Before committing, run a staging cluster with your actual NetworkPolicy corpus (not a demo set) and measure pod churn throughput, conntrack pressure, and CPU spent on networking — iptables-mode pain appears exactly here, in rule-count scaling, not in idle benchmarks.
3. **Version the CNI like critical infrastructure.** CNI upgrades can restart pod networking or change behavior subtly; pin versions explicitly, read release notes before cluster upgrades, and never let the k8s version and CNI version drift far apart on managed clusters.
4. **Monitor the CNI's own health.** Alert on pod-not-ready events with CNI-plugin errors in events/logs, IPAM pool exhaustion, and (for eBPF CNIs) program load failures; the CNI failing is a whole-cluster outage and should page like one.
5. **Keep policy testable.** With policy enforcement real (Cilium/Calico), add CI tests that assert a default-deny namespace actually blocks traffic — the most expensive CNI failure mode is the silent one where enforcement worked until a config regression quietly stopped matching traffic.

## Pitfalls

1. **flannel with ignored NetworkPolicies.** Teams write policies, kubectl accepts them, nothing is enforced — discovered during a security review or an incident; if simplicity forced flannel, document loudly that isolation must come from elsewhere (namespace RBAC, separate clusters).
2. **MTU mismatches under overlay.** VXLAN adds ~50 bytes of overhead; on networks with 1500 MTU and no path-discovery this yields silent large-packet failure (small pings work, TLS handshakes with big certificates hang) — set the CNI's MTU explicitly from the underlying network's value.
3. **Conntrack table exhaustion.** High service-connection churn with iptables-mode CNIs can exhaust the node conntrack table, dropping connections at random; raise limits and monitor `conntrack_count`/`conntrack_max`, or move the policy-heavy clusters to an eBPF dataplane.
4. **Dual-stack surprises.** Not every CNI feature parity exists for IPv6 (policies, some encryption modes); if dual-stack matters (see the ipv6-dual-stack article), verify the specific CNI version's support matrix rather than assuming.
5. **eBPF mode treated as a checkbox upgrade.** Flipping Calico to its eBPF mode or enabling extra Cilium features changes kube-proxy responsibilities, load balancing behavior, and failure modes mid-cluster — stage it like a platform migration on a canary node pool, not a config toggle.
