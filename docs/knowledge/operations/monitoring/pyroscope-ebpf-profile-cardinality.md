# Pyroscope eBPF Profile Cardinality Governance

Continuous profiling with eBPF agents (Grafana Alloy's eBPF profiling components, or the OpenTelemetry eBPF profiler feeding Pyroscope) captures stack traces system-wide with negligible per-sample application changes. The cost model is different from metrics: cardinality arrives through profile labels — service name, pod, container, and any custom dimensions attached to profile series — and through the sheer volume of samples an always-on profiler emits. Ungoverned, both dimensions turn a useful profiling deployment into a storage and query liability.

## Scope

Covers cardinality governance for eBPF-based continuous profiling into Pyroscope: where profile labels come from and which to keep, how profile types scope what is captured, sampling and scrape-interval overhead considerations for kernel-level agents, and the monitoring needed to keep profile series bounded. Targets operators running Alloy eBPF profiling or the OTel eBPF profiler against a Pyroscope server. Excludes SDK push-mode instrumentation (language-native profilers) except for contrast, and excludes Pyroscope cluster storage internals.

## Workflow or implementation guidance

Governance here is about keeping two budgets: a label budget and an overhead budget.

Label budget. eBPF agents attach labels to every profile series they ship. The defaults derive from what the kernel exposes per process — service name discovered from the workload, container or pod identifiers, namespace — and each additional custom label multiplies series count by its distinct value count. Start from the profile-types configuration: each profile type (CPU, allocations, contention, and so on, depending on agent) is a separate series family, and enabling every type for every workload is rarely justified. Enable the profile types each team will actually read, and let the others stay off until asked for. Then audit labels with the same test used for metrics: dimensions used to aggregate across workloads (cluster, namespace, service) are legitimate; per-instance or per-pod values are only worth their cost when an engineer will drill from aggregate to that exact pod -- and in profiling, the stack traces themselves provide the drill-down, so per-pod labels are usually redundant weight.

Label discipline matters more in profiling than in metrics because the payload behind each series is a full profile tree; series count multiplies already-heavy data. Prefer the smallest set: service name plus the minimal deployment identity. Pyroscope's aggregation in queries can combine series, but it cannot undo cardinality already ingested.

Overhead budget. eBPF profilers sample at a configurable rate; higher rates resolve shorter hot paths but raise kernel-to-userspace copy volume proportionally. Set the sampling rate per the questions being asked — a rate that characterizes steady-state CPU hot spots need not catch microsecond events. Where the agent supports a scrape or upload interval, batch uploads rather than streaming, so the Pyroscope server absorbs periodic loads rather than continuous ones. Measure the agent's own CPU and memory on representative nodes before fleet-wide rollout; eBPF overhead is low but not zero, and it is paid on every node, so fleet-wide cost is overhead times node count.

Rollout order: pilot on a canary pool covering each workload type, verify profile completeness (symbols resolved, kernel and user stacks both present) and overhead measurements, then expand with the label and profile-type policy already enforced in configuration. Keep the policy in the agent configuration (Alloy component configuration or the OTel eBPF profiler's settings), not in per-node ad hoc flags, so drift is impossible.

Monitoring. Watch profile ingestion rates and series counts per tenant in Pyroscope, alert on step changes (a new label or a churny pod-name label announces itself exactly this way), and track agent-side drop counters for upload backpressure.

## Controls

- Profile-type allow-list per workload class in agent configuration, with additions requiring a stated analysis need.
- Label allow-list enforced in the agent configuration; pod-unique and hash-suffixed identifiers relabeled away at source.
- Sampling rate and upload interval declared per node class with a documented rationale; changes re-measured on canary nodes.
- Ingestion monitoring: profiles per second, distinct series per tenant, and bytes, with alerts on step changes.
- Agent overhead check: CPU and memory of the agent process measured on canary nodes pre-rollout and spot-checked monthly.
- Quarterly review retiring profile types and labels nobody queried, using Pyroscope's usage data where available.

## Validation evidence

Three artifacts prove governance. A series-count report before and after a label removal, showing the expected multiplicative drop. A completeness check: a captured profile for a known CPU-bound test workload, showing expected functions resolved with symbols (not raw addresses), demonstrating the pipeline works end to end. An overhead measurement from the canary pool: agent CPU and memory under the declared sampling settings across a representative week, filed alongside the fleet-size arithmetic that projects total cost. For query-side health, the latency of a representative flame graph query before and after a cardinality reduction closes the set.

## Failure modes and correction

- Series count climbs after fleet growth: pod-name or container-ID labels slipped in with a node pool expansion. Relabel them away in agent configuration; the ingestion series-count alert should have caught it first.
- Flame graphs show unsymbolized frames: symbolization failed (missing debug info, stripped binaries). Fix deployment build flags to include symbols or configure symbolizer sources; cardinality governance is irrelevant if profiles are unreadable.
- Pyroscope server backpressure and agent drops: upload volume outgrew the server. Increase upload batching interval, lower the sampling rate, or scale the server; check whether a new profile type multiplied volume.
- Kernel-version-dependent failures on some nodes: eBPF programs require kernel features; nodes below the threshold ship nothing. Detect via the agent's own error metrics and either upgrade kernels or exclude those pools.
- Query timeouts on broad selectors: users querying across all series with wide time ranges. Encourage service-scoped selectors, and revisit whether per-pod labels are actually needed for the common queries.

## Limitations

eBPF profiler capabilities, supported profile types, and configuration keys differ across agent implementations (Alloy's eBPF components versus the OTel eBPF profiler) and versions; the deployed agent's documentation is authoritative. Kernel version floors apply and vary by feature. Overhead numbers are workload- and kernel-dependent, so figures here are directional and must be measured. Symbolization quality depends on build artifacts the profiling pipeline does not control. Pyroscope's own scaling behavior, storage formats, and any per-tenant limits evolve rapidly between releases, revalidating the numbers after upgrades.

## Canonical sources

- Grafana Alloy eBPF profiling configuration: https://grafana.com/docs/pyroscope/latest/configure-client/grafana-alloy/ebpf/
- Pyroscope profile types: https://grafana.com/docs/pyroscope/latest/configure-client/profile-types/
- OpenTelemetry eBPF profiler client configuration: https://grafana.com/docs/pyroscope/latest/configure-client/opentelemetry/ebpf-profiler/
