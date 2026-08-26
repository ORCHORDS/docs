# eBPF-Based Observability — Kernel-Level Tracing Without Instrumentation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Kubernetes cluster has 200 microservices but only 40% have
OpenTelemetry SDKs instrumented. The uninstrumented services are a
black box — you cannot trace requests through them, identify which
syscalls are slow, or detect anomalous network connections. Adding
SDK instrumentation to all services requires code changes across 12
teams and 6 programming languages, with an estimated 3-month rollout.
Meanwhile, a latency regression in an uninstrumented Go service is
affecting production, and you have no visibility into what the process
is doing at the kernel level.

## Context

eBPF (extended Berkeley Packet Filter) is a Linux kernel technology
that allows sandboxed programs to run inside the kernel without
modifying kernel source or loading kernel modules. In 2026, eBPF has
become the foundation for a generation of observability and security
tools, replacing user-space agents with kernel-level instrumentation
that provides deep visibility into networking, syscalls, and process
execution with typically less than 2-5% CPU overhead. The key
ecosystem projects are Cilium/Hubble (networking + flow observability),
Tetragon (security observability + runtime enforcement), Pixie/Beyla
(automatic distributed tracing), and bpftrace (ad-hoc tracing).

## bpftrace one-liners

```bash
# Syscall count by process
sudo bpftrace -e 'tracepoint:raw_syscalls:sys_enter {
  @[comm] = count();
}'

# Trace files opened by process
sudo bpftrace -e 'tracepoint:syscalls:sys_enter_openat {
  printf("%d %s %s\n", pid, comm, str(args->filename));
}'

# Read size distribution by process
sudo bpftrace -e 'tracepoint:syscalls:sys_exit_read /args->ret > 0/ {
  @[comm] = hist(args->ret);
}'

# TCP connection latency histogram
sudo bpftrace -e 'kprobe:tcp_v4_connect {
  @start[tid] = nsecs;
}
kretprobe:tcp_v4_connect /@start[tid]/ {
  @us = hist((nsecs - @start[tid]) / 1000);
  delete(@start[tid]);
}'

# DNS lookup latency
sudo bpftrace -e 'uprobe:/lib/x86_64-linux-gnu/libc.so.6:getaddrinfo {
  @start[tid] = nsecs;
}
uretprobe:/lib/x86_64-linux-gnu/libc.so.6:getaddrinfo /@start[tid]/ {
  @ms = hist((nsecs - @start[tid]) / 1000000);
  delete(@start[tid]);
}'
```

## Cilium + Hubble (Kubernetes networking)

```bash
# Install Cilium with Hubble
cilium install --version 1.16
cilium hubble enable --ui

# Observe network flows
hubble observe --namespace default --protocol TCP
hubble observe --verdict DROPPED    # see denied traffic
hubble observe --to-label app=api   # traffic to specific service

# Export to Prometheus for dashboards
# Hubble metrics are exposed at :9965/metrics by default
```

## Observability stack architecture

```
Kernel-level data sources:
  Cilium/Hubble    → Network flows, DNS, L7 protocol visibility
  Tetragon         → Security events, process exec, file access
  Beyla            → Auto-instrumented HTTP/gRPC/SQL traces

Data pipeline:
  eBPF programs → Ring buffer → User-space collector
    → OpenTelemetry Collector → Backends

Backends:
  Metrics:  Prometheus / Grafana Mimir
  Traces:   Grafana Tempo / Jaeger
  Logs:     Grafana Loki / Elasticsearch
  Flows:    Hubble UI / Grafana
```

## Kernel requirements

```
Minimum:      Linux 5.10 LTS (basic eBPF support)
Recommended:  Linux 6.1+ (CO-RE support, BTF by default)
Tetragon:     Linux 5.15+ (LSM BPF hooks)

CO-RE (Compile Once, Run Everywhere):
  Without CO-RE: eBPF programs must be recompiled per kernel version
  With CO-RE:    Programs compiled once, BTF provides struct offsets
  Check:         ls /sys/kernel/btf/vmlinux  (exists = BTF available)
```

## Anti-patterns

- **Uprobes on hot paths** — user-space probes require a context
  switch per event, causing up to 200% overhead compared to kernel
  probes. Use kprobes or tracepoints instead where possible. Reserve
  uprobes for cold paths or debugging sessions.
- **kprobes instead of tracepoints** — kprobes attach to arbitrary
  kernel functions but are unstable across kernel versions. Always
  prefer tracepoints (stable ABI) for production monitoring.
  Tracepoints survive kernel upgrades; kprobes may silently stop
  working.
- **Over-instrumenting** — every probe has per-event cost. Attaching
  to high-frequency hooks (per-packet XDP, high-rate kprobes)
  without filtering generates excessive data and measurable CPU
  overhead. Always filter at the eBPF level, not in user space.
- **Expecting application-level context** — eBPF sees syscalls,
  sockets, and probed library calls but cannot read in-process
  variables, business logic, or domain context. Custom spans and
  business attributes still require SDK instrumentation.

## Gotchas

- **Kernel structure volatility** — field offsets and names change
  between kernel versions. Without CO-RE (kernel 6.x+ with BTF),
  eBPF programs must be recompiled per kernel version, which is a
  major deployment and maintenance burden.
- **Incomplete syscall coverage** — overlooking syscall variants
  (e.g., `openat2` vs `openat` vs `open`) creates blind spots in
  observability and security. Audit the full syscall family for each
  operation you trace.
- **Privileged access required** — loading eBPF programs requires
  `CAP_BPF` (Linux 5.8+) or root. In Kubernetes, this means
  privileged DaemonSets or specific capability grants, which has
  security implications.
- **Map memory limits** — eBPF maps (hash tables, arrays) have
  configurable but finite memory. High-cardinality keys (per-PID
  tracking on busy systems) can exhaust map space, causing silent
  data loss.

## Verification

- eBPF programs load successfully on target kernel version.
- CO-RE compatibility is confirmed (BTF available on all nodes).
- CPU overhead of probes stays below 5% under production load.
- Tracepoints are used instead of kprobes for production monitoring.
- Hubble flows are exported to the central observability platform.
- Beyla auto-tracing covers uninstrumented services.

## Related

- `documentation/docs/policies/monitoring/opentelemetry-collector-pipeline-configuration.md`
- `documentation/docs/policies/monitoring/distributed-tracing-opentelemetry-patterns.md`
- `documentation/docs/policies/monitoring/synthetic-monitoring-uptime-probes.md`

## Source URLs (verified 2026-08-16)

- eBPF in 2026: From Kernel Observability to Application Security — https://devstarsj.github.io/2026/03/09/ebpf-2026-observability-security-networking/
- Building a Production eBPF Observability & Security Stack for Kubernetes in 2026 — https://dev.to/x4nent/building-a-production-ebpf-observability-security-stack-for-kubernetes-in-2026-5051
- Hardening eBPF for Runtime Security: Lessons from Datadog — https://www.datadoghq.com/blog/engineering/ebpf-workload-protection-lessons/
- Tetragon — eBPF-based Security Observability and Runtime Enforcement — https://tetragon.io/
