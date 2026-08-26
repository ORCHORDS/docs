# time-travel-debugging-rr

**Issue:** A heisenbug corrupts state long before any symptom appears. By the time a breakpoint or watchpoint fires, the write that caused the damage has already happened, and every restart gives you a slightly different run. Classic debuggers only move forward, so you are left guessing at initial conditions. Record/replay ("time-travel") debugging fixes this ordering problem: you record the execution once, then replay it deterministically and step backward to the moment of corruption.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why record/replay changes the debugging model

1. **Recording makes execution deterministic.** rr captures the full syscall and signal interface between the program and the kernel, so a replay reproduces the original run instruction-for-instruction, including race outcomes. The bug you caught once on a Friday night now reproduces on demand, forever.
2. **Reverse execution turns questions around.** Instead of "where will this break", you ask "how did I get here": set a watchpoint on the corrupted variable, run `reverse-continue`, and the debugger stops at the exact instruction that performed the bad write. This combine-with-watchpoints workflow is rr's core value over plain gdb.
3. **It runs on commodity hardware.** rr was built by Mozilla to debug Firefox and now records large real-world targets including Chrome, LibreOffice, QEMU, and Go programs. It needs Linux x86/x64 hardware performance counters — which is also its main portability limit (no macOS, and most VMs hide the counters it requires).
4. **Traces are compact, durable, and portable.** A trace is a directory you can compress, copy to another machine, attach to a bug ticket, and replay there — turning "cannot reproduce" reports into reproducible artifacts.
5. **Multi-process workloads are first class.** Server-style trees of forked children (and containerized runs) record fine; on replay you pick the process you care about rather than stepping through all of them.

## Working with rr day to day

1. **Record before you need it: `rr record ./app` (or `rr record -- ./app args`).** Recording must happen while the bug occurs — you cannot attach retroactively to an already-running process. Overhead is typically modest; if timing-sensitive behavior hides from you, that is the nondeterminism rr exists to neutralize.
2. **Replay with `rr replay`; you are in gdb with extra commands.** The reverse commands mirror the forward ones: `reverse-continue` (`rc`), `reverse-next` (`rn`), `reverse-step`, `reverse-finish`. Anything you already know about gdb (breakpoints, Python scripting, TUI) carries over.
3. **Watchpoints are the killer feature.** `watch var` (write), `rwatch var` (read), `awatch var` (either) combined with `reverse-continue` answers "who touched this and when" in one round trip — the single most common time-travel workflow.
4. **Use `rr ps` for multi-process traces.** Traces of browsers or servers contain many processes; list them with `rr ps` and select the interesting one with `rr replay -p <pid-or-name>` (Firefox docs use `rr replay -p firefox`) instead of debugging the wrong child.
5. **Use `--chaos` when a race only triggers in production.** `rr record --chaos` deliberately scrambles scheduling priorities between threads to surface interleavings that normal runs rarely hit, turning a once-a-week flake into a once-per-recording one.

## Time-travel options beyond rr on Linux

1. **WinDbg Time Travel Debugging (TTD) is the Windows-native equivalent.** For Windows targets (including user-mode apps and services), WinDbg TTD records a trace you can step backward through with the same reverse-continue/reverse-step mental model; if your day job is win32/`git bash` environments, this is your rr substitute.
2. **There is no production JavaScript time-travel.** Node/V8 and browsers offer no rr-style recorder; for JS the practical approximation is heavy structured logging plus Error.prepareStackTrace capture, or a recorded DOM/network session via remote-debugging. Do not promise "time travel" for a Node service — budget for logging instead.
3. **gdb alone has `record full` but it is slow and fragile.** gdb's built-in process-record-and-replay works without perf counters and can be a fallback in a VM, but it cannot handle many modern syscalls (recording aborts) and the overhead is heavy; prefer rr whenever the environment allows it.
4. **Core dumps are the poor cousin.** A core file is one frozen moment; a trace is every moment. Keep cores for "what is the state right now" questions and reach for recording when the question is causal — "what led to this state".

## Limits and anti-patterns

1. **You must record the failing run; planning beats rescue.** Keep a small wrapper (`rr record --chaos npm test`) in flaky CI jobs or on the canary box so a trace exists when the bug next fires — post-mortem wishing does not create one.
2. **VMs and nested virtualization usually break it.** rr requires hardware performance counters exposed to the guest; typical cloud VMs and default VirtualBox/VMware configs do not pass them through. Bare metal, WSL2 with recent kernels (often), or CI runners with counter access are the safe bets — verify with `rr record /bin/true` before investing.
3. **Long-running daemons produce large traces.** Recording a multi-hour server is technically possible but unwieldy; the standard pattern is to record the unit test, reproducer script, or a bounded window that reaches the bug quickly.
4. **Replay is not a profiler.** rr answers causal questions under a debugger, not "where is time spent"; for performance work use perf and flame graphs (see the strace/perf article) — the two tools are complementary, not interchangeable.
5. **Do not confuse determinism with a fix.** A replay that reproduces reliably tells you the mechanism, not the repair; once rr shows you the interleaving, write the regression test (and the lock/ordering fix) in your normal toolchain — the test must pass without rr.

## Related

- strace-perf-for-app-developers (profiling, the other half of systems debugging)
- vscode-debugging-config (forward debugging, when that is enough)
