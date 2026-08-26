# nodejs-heap-snapshots

**Issue:** Node.js process memory grows continuously
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Node.js processes can develop memory leaks through event listener accumulation, closure leaks, or caching without eviction. Heap snapshots reveal the retained object graph.

## Pattern / Solution
1. Take snapshots programmatically: const v8 = require('v8'); v8.writeHeapSnapshot().\n2. Send SIGUSR2 to a running Node process with --inspect to trigger a snapshot.\n3. Load .heapsnapshot file in Chrome DevTools > Memory > Load.\n4. Compare two snapshots in Comparison view to find allocations growing between snapshots.\n5. Look for large Detached arrays or objects in the tree.

## Gotchas
- Taking a heap snapshot pauses the Node process; don't do it in production without preparation.\n- Use --max-old-space-size to limit heap before OOM kills the process.\n- clinic.js heapprofiler provides continuous heap allocation tracing without snapshots.

## Related
nodejs-profiling-v8, chrome-devtools-memory, memory-management-js
