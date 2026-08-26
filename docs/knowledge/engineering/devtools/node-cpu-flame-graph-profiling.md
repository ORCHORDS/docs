# node-cpu-flame-graph-profiling

**Issue:** A Node.js service is slow or pinning a CPU core, but logs and APM dashboards only show that "request latency is high" without saying which function is burning the cycles. This article covers the current workflow for capturing a V8 CPU profile from a Node process (CLI flags, DevTools, or the inspector protocol) and reading it as a flame graph in speedscope, plus the practices that separate a useful profile from a misleading one.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Capturing a CPU profile

1. **`node --cpu-prof` (zero setup).** Start the process with `node --cpu-prof --cpu-prof-dir=./profiles --cpu-prof-name=run1.cpuprofile app.js` and it writes an isolate-specific `.cpuprofile` file on exit. Best for scripts, benchmarks, and reproducible test harnesses where you can control process lifetime.
2. **`--cpu-prof-interval` for short hot paths.** The default sampling interval is 1000 microseconds; lowering it (e.g. `--cpu-prof-interval=500`) catches shorter hot functions at the cost of a larger file. Raise it when profiling long-running servers to keep files manageable.
3. **DevTools attach via `chrome://inspect`.** Run node with `--inspect`, open `chrome://inspect`, attach to the target, and use the Performance/Profiler tab to record and stop a profile interactively. This is the fastest path when you cannot restart the process but can attach a debugger.
4. **Inspector protocol from code.** The `node:inspector` module exposes `Profiler.start` / `Profiler.stop`, so you can build an admin endpoint or signal handler (e.g. on SIGUSR2) that returns a profile as JSON on demand. This is the foundation for on-demand production profiling.
5. **Wrapper tools when you want opinionated output.** `0x` and Clinic.js (flame mode) wrap the process, capture a CPU profile, and render their own HTML flame graphs with process metadata. Useful for quick local investigations; raw `.cpuprofile` + speedscope remains the most portable format.

## Reading the flame graph in speedscope

1. **Open the profile without leaving the terminal or repo.** `npx speedscope profiles/run1.cpuprofile` launches a local viewer, and speedscope.app can open files entirely client-side for profiles that are not sensitive. Speedscope natively understands the V8 `.cpuprofile` format, so no conversion step is needed.
2. **Read width, not depth.** In the default left-heavy (icicle) view each box is a stack frame and width is self-plus-children time on the left-most aggregation; a wide frame near the top of the collapsed view is a hot code path. The left-heavy ordering merges identical stacks so recurring hot paths become visually obvious.
3. **Switch views deliberately.** Use "Left Heavy" for finding aggregate hot paths, "Chronological" flame chart to see phase changes (startup vs steady-state vs a load burst), and the sandwich view (top-down/bottom-up) to quantify a single function's total vs self time wherever it appears in the tree.
4. **Search and zoom instead of eyeballing.** Type a function or module name in the search box to highlight its frames and see what fraction of total time it accounts for; click a frame to zoom the tree to its subtree. Numbers beat impressions — a frame that "looks big" may be 0.4% of total time.
5. **Load multiple profiles into one comparison.** Speedscope accepts several profiles in one session, letting you diff before/after a fix or baseline vs loaded run to confirm the change actually moved the metric and that the hot spot was not noise.

## Best practices and pitfalls

1. **Profile a realistic workload.** An idle process produces a profile dominated by timers and the event loop; drive the app with a load generator, replayed traffic, or the actual failing scenario, otherwise you optimize the wrong thing.
2. **Keep profiling windows short and focused.** The sampling profiler adds overhead and the file grows with run time; capture the 10-60 seconds around the problem rather than hours. Long captures also make flame graphs unreadable.
3. **Treat single runs as noise until repeated.** JSIT behavior, GC timing, and machine state vary between runs; a frame that is 12% of one profile and 3% of the next is noise, not a hotspot. Confirm with at least two captures before rewriting code.
4. **Interpret synthetic frames correctly.** `(program)`, `(garbage collector)`, `(idle)` and `process._tickCallback` style frames are infrastructure, not your bug — but a fat `(garbage collector)` bar is a real signal that allocation churn (a memory problem) is stealing CPU.
5. **Fix by share of total, not by local micro-optimizations.** Use the sandwich view's self-time percentages to rank work; only after the top consumers are addressed do micro-level wins matter. Re-profile after each fix — the graph changes once the biggest flame is gone.
