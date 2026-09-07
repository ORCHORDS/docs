---
title: eBPF for XDP and TC Kernel Hooks Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://www.kernel.org/doc/html/latest/networking/filter.html ; https://docs.cilium.io/en/latest/network/ ; https://www.brendangregg.com/ebpf.html
---

# eBPF for XDP and TC Kernel Hooks Version Governance

## 1. Purpose

This reference card defines the version-governance model for Linux extended Berkeley Packet Filter (eBPF) programs attached at the eXpress Data Path (XDP) and Traffic Control (TC) clsact/BPF hook points. It applies to platforms that load eBPF networking programs for ingress/egress packet processing, load balancing, denial-of-service mitigation, observability, and policy enforcement inside Kubernetes node kernels.

## 2. Scope

In scope:

- eBPF kernel image compatibility matrix (kernel ≥ 4.19 LTS baseline; ≥ 5.10 recommended; ≥ 6.6 LTS for BTF-signed-only flows).
- XDP driver (native), XDP offload (Netronome/NFP), and XDP generic/SKB modes.
- TC clsact ingress/egress programs using libbpf ≥ 1.4 with BTF type information.
- BPF CO-RE (Compile Once – Run Everywhere) relocations and BTF minimum-viable-set rules.
- Cilium, Calico eBPF data plane, and Tetragon as primary consumers.

Out of scope:

- Userspace eBPF runtimes (uBPF, bpftime) and the AArch64 JIT specifics beyond pointer-auth handling.
- Application-level socket filtering via SO_ATTACH_BPF outside of XDP/TC.

## 3. Versioning policy

- Pin the **libbpf** minor version per fleet (no floating `latest` in shipped OCI artefacts). Use libbpf ≥ 1.4.7 with `LIBBPF_STRICT_DIRECT_ASSIGN`, `LIBBPF_STRICT_HDR_FIND`, and `LIBBPF_MAP_KEEPER` default-on.
- Require kernel **BTF** (`/sys/kernel/btf/vmlinux`) on every node. Fail-closed on missing BTF for CO-RE programs.
- Reject kernels < 4.19 LTS from the orchestrator node-pool registration webhook.
- For XDP driver mode, require NIC drivers with AF_XDP zero-copy support or fallback to SKB mode automatically.
- TC programs must declare a `SEC("classifier/ingress")` or `SEC("classifier/egress")` section and supply a pin path under `/sys/fs/bpf/tc/<ifindex>/`.

## 4. Compatibility matrix

| Kernel | libbpf | BTF | XDP native | XDP SKB | TC clsact | CO-RE |
| --- | --- | --- | --- | --- | --- | --- |
| 4.19 LTS | 1.2.x | optional | partial | yes | yes | no (BTF reloc fallback) |
| 5.10 LTS | 1.3.x | required | yes | yes | yes | yes |
| 5.15 LTS | 1.4.x | required | yes | yes | yes | yes |
| 6.1 LTS | 1.5.x | required | yes | yes | yes | yes (kfuncs) |
| 6.6 LTS | 1.6.x | required | yes (multi-buf) | yes | yes | yes (sleepable kfuncs opt-in) |

## 5. Build, sign, and load

- Compile with `clang -target bpf -g -D__TARGET_ARCH_<arch>`. Use BTF via `-g` and embed the BTF for portable object files.
- Sign artefacts with Sigstore Cosign keyless (OIDC + Fulcio) using `--rekor=false=false --output-signature=/signatures/xdp.sig`. Bundle the public key with `cosign verify --key k8s://cosign-public`.
- Load via the Cilium/Tetragon operator; never invoke `ip` or `tc` from inside a pod spec.
- Pin maps under `/sys/fs/bpf/<program-id>/` and reference them by BPF FS path, not by id, across restarts.

## 6. Upgrade procedure

1. Build the new eBPF object under `bpf/<program>.bpf.o` and push to the in-cluster OCI registry.
2. Tag the node pool with the new DaemonSet version; drain one node at a time.
3. Verify kernel health with `bpftool prog show` and `bpftool map show` after pod startup.
4. Promote to 100 % after at least 24 h green metrics on canary nodes.

## 7. Rollback procedure

- Roll back by reverting the operator DaemonSet to the previous pinned image and reattaching old `.bpf.o` from the BPF FS snapshot.
- Detach via `tc filter delete dev <iface> ingress pref <handle>` and `ip link set dev <iface> xdp off` before relaunching the old DaemonSet to avoid lingering clsact filters.

## 8. Observability

- Emit Prometheus metrics from BPF programs via the BPF ring buffer (`BPF_MAP_TYPE_RINGBUF`) → userspace exporter.
- Required metrics: `xdp_packets_total{action=...}`, `tc_packets_total{hook=...,verdict=...}`, `bpf_jit_failures_total`.
- Alert on `rate(bpf_jit_failures_total[5m]) > 0` and on `xdp_exception_count > 0` for any driver.

## 9. References

- Cilium eBPF datapath documentation — https://docs.cilium.io/en/latest/network/
- libbpf release notes — https://github.com/libbpf/libbpf/releases
- BPF Design Q&A — https://docs.kernel.org/bpf/bpf_design_QA.html
