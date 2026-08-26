# nodejs-profiling-v8

**Issue:** Node.js performance bottlenecks are unidentified
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
V8 includes a built-in CPU profiler. Node.js exposes it via --prof flag, generating a tick file that can be processed into a human-readable report.

## Pattern / Solution
1. Run: node --prof app.js.\n2. Process: node --prof-process isolate-*.log > profile.txt.\n3. Look for Bottom up (heavy) profile section; identify hot functions.\n4. Use 0x npm package for flamegraph visualization.\n5. Use clinic.js suite for automated bottleneck detection (clinic doctor, clinic flame).

## Gotchas
- --prof adds overhead; profile in a controlled load-test environment.\n- JIT deoptimizations (deopt) appear in the profile; investigate IC-related deoptimizations.\n- Async operations show as idle time; use async_hooks or clinic.js to trace async bottlenecks.

## Related
nodejs-event-loop-lag, nodejs-heap-snapshots, nodejs-worker-threads
