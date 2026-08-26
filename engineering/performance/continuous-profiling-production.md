# continuous-profiling-production

**Issue:** Performance problems are investigated only after users complain, using ad-hoc profiler sessions against a local build that does not match production binaries, traffic, or data volumes. By the time someone attaches a debugger, the slow window has passed and the flamegraph shows idle time instead of the regression. This article defines a continuous profiling methodology: always-on, low-overhead sampling profilers running in production, with profiles correlated to deployments and latency SLOs so regressions are found from permanent telemetry rather than guesswork.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Concepts

1. **Continuous vs on-demand profiling.** Continuous profilers sample CPU, memory allocation, mutex contention, and wall-clock profiles from every instance all the time and ship them to a central store, so the profile covering the incident at 03:00 exists even if nobody was watching. On-demand profiling (attaching to a process when it is already slow) misses the cause and perturbs the system being measured.
2. **Sampling over instrumentation.** Production-safe profilers sample stacks at a fixed frequency (typically 100 Hz for CPU) rather than instrumenting every function call, keeping overhead near 1-2% CPU. The statistical aggregate over minutes is as actionable as a full trace, without the latency tax.
3. **eBPF-based stack collection.** eBPF profilers in the kernel can unwind stacks across languages without code changes or sidecar agents, which is why they became the default collection mechanism for heterogeneous fleets by 2025. Trade-off: kernel frame pointers may be missing in some builds, causing partial stacks for JIT-compiled frames (Go, JVM, V8).
4. **Profile types beyond CPU.** A complete setup captures heap allocation profiles (who allocates, useful for GC pressure), goroutine/thread contention, off-CPU / wall-clock profiles (what blocked while waiting on I/O or locks), and memory leak differentials. CPU-only profiling finds hot loops but is blind to lock convoys and blocking I/O.
5. **Time-series correlation.** Profiles are only useful when they can be sliced by service, instance, pod, and time window matching a latency or error-rate anomaly. Pyroscope and Parca both tag profiles with labels like Prometheus metrics, letting you diff "slow pod A now" against "fast pod B now" or "this service before vs after deploy".

## Tooling Landscape

1. **Grafana Pyroscope.** The most common choice when Grafana is already the observability stack; it integrates with Prometheus exemplars and can jump from a Prometheus metric spike directly to the matching profile window. Supports multi-tenancy and ingests profiles from many languages plus eBPF agents, and is available as Grafana Cloud's Profiles drilldown.
2. **Parca.** Fully open-source alternative with the strongest eBPF heritage and clean Prometheus-style integration; a good fit for teams avoiding vendor-hosted components. It shares the Pull/Push profile protobuf format (now a CNCF effort, pprof-derived) with Pyroscope, so migration cost is low.
3. **Language-native agents.** pprof (Go), async-profiler (JVM), py-spy / austin (Python), and eBPF via bpftrace cover single-service deep dives when a fleet-wide platform is overkill. The common interchange format means a one-off py-spy capture can still be loaded into the central UI for comparison.
4. **Cloud-integrated profilers.** Cloud Profiler (GCP), CodeGuru Profiler's successors, and Datadog Continuous Profiler bundle profiling with APM traces, which shortens the path from "slow trace" to "flamegraph of that request window". Prefer these when the APM vendor is already paid for; watch retention and per-host pricing at fleet scale.
5. **OpenTelemetry profiles signal.** The OTel semantic conventions for profiles reached practical maturity in 2025, letting one collector pipeline carry traces, metrics, logs, and profiles. Adopting it avoids a second ingestion network and keeps profile labels consistent with the rest of the telemetry.

## Methodology

1. **Deploy profiling to every instance, not a sample.** Tail latency and rare allocations live on the 1% of instances doing unusual work; sampling instances means sampling away exactly the signal you want. Agent overhead below ~2% CPU is the accepted cost of always-on coverage.
2. **Establish a baseline per service per deploy.** Compare the profile of the current release against the previous release over an equal traffic window before attributing anything to "the database". Diffing two flamegraphs side by side turns "it feels slower" into "this function appeared and takes 300 ms of every request".
3. **Read flamegraphs wide, not tall.** Wide frames (frequent samples) are the optimization targets; a tall narrow spike is usually a one-off. Look for frames that grew between deploys, library code called from your hot path, and allocation profiles where a small source line dominates bytes allocated.
4. **Correlate with deployment markers and SLO burn.** Overlay deploy events on profile timelines so a regression is attributed to the right commit within minutes; link p99 burn-rate alerts to the profile window so the on-call engineer opens a flamegraph, not a dashboard of averages.
5. **Keep profiles queryable for the incident window.** Retain raw profiles for at least 14-30 days so a weekly incident review can still pull the exact window. Aggregated single "profile of the week" snapshots lose the ability to isolate the bad 10 minutes.

## Gotchas and Anti-Patterns

1. **Overhead denial.** Teams enable every profile type at max sample rates and then see latency regressions from the profiler itself; cap CPU sampling near 100 Hz and disable off-CPU profiling where the agent does not support it natively. Measure the profiler's own cost in canary first.
2. **Symbolization gaps.** eBPF and JIT languages need frame pointers or symbol tables present in production builds; strip them and you get "[unknown]" frames where the answer was. Ship unstripped symbols (or upload symbol files to the profiler server) as part of the build pipeline.
3. **Profiling the wrong dimension.** A CPU flamegraph of an I/O-bound service shows mostly idle stacks; use wall-clock/off-CPU profiles to find blocking, and check mutex profiles before concluding a lock refactor "fixed" anything. Match profile type to the suspected bottleneck (USE method: utilization, saturation, errors per resource).
4. **Using production profile data without traffic context.** A hot function at 02:00 might be a cron job, not user-facing latency; always slice by route, queue, or tenant before prioritizing optimizations. Profiles tell you where time goes, not whether users felt it.
5. **Treating profiles as a one-time audit.** Continuous profiling pays off as a permanent regression detector; running it only during incidents rebuilds baselines from scratch each time. Wire profile diffs into CI-adjacent workflows (nightly compare, release checklist) instead of hero debugging.

## Related

nodejs-profiling-v8, workers-cpu-profiling, performance-regression-detection, nodejs-heap-snapshots, latency-budget-allocation
