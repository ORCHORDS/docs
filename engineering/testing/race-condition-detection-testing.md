# race-condition-detection-testing

**Issue:** Data races and concurrency bugs are non-deterministic: the same test can pass a thousand times and fail in production once two goroutines, threads, or async tasks interleave differently under load. Unit assertions alone cannot prove thread safety because they only observe the interleaving that happened to execute. Race detection requires a different toolbox: dynamic detectors such as ThreadSanitizer and Go's race detector that instrument memory accesses, stress loops that amplify scheduling variety, deadline-based bug reproduction, and CI policies that treat a single detector report as a hard failure rather than flakiness.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Dynamic race detectors

1. **Go tests: always run with -race.** Go's race detector (built on ThreadSanitizer, supported on amd64 and arm64) is enabled with go test -race and reports races between goroutines touching the same memory without synchronization. The cost is roughly 2-10x runtime and memory, cheap enough to make it the default for the whole suite in CI rather than a special job.
2. **C/C++ and Rust: build a TSan variant.** Compiling with -fsanitize=thread (Clang/GCC) or the equivalent sanitizer flag set produces a binary that detects races at runtime. Keep a dedicated CI job compiling the test suite with TSan because the instrumented build is incompatible with other sanitizers like ASan and with some lock-free libraries.
3. **Java: run concurrency tests under specific interleavings.** Tools in the jcstress lineage and stress executors with CPU pinning explore more interleavings than naive loops; combine them with memory-visibility assertions (reading a field without synchronization) that static analysis can also flag.
4. **JavaScript: single-threaded does not mean race-free.** Async interleaving between awaits, microtasks, and external events still produces logical races (check-then-act on shared state across awaits). Deterministic schedulers in test frameworks, explicit interleaving injection, and property tests on async state machines cover this class.

## Detector limitations to design around

1. **Detectors only find executed races.** TSan and the Go detector are dynamic: a race in an uncovered code path is invisible. Coverage of concurrent code paths is a precondition, so race-detection value scales with test coverage of the concurrency-heavy modules.
2. **Probability, not proof.** A passing race-detector run means no race was exhibited, not that none exists. Raise confidence by combining detectors with stress loops, higher iteration counts, and CPU load that shifts scheduling windows.
3. **False positives on custom synchronization.** Lock-free algorithms and memory-ordering tricks can be flagged incorrectly; the sanctioned response is suppression lists and runtime annotations documenting why the access is safe, kept small and reviewed, never a blanket disable.
4. **Overhead changes timing.** Instrumented builds run slower and allocate differently, which can both hide races (by serializing timing) and reveal ones production never hits; treat detector output as one signal alongside non-instrumented stress runs.

## Reproducing and pinning race bugs

1. **Write the reproducer as a stress loop with a deadline.** Loop the suspect operation for N iterations or M seconds and assert the invariant each iteration; a flaky bug becomes a reproducible test failure that CI can catch repeatedly. Keep the loop in the suite afterward as a regression guard.
2. **Vary the things the scheduler varies.** Thread counts, iteration counts, injected yields or sleeps at suspicious boundaries, and CPU contention (run the loop while another load spins) all widen the interleaving space explored.
3. **Assert invariants, not schedules.** Test the postcondition (counter equals number of increments, no lost updates, no duplicate ids) rather than the specific interleaving; schedules are unobservable and unstable across machines.
4. **Freeze concurrency bugs into deterministic tests where possible.** After fixing, add a test that drives the exact interleaving that failed (via controlled synchronization points) if the framework supports it, so the regression test does not itself become flaky.
5. **Capture the report artifact.** Detector reports contain stack traces for both accesses; save the full report in CI logs and link it from the issue, because the failing access pair is often the entire diagnosis.

## CI policy

1. **A detector report is a build failure, not flakiness.** Unlike assertion flakiness, TSan and -race reports have essentially no false-positive rate for ordinary code; retrying a race-detected test to green is hiding a real bug and must be prohibited.
2. **Run race jobs on every merge, with a longer nightly soak.** The merge job catches races in changed code cheaply; the nightly job runs higher iteration counts and stress variants to catch low-probability races across the whole suite.
3. **Keep suppression lists under review.** Any new suppression in a diff requires justification in review and an expiry or review date, or suppressions quietly become a graveyard of hidden races.
4. **Track race-find rate as a health metric.** A sudden drop in detector findings after a build config change usually means the detector stopped running, not that the code got safer; verify instrumentation is active, not silently disabled by an incompatible flag.
