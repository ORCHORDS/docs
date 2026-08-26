# ebpf-infrastructure-observability

**Issue:** Infrastructure teams need answers that traditional agents cannot give: which process is burning CPU across 400 nodes without instrumenting code, what syscalls did that container make in the second before it was compromised, and which network flows are being dropped and why — all without paying per-event agent overhead. eBPF allows small, verified programs to run inside the Linux kernel on events (syscalls, network packets, kprobes), which has turned it into the 2025-2026 default substrate for continuous profiling, runtime security, and network observability. This article covers what eBPF actually is for an infra engineer, the production tool categories built on it, and the operational constraints that decide whether it fits your fleet.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Mental Model

1. **Kernel-event programs, not processes.** An eBPF program is a small sandboxed function attached to a hook — a syscall entry, a network interface, a tracepoint — that executes when the event fires; there is no polling loop and no per-event userspace wake-up, which is why the overhead can stay near zero when idle.
2. **The verifier is the safety story.** Before loading, the kernel's verifier proves the program terminates, cannot access out-of-bounds memory, and cannot crash the kernel — this is what makes it acceptable to run foreign code in kernel space on production nodes, and also why kernel-version differences can reject programs (missing features, changed function signatures).
3. **CO-RE and BTF make programs portable.** Compile Once – Run Everywhere uses BTF type information so a program built on one kernel can be relocated onto another's data structures; this is what lets vendors ship one agent binary that works across your mixed fleet, and its prerequisite (kernel BTF enabled) is a first-line compatibility check.
4. **Maps are the data channel.** eBPF programs write into kernel-side key-value "maps" (histograms, stacks, ring buffers) that userspace reads asynchronously — high-frequency events are aggregated in kernel and only summaries cross the boundary, which is the core of the low-overhead claim.
5. **One loader per host, then ecosystems.** Agents like Cilium, Tetragon, Falco, and Parca each load their own programs; there is no universal orchestrator, so fleets run several eBPF consumers side by side — the practical cost is not CPU, it is debugging which agent's program attached to which hook when something conflicts.

## Observability Uses

1. **Continuous profiling with zero instrumentation.** Parca Agent, Grafana Pyroscope, and (for auto-instrumented app telemetry) Beyla sample stack traces of every process on a node via eBPF and ship aggregated flame graphs — no code changes, no sidecars, ~1% CPU class overhead, turning "what is eating CPU in prod" into a query against always-on profiles instead of a one-off perf session.
2. **Network flow visibility.** Cilium's Hubble exposes L3/L4 (and with parsing, L7) flow records and policy-drop reasons directly from the eBPF dataplane — when a NetworkPolicy blocks pod A from pod B, Hubble names the rule, replacing packet-capture archaeology on production nodes.
3. **Generic tracing with bpftrace/BCC.** For ad-hoc investigation, bpftrace one-liners (`trace this syscall with its args, aggregate by process`) answer questions no pre-built agent anticipated; the skill is scarce, so keep a small library of vetted scripts rather than improvising under incident pressure.
4. **File/system event auditing.** eBPF file-open and exec auditors record which binary opened which file with which UID — far cheaper than auditd at scale, and the same mechanism feeds security tools (below) and compliance evidence (who read the secrets directory, when).
5. **Filling the OTel gap.** eBPF-derived metrics and profiles slot into existing OpenTelemetry pipelines as complementary signals — traces say where a request went, eBPF profiles and flows say what the machine was actually doing underneath, and the combination catches issues neither sees alone.

## Security Uses

1. **Runtime security enforcement with Tetragon.** Tetragon attaches eBPF sensors at syscall and kernel-function level for real-time policy — kill a process the instant it calls `ptrace` or opens a sensitive file, not five seconds later in a log pipeline; it is Kubernetes-aware, so policy can target pods by label and namespace.
2. **Detection with Falco and Tracee.** Falco pioneered eBPF-based rule detection (`a shell spawned inside a container`, `file under /etc modified`) with a mature rule ecosystem; Aqua's Tracee covers similar ground with a trace-first philosophy — both detect, while Tetragon's differentiator is inline enforcement.
3. **The 2025-2026 consolidation trend.** The ecosystem is converging on fewer, deeper tools — Cilium's own guidance now walks Falco users through migrating to Tetragon for enforcement, and teams increasingly run one eBPF security layer instead of stacking several agents whose sensors overlap.
4. **KubeArmor for policy-style hardening.** KubeArmor maps Kubernetes annotations/labels to enforcement of system-level constraints (which binaries a pod may exec, which files it may write), fitting teams that want auditable policy objects rather than inline rule code.
5. **Forensics that survive attacker cleanup.** Because events are captured in-kernel at the moment they happen and streamed out immediately, eBPF audit trails record process execution and file access even when the intruder deletes logs afterward — the sensor is not a file the attacker can truncate.

## Operational Constraints

1. **Kernel version is the gate.** Modern features want roughly 5.x+ kernels with BTF compiled in (`/sys/kernel/btf/vmlinux` present); verify across the whole fleet including the oldest node image and any appliances, because a single unsupported kernel fragments your coverage story.
2. **Overhead is per-tool, not per-technology.** "eBPF is free" is marketing; each loaded program costs something, and sensors that ship every event to userspace (rather than aggregating in kernel) can get expensive under load — benchmark the specific tool on your workload, not the brand.
3. **Signed/locked-down kernels can block loading.** Secure Boot with lockdown, or module-signing policies, may prevent unprivileged eBPF loads; on such fleets (and some managed kernels) you need the vendor's blessed loading path or explicit sign-off from the platform security team.
4. **Privilege requirements are real.** eBPF agents typically need `CAP_BPF`/`CAP_SYS_ADMIN` or a privileged DaemonSet — treat the agent as high-value infrastructure: pin its version, scope its RBAC, and audit it like the kernel-adjacent software it is.
5. **Debuggability is still expert-shaped.** `bpftool prog show`, verifier logs, and per-hook attach lists are your diagnostics when an agent misbehaves or two tools fight over a hook; document who on the team can run these before you depend on the tooling in an incident.

## Pitfalls

1. **Tool sprawl recreates the agent problem.** Installing Tetragon, Falco, Pixie, and a commercial APM's eBPF collector on the same nodes stacks sensors on the same hooks and multiplies upgrade risk; inventory what each existing agent already collects before adding another.
2. **Silent coverage gaps.** A node with an old kernel, missing BTF, or a blocked load quietly runs without the security monitoring you believe covers the fleet — monitor sensor presence per node (is the agent's program actually loaded?), not just agent pod health.
3. **Alert floods from default rules.** Runtime-security rule sets out of the box flag normal CI and build-container behavior (compilers exec'ing shells); tune to your baseline with a learning period, or the tool gets disabled within a month of the first page-storm.
4. **Profiling storage creep.** Always-on profiling across hundreds of nodes generates a steady profile stream; set retention and aggregation (and sample rates) consciously or the observability bill rivals the workload it watches.
5. **Treating enforcement as a toggle.** Moving from detect-only to inline kill policies changes failure modes — a too-broad Tetragon policy can sever legitimate traffic instantly; stage enforcement in audit mode with the same discipline as a firewall change, per namespace, with a rollback path.
