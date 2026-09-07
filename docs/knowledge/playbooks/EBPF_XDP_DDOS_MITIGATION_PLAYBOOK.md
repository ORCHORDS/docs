# eBPF XDP DDoS Mitigation Playbook

## Purpose

Provide a controlled procedure for attaching an eBPF XDP program to a node's primary NIC to absorb volumetric L3/L4 DDoS attacks at the earliest possible point in the network stack, without dropping legitimate traffic.

## Audience

Network engineers, SRE on-call, security incident responders.

## Pre-conditions

- Linux kernel ≥ 5.10 LTS on the target node with `/sys/kernel/btf/vmlinux` populated.
- libbpf ≥ 1.4 and `clang` ≥ 14 installed in the XDP build container.
- An XDP-capable NIC (Intel i40e, ice, mlx5, or virtio with native XDP support) on every node in the protected pool.
- Allow-list of legitimate source prefixes (`bgp_allowlist`) maintained in version control.
- Sign-off from the network team that the chosen XDP mode (driver, SKB, or offload) matches the NIC and driver.

## Procedure

1. **Canary**: deploy the XDP program to a single node via the platform's `xdp-daemon` DaemonSet. Mode: `driver` (native) preferred, fall back to `skb`.
2. **Whitelist**: load the allow-list of /32 and /24 prefixes into a `BPF_MAP_TYPE_LPM_TRIE`. Updates apply atomically via `bpf_map_update_elem` from a sidecar.
3. **Counters**: emit `xdp_packets_total{action=passed,dropped,tx,redirect}` to Prometheus. Establish a 1-minute baseline before traffic peaks.
4. **Soft drop**: switch on rate-limited drops for traffic exceeding a threshold (e.g. 100 kpps per source /24). Observe `xdp_exception_count` and `xdp_packets_total{action="dropped"}`.
5. **Hard drop**: enable full drops for prefix denials; emit an alert to the network channel when sustained drops exceed the budget.
6. **Scale**: extend the DaemonSet to all nodes in the protected pool. Confirm no `bpf_jit_failures_total` spikes.
7. **Decommission**: when upstream DDoS scrubbing returns to nominal, switch the program back to pass-through but keep the BPF object loaded for instant re-engagement.

## Rollback

- Detach the XDP program with `ip link set dev <iface> xdp off` (driver mode) or `ip link set dev <iface> xdpdrv off`. The kernel removes the program atomically; no service impact if detached during a maintenance window.
- Restore the previous DaemonSet version; verify with `bpftool prog show` that the program is unloaded.

## References

- Cloudflare XDP architecture — https://blog.cloudflare.com/xdp-ddos-mitigation/
- Cilium XDP documentation — https://docs.cilium.io/en/latest/network/servicemesh/
- Internal: Batch 98 reference card `EBPF_XDP_TC_GOVERNANCE.md`.
