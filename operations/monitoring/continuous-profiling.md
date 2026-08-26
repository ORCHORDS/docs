# Continuous Profiling in Production

Continuous profiling captures stack-trace samples from running production
processes at low frequency (e.g. 100 Hz) and aggregates them into flamegraphs.
Unlike APM transaction traces, profiling answers *where inside the code* CPU,
memory allocations, lock contention, or I/O time is spent — even for the
requests you never traced. In 2026 the common stacks are Pyroscope, Parca,
Grafana's built-in profiler, and Datadog's Continuous Profiler.

## Symptom

- Overall CPU usage is 85% but `top` shows no single process is the culprit.
- GC pressure and allocation graphs (you already have those) spike but you
  cannot tell *which* code path is allocating.
- Latency p99 is high but no individual span is slow — the cost is spread
  across many small operations only visible at the line level.
- "The service is slow" with no clear bottleneck — flamegraphs surface the
  top function consuming cycles without needing a hypothesis first.
- Lock contention or syscall overhead not visible in any of your RED metrics.

## Gotchas

- **Profiling is sampling, not instrumentation.** You see where time is
  *probabilistically* spent. A function that runs in 100us but is called a
  million times will show up; a function called once and slow will not, unless
  you sample while it runs. Don't profile a one-off hang — use a trace.
- **`profiling` is not free.** It adds 0.5-3% CPU overhead typically, but the
  symbolization step on interpreted languages (Python, Ruby, PHP) can be
  notably heavier. Validate overhead in staging with a load test before
  enabling cluster-wide.
- **Missing symbols = useless flamegraphs.** Compiled Go/Rust/C binaries must
  ship with debug symbols (Go does by default; Rust needs
  `RUSTFLAGS="-C debuginfo=2"`). Stripped binaries produce a single `<unknown>`
  frame. Pyroscope and Parca can sometimes symbolize via `.debug` files
  uploaded separately (e.g. ELF `.gnu_debuglink`).
- **pprof vs. eBPF vs. OTel profiling.** Go's `net/http/pprof` is in-process
  and pulls samples on demand. eBPF (Parca Agent, Pyroscope eBPF mode,
  OTel profiling) samples from the kernel without app cooperation — works on
  any language but needs a recent kernel (5.4+) and elevated privileges.
- **Profile labels matter more than you think.** Tag profiles with
  `service_name`, `version`, and `env`. Without version labels you cannot
  diff "before deploy" vs. "after deploy" to prove a regression.
- **Long-tail latency is invisible in average profiles.** Aggregate
  flamegraphs show the mean. Use differential flamegraphs (compare two time
  windows) to see what changed during an incident, not just what is "big."
- **Allocation profiles ≠ heap profiles.** `alloc_objects`/`alloc_space`
  (Pyroscope `memory` / Go `alloc`) shows allocations over time; `inuse_space`
  shows current live heap. A leak shows in `inuse`, GC churn shows in `alloc`.
  Pick the right one for the symptom.

## Example: Pyroscope with Go

```go
// main.go
import "github.com/grafana/pyroscope-go"

func main() {
    pyroscope.Start(pyroscope.Config{
        ApplicationName: "payments-api",
        ServerAddress:   "http://pyroscope:4040",
        Logger:          pyroscope.StandardLogger,
        Tags:            map[string]string{"service.version": version},
        ProfileTypes: []pyroscope.ProfileType{
            pyroscope.ProfileCPU,
            pyroscope.ProfileAllocObjects,
            pyroscope.ProfileAllocSpace,
            pyroscope.ProfileInuseObjects,
            pyroscope.ProfileInuseSpace,
        },
    })
    // ... rest of app
}
```

## Example: Differential flamegraph for incident diff

Most profilers support comparing two time ranges. In Pyroscope/Grafana:

1. Select the service and `cpu` profile type.
2. Set "Compare" mode, pick the incident window vs. a baseline window.
3. Red bars = functions that grew during the incident. Blue = shrunk.
4. The largest red bar is your prime suspect.

## Verifying it works

- Load-test a known-slow endpoint and confirm the profile shows the expected
  hot function (e.g. a JSON marshal).
- Push a deliberately slow commit and confirm the diff flamegraph highlights
  the changed function within one sampling cycle (~30s at 100 Hz).
- Confirm the version tag updates with each deploy so diffs are reliable.
