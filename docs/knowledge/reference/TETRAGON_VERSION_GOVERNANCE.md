---
title: Cilium Tetragon Runtime Enforcement Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: Cilium Tetragon project (https://github.com/cilium/tetragon), CNCF Sandbox; Tetragon 1.0 (March 2024), 1.1 (June 2024), 1.2 (October 2024), 1.3 (March 2025), 1.4 (August 2025), 1.5 (March 2026), 1.6 (August 2026); TracingPolicy CRD; kernel BTF and CO-RE; complements FALCO_VERSION_GOVERNANCE.md for detection-vs-enforcement
---

# Cilium Tetragon Runtime Enforcement Version Governance

## Scope

This card governs how `orchords-docs` evaluates Cilium Tetragon as a Kubernetes-aware runtime enforcement layer. Tetragon is the eBPF-based enforcement engine that complements Falco-style detection: it captures kernel events with the same eBPF probe used by Cilium and applies TracingPolicies that can kill a process, block a syscall, or override a file path **at the kernel layer**, not after the fact. A KB card that cites Tetragon without binding to TracingPolicy CRD version, kernel BTF availability, and Cilium operator compatibility produces an installation whose enforcement rules silently fail to apply.

## Why this card exists

Tetragon is part of the Cilium family and is governed by the same release cadence as Cilium itself (see `CILIUM_VERSION_GOVERNANCE.md`). Where Falco is read-only detection with sidecar output, Tetragon is in-kernel enforcement. Many production clusters run both: Falco detects and forwards to a SIEM; Tetragon blocks the offending syscall. Version drift between Tetragon and Cilium breaks the kernel probe ABI; version drift between Tetragon and the TracingPolicy CRD silently disables new policy fields.

## Version support matrix (2026-09)

| Tetragon | Released | EoL | Notes |
|---|---|---|---|
| 1.3.x | March 2025 | ~6 months after next minor | stable, TracingPolicy v1 |
| 1.4.x | August 2025 | ~6 months after next minor | stable, kprobe and tracepoint filters |
| 1.5.x | March 2026 | ~6 months after next minor | stable, kernel 6.x coverage |
| 1.6.x | August 2026 | current | stable, exclusive enforcement preview |

Policy:

- Tetragon minor must be within ±1 minor of the running Cilium (`CILIUM_VERSION_GOVERNANCE.md`).
- TracingPolicy CRD `apiVersion` MUST be pinned to the Tetragon minor that introduces the fields used.
- Upgrade window: ≤ 3 months after a new Tetragon minor release.

## Kernel and BTF requirements

- Production: kernel ≥ 5.8 with BTF (`/sys/kernel/btf/vmlinux` present).
- AArch64 production: kernel ≥ 5.10 with BTF; TracingPolicy `kprobe` and `tracepoint` filters must be validated on the target CPU before enforcement.
- Avoid BTF-less kernels; the legacy kprobe path does not enforce `TracingPolicy.spec.kprobe.selector` with kernel version constraints.

## TracingPolicy governance

- All `TracingPolicy` and `TracingPolicyNamespaced` resources MUST be reviewed against the Tetragon minor that ships the fields used.
- `kprobe.selector.matchArgs`, `tracepoint.selector.matchNamespaces`, and `signalfault.signo` are forward-only fields — backporting requires the corresponding Tetragon image.
- `enforcementAction` is the single most load-bearing field; review every value other than `SIGKILL`, `SIGTERM`, `OVERRIDE`, and `NONE`.
- Layered enforcement: lower-numbered policies take precedence; ship a single owner per enforcement action per workload.

## Compatibility notes

- Tetragon reuses the Cilium BPF map and probe; co-deployment with Cilium CNI is the supported path.
- Hubble integration (`TETRAGON_HUBBLE_INTEGRATION`) requires Hubble ≥ the release that ships with the same Cilium minor.
- Avoid running multiple Tetragon daemonsets against the same node — the eBPF program map is single-tenant.

References: `https://github.com/cilium/tetragon`, `https://docs.cilium.io/en/latest/security/policy/index.html`, `https://github.com/cilium/tetragon/tree/main/Documentation`, `https://www.cncf.io/projects/tetragon/`.
