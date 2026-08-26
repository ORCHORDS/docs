# JDK 24 virtual-thread synchronized pinning change

**Issue:** Guidance written for JDK 21–23 often says a virtual thread that blocks inside `synchronized` pins its carrier platform thread. JEP 491 changed this in JDK 24: monitor acquisition, holding, `Object.wait()`, and reacquisition can unmount virtual threads, eliminating nearly all synchronized-related pinning. Old diagnostics and automatic `ReentrantLock` rewrites can therefore be misleading after upgrade.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Record the exact JDK runtime used by each load test and production service; do not transfer pinning conclusions across the JDK 24 boundary.
- On JDK 24 and later, choose `synchronized` versus `java.util.concurrent.locks` for semantics and measured performance, not solely to avoid the old monitor-pinning behavior.
- Still keep blocking and I/O out of unnecessarily broad critical sections because contention and long lock hold time remain.
- Capture JDK Flight Recorder `jdk.VirtualThreadPinned` events for remaining pinning situations.
- Remove reliance on `-Djdk.tracePinnedThreads`; JEP 491 states that setting it has no effect after the change.
- Inventory native methods, Foreign Function and Memory calls with callbacks into blocking Java, class loading, and class initialization.
- Rebenchmark carrier utilization, throughput, latency, fairness, and deadlock behavior after migration.

## Implementation and tests

Run the same virtual-thread workload on the old supported JDK and JDK 24 or later. Include blocking I/O while holding a monitor, contention acquiring a monitor, `Object.wait()`, a native callback that blocks, and concurrent class initialization. Compare JFR pin events, carrier-thread saturation, throughput, and tail latency.

Test correctness separately: monitor mutual exclusion, visibility, reentrancy, interrupt handling, wait/notify, timeout, and shutdown. JEP 491 changes the JVM implementation’s ability to unmount; it does not relax Java synchronization semantics.

## Gotchas

“Nearly all” is not “all.” JEP 491 retains diagnostics for cases such as native code calling back into blocking Java and identifies class-resolution or initialization cases as remaining work. A lack of pinning does not eliminate lock contention, deadlock, starvation, native blocking, or poor critical-section design.

JEP 491 was delivered in JDK 24. Vendor builds and older releases must be tested rather than inferred.

## Official sources

- [OpenJDK JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [OpenJDK JDK 24 project](https://openjdk.org/projects/jdk/24/)
